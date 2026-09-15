# -*- coding: utf-8 -*-
"""update 能力的执行时间轴（契约 §6，设计点 7 / 8 / 12）。

职责边界：
  - 消费 plan 里**已经解析完成**的载荷，逐条执行「抢改复核 → 关闭兜底 → 幂等判定
    → 写字段 → 推状态 → 落审计」，并汇总成三分报告；
  - 每一次 client.request 都单独 try/except，把失败收敛成**该条**的 failed，
    绝不让异常穿透到 main。

不做的事：不解析值、不重新换算日期、不重新检索经办人/版本/优先级
（两阶段门禁的语义是「确认什么就执行什么」，任何一处重算都会让实际写入值
与用户确认过的值不一致）；不渲染文案（渲染在 update_render）；不做补偿回滚。

三条最容易写错、写死在这里的口径：
  1. **异常不得穿透**。既有 cmd_apply 的 create 分支是「写完审计就 raise」，
     顺手复用那段 try/except 会让一条 403 打断整批、退出码变 1，
     进而让模型误判整件事失败而触发被明确禁止的自动重跑。
  2. **抢改复核逐条 GET，刻意不批量预读**。批量预读会把「读到当前值」到「发出写入」
     的窗口从单条往返拉大到整批往返，直接削弱防抢改效果。
  3. **比对键集合 = 本次 --set 字段键 ∪（仅当本次带 --status 时才并入的 status）**。
     本次不改状态却拿 status 参与比对，会让「用户只改截止日期、他人恰好推了一次
     无关状态」被无谓跳过，超出授权的复核范围。
"""

import hashlib

import update_fields
import update_plan
import update_render


# 逐条报告与审计里共用的固定文案（改一个字就是回归）
_REASON_IDEMPOTENT = "值已是目标值"
_REASON_CLOSED_BY_OTHERS = "执行前已被他人关闭，未获显式授权推状态"
_REASON_DRIFT_PREFIX = "他人已改动："

# 状态字段没有 FIELD_SPECS 条目，中文名单独定义
_STATUS_CN = "状态"

# 完成类状态的全稿唯一判据
_DONE_CATEGORY = "done"


# ---------------------------------------------------------------- 小工具

def _request(client_mod, source, method, path, body, rate):
    """所有请求的统一出口：只负责 429 计数，异常照常上抛，由各步骤单独接住。

    退避本身发生在 client.request 内部（静默 sleep），这里只能观测到
    「退避后仍然失败」的那次，因此 retry_after_seconds 保持为 0，
    不编造一个 client 没有暴露的数字。
    """
    try:
        return client_mod.request(source, method, path, body=body)
    except client_mod.JiraError as e:
        if e.error_code == "RATE_LIMITED":
            rate["count"] += 1
        raise


def _field_cn(field):
    if field == "status":
        return _STATUS_CN
    spec = update_fields.FIELD_SPECS.get(field)
    return spec["cn"] if spec else field


def _readable(field, value):
    """把字段值渲染成给人看的短文本（复用渲染层的空值/数组写法，避免两处不一致）。"""
    if field == "status":
        value = value.get("name") if isinstance(value, dict) else value
    elif field == "assignee":
        if isinstance(value, dict):
            value = value.get("displayName") or value.get("name")
    elif field == "priority":
        if isinstance(value, dict):
            value = value.get("name")
    elif field == "fixVersions":
        value = [v.get("name") if isinstance(v, dict) else v for v in (value or [])]
    return update_render._display_value(value)


def _set_fields(item):
    """本次 --set 的字段键：plan 的 before 存储键集合去掉恒存的 status。

    put_payload 的键与它一致，但 before 保留了原始顺序，报告里的「先报哪个字段
    被抢改」因此是确定的。
    """
    return [name for name in (item.get("before") or {}) if name != "status"]


def _status_of(fields):
    """从 issue 的 fields 里取状态三元组（id / name / category）。"""
    status = fields.get("status") or {}
    if not isinstance(status, dict):
        return {}
    category = (status.get("statusCategory") or {}).get("key")
    return {"id": status.get("id"), "name": status.get("name"), "category": category}


def _target_category(status_change, transitions):
    """目标状态的 statusCategory。

    plan 的 status_change 若记了 to_category 就用它；没记就从本跳的 transitions 里
    按目标名反查；都拿不到时退回 "done"（推状态的绝大多数目标是完成类，
    且该取值只影响「严格小于目标档」这条中间跳过滤，不会放宽终态词表拦截）。
    """
    recorded = (status_change or {}).get("to_category")
    if recorded:
        return recorded
    target_name = (status_change or {}).get("to_name")
    for tr in transitions or []:
        if tr.get("to_name") == target_name:
            return tr.get("to_category")
    return _DONE_CATEGORY


# ---------------------------------------------------------------- 审计

def _audit_old_value(field, value):
    """审计里的旧值表示，返回 (落盘值, 截断元数据)。

    summary 与 description **一律全文写入、不截断** —— 这两个字段是覆盖式写入、
    写错即原文丢失且工具不提供撤销，截断会让「从审计取回旧描述全文手工恢复」落空；
    它们本就被限制为只能单条修改，不存在批量放大的体积问题。
    其余字段超限时截断，并把长度与 sha1 前 8 位平铺在该字段记录上，
    供事后核对是不是同一份文本。
    """
    if field in ("summary", "description"):
        return value, {}
    if not isinstance(value, str) or len(value) <= update_fields.AUDIT_TRUNCATE_LIMIT:
        return value, {}
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return value[:update_fields.AUDIT_TRUNCATE_LIMIT], {
        "truncated": True, "length": len(value), "sha1": digest}


def _audit_field_changes(item):
    """审计用的字段改动清单：每字段 old/new，old 按体积规则处理。"""
    out = []
    for change in item.get("field_changes") or []:
        field = change.get("jira_field")
        old, meta = _audit_old_value(field, change.get("old"))
        record = {"field": field,
                  "jira_field": field,
                  "name": change.get("name"),
                  "old": old,
                  "new": change.get("new")}
        record.update(meta)
        out.append(record)
    return out


def _audit_record(plan, item, entry, extra, rate):
    """组装一条审计记录（契约 §6.2）。逐条处理完立刻写，不是批末统一写。"""
    status_result = entry.get("status_result") or {}
    hops = status_result.get("hops") or []
    record = {
        "action": "update",
        "plan_id": plan.get("plan_id"),
        "key": entry.get("key"),
        "result": entry.get("result"),
        "reason": entry.get("reason"),
        "field_changes": _audit_field_changes(item),
        "status_from": extra.get("status_from"),
        "status_to_id": hops[-1].get("to_id") if hops else None,
        "status_to_name": status_result.get("to_name"),
        "hops": hops,
        "half_done": entry.get("half_done"),
        "complete_set_declared": plan.get("complete_set_declared"),
        "base_url": plan.get("base_url"),
        "auto_fill_drift": entry.get("auto_fill_drift") or [],
        "rate_limit_seconds": rate.get("retry_after_seconds", 0),
        "rate_limit_count": rate.get("count", 0),
    }
    if extra.get("error"):
        # 逐条报告只给 JiraError.error 文本，error_code 留在审计里供事后排查
        record["error"] = extra["error"]
        record["error_code"] = extra.get("error_code")
    return record


# ---------------------------------------------------------------- 单条执行

def _entry(item, result, reason="", half_done=False, status_result=None, drift=None):
    return {
        "key": item.get("key"),
        "result": result,
        "half_done": half_done,
        "reason": reason,
        "field_changes": item.get("field_changes") or [],
        "status_result": status_result,
        "auto_fill_drift": drift or [],
    }


def _check_drift(item, current_fields, compare_status):
    """抢改复核：逐个比对本次要改的字段，返回首个不一致的原因文本或 None。

    比对键集合刻意窄于读取键集合：status 每条都读（供关闭判定、幂等判定与旧值留痕），
    但只有本次带了 --status 时才进入「不一致即跳过」的比对。
    """
    before = item.get("before") or {}
    keys = _set_fields(item)
    if compare_status:
        keys.append("status")
    for field in keys:
        if field not in before:
            continue
        old = before.get(field)
        now = current_fields.get(field)
        if update_fields.compare_field(field, old, now):
            continue
        return "%s%s 由 %s 变成 %s" % (_REASON_DRIFT_PREFIX, _field_cn(field),
                                       _readable(field, old), _readable(field, now))
    return None


def _is_idempotent(item, current_fields):
    """本条的所有目标值是否都已等于当前值（比对方向：目标载荷 ← 当前值）。

    fixVersions 的目标载荷只有 id、当前值只有 name，比不上就当作「不相等」，
    偏向多写一次而不是漏写 —— 漏写会让用户以为改了其实没改。
    """
    payload = item.get("put_payload") or {}
    for field, target in payload.items():
        if not update_fields.compare_field(field, target, current_fields.get(field)):
            return False
    return True


def _auto_fill_drift(plan_filled, actual_items):
    """比对预览期与执行期的自动填充结果，返回差异清单。

    只对第一跳做比对：预览本就声明了「后续跳的必填项无法提前列出」，
    拿没预览过的跳去报差异只会制造噪声。
    """
    preview_map = {f.get("field"): f for f in plan_filled or []}
    drift = []
    for actual in actual_items or []:
        field = actual.get("field")
        if field not in preview_map:
            continue
        previewed = preview_map[field]
        if previewed.get("value_name") == actual.get("value_name"):
            continue
        drift.append({"field": field,
                      "name": actual.get("name") or previewed.get("name"),
                      "preview": previewed.get("value_name"),
                      "actual": actual.get("value_name")})
    return drift


def _push_status(client_mod, source, item, current, rate, extra):
    """逐跳推状态。返回 (ok, status_result, drift, reason)。

    每跳前重新 GET transitions 并自行解析原始响应；最多 MAX_HOPS 跳，
    visited 防环。任一跳失败或走不通 → 该条失败且 half_done，**不做任何补偿、
    不改回去**。
    """
    status_change = item.get("status_change") or {}
    key = item.get("key")
    target_name = status_change.get("to_name")
    origin_name = current.get("name")
    hops = []
    visited = set()
    if origin_name:
        visited.add(origin_name)
    drift = []

    for hop_index in range(update_fields.MAX_HOPS):
        path = "/rest/api/2/issue/%s/transitions?expand=transitions.fields" % (
            client_mod.url_quote(key))
        try:
            resp = _request(client_mod, source, "GET", path, None, rate)
        except client_mod.JiraError as e:
            extra["error"] = e.error
            extra["error_code"] = e.error_code
            return False, _status_result(origin_name, target_name, hops), drift, \
                _half_done_reason(item, current, origin_name)

        transitions = update_plan.parse_transitions(resp)
        chosen = update_plan.pick_next_hop(
            transitions, current.get("category"), target_name,
            _target_category(status_change, transitions), visited)
        if chosen is None:
            return False, _status_result(origin_name, target_name, hops), drift, \
                _half_done_reason(item, current, origin_name)

        fields_payload, filled_items = update_plan.auto_fill(chosen.get("required") or [])
        if hop_index == 0:
            drift = _auto_fill_drift(status_change.get("auto_filled"), filled_items)

        body = {"transition": {"id": chosen.get("id")}}
        if fields_payload:
            body["fields"] = fields_payload
        try:
            _request(client_mod, source, "POST",
                     "/rest/api/2/issue/%s/transitions" % client_mod.url_quote(key),
                     body, rate)
        except client_mod.JiraError as e:
            extra["error"] = e.error
            extra["error_code"] = e.error_code
            return False, _status_result(origin_name, target_name, hops), drift, \
                _half_done_reason(item, current, origin_name)

        # 成功判据：client.request 未抛 JiraError 即成功，不解析返回体（204 无体）
        hops.append({"id": chosen.get("id"), "to_id": chosen.get("to_id"),
                     "to_name": chosen.get("to_name")})
        current = {"id": chosen.get("to_id"), "name": chosen.get("to_name"),
                   "category": chosen.get("to_category")}
        visited.add(chosen.get("to_name"))
        if chosen.get("to_name") == target_name:
            return True, _status_result(origin_name, target_name, hops), drift, ""

    # 跳数用尽仍未到目标
    return False, _status_result(origin_name, target_name, hops), drift, \
        _half_done_reason(item, current, origin_name)


def _status_result(from_name, to_name, hops):
    return {"from_name": from_name, "to_name": to_name, "hops": hops}


def _half_done_reason(item, current, origin_name):
    """半成品原因。字段确实写过才说「字段已改」，不写没发生的事。"""
    stopped = current.get("name")
    tail = "状态停在「%s」（原始状态 %s）；工具不会改回去" % (stopped, origin_name)
    if item.get("put_payload"):
        return "字段已改、" + tail
    return tail


def _execute_item(client_mod, source, plan, item, compare_status, rate):
    """单条 issue 的固定处理顺序，返回 (report_entry, extra, race_skipped)。"""
    key = item.get("key")
    extra = {"status_from": None}
    allow_closed = bool(plan.get("allow_closed_transition"))
    status_change = item.get("status_change")

    # 1. 抢改复核：逐条 GET，读取键 = 本次字段 ∪ status（status 恒读）
    read_fields = _set_fields(item)
    if "status" not in read_fields:
        read_fields = read_fields + ["status"]
    path = "/rest/api/2/issue/%s?fields=%s" % (client_mod.url_quote(key),
                                               ",".join(read_fields))
    try:
        resp = _request(client_mod, source, "GET", path, None, rate)
    except client_mod.JiraError as e:
        extra.update({"error": e.error, "error_code": e.error_code})
        return _entry(item, "failed", e.error), extra, False

    current_fields = resp.get("fields") or {}
    current = _status_of(current_fields)
    extra["status_from"] = current.get("name")

    drift_reason = _check_drift(item, current_fields, compare_status)
    if drift_reason:
        # 抢改跳过属于「本来就该做、这轮为了不覆盖别人而让开」，要进 resume_keys
        return _entry(item, "skipped", drift_reason), extra, True

    # 2. 关闭单 TOCTOU 兜底：预览时未关闭、执行前被他人关闭且未授权推状态
    closed_note = ""
    if (status_change and not item.get("closed")
            and current.get("category") == _DONE_CATEGORY and not allow_closed):
        status_change = None
        closed_note = _REASON_CLOSED_BY_OTHERS

    # 3. 幂等：无需改动的条目直接跳过，不进 resume_keys
    if item.get("no_change") or (status_change is None and _is_idempotent(item, current_fields)):
        reason = closed_note or _REASON_IDEMPOTENT
        return _entry(item, "skipped", reason), extra, False

    # 4. 写字段：一次 PUT，直接用 plan 里已解析好的载荷
    payload = item.get("put_payload") or {}
    if payload:
        try:
            _request(client_mod, source, "PUT",
                     "/rest/api/2/issue/%s" % client_mod.url_quote(key),
                     {"fields": payload}, rate)
        except client_mod.JiraError as e:
            extra.update({"error": e.error, "error_code": e.error_code})
            return _entry(item, "failed", e.error), extra, False

    # 5. 推状态
    if closed_note:
        # 字段已照改，但状态部分被兜底拦下 —— 本条按跳过计（状态没推成，不能算成功）
        return _entry(item, "skipped", closed_note), extra, False
    if status_change is None:
        return _entry(item, "success"), extra, False

    ok, status_result, drift, reason = _push_status(
        client_mod, source, item, current, rate, extra)
    if not ok:
        return _entry(item, "failed", reason, half_done=True,
                      status_result=status_result, drift=drift), extra, False

    if drift:
        # 自动填充与预览不一致不中止（结论 14 已接受自动填充的不确定性），但必须标注
        reason = "；".join(
            "自动填充值与预览不一致：%s 预览=%s 实际=%s"
            % (d.get("name"), d.get("preview"), d.get("actual")) for d in drift)
    else:
        reason = ""
    return _entry(item, "success", reason, status_result=status_result,
                  drift=drift), extra, False


# ---------------------------------------------------------------- 入口

def execute(client_mod, source, plan, audit_fn):
    """执行一份 update plan，返回契约 §6.1 的 report。

    audit_fn(record) 由调用方注入（jira_cli 传 planmod.audit 的偏函数）。
    整批跑完一律 ok/退出码由调用方按「无论逐条成败都成功」处理，
    逐条失败只体现在 report 里。
    """
    items = plan.get("items") or []
    # 「本次带了 --status」以 plan 里的显式标记为准。
    # 不能用 any(status_change) 反推：预览期的幂等短路会把已是目标状态那条的
    # status_change 置空，全部条目都幂等时反推为假，status 就被排除出比对键集合，
    # 他人在预览与执行之间把状态推回去也检不出来，最后报成 success。
    # 旧 plan（无该字段）回退到反推，保证跨版本的 plan 仍能执行。
    if "status_requested" in plan:
        compare_status = bool(plan["status_requested"])
    else:
        compare_status = any(item.get("status_change") for item in items)

    counts = {"success": 0, "skipped": 0, "failed": 0}
    rate = {"retry_after_seconds": 0, "count": 0}
    report_items = []
    resume_keys = []
    audit_errors = []

    for item in items:
        entry, extra, race_skipped = _execute_item(
            client_mod, source, plan, item, compare_status, rate)
        counts[entry["result"]] = counts.get(entry["result"], 0) + 1
        # 逐条追加审计：进程被打断后，审计是唯一能还原做了哪几条的凭据。
        # 写盘失败（磁盘满、权限异常）不得打断整批 —— 那会让已经改掉的前几条单
        # 既不在报告里、又要把退出码变成 1，比丢一行审计坏得多。
        # 但也不能静默吞掉：失败原因收进 audit_errors，由报告如实带出。
        try:
            audit_fn(_audit_record(plan, item, entry, extra, rate))
        except Exception as e:                      # noqa: BLE001 审计不可用不影响主流程
            audit_errors.append("%s: %s: %s" % (entry.get("key"), type(e).__name__, e))
        if entry["result"] == "failed" or race_skipped:
            resume_keys.append(entry["key"])
        report_items.append(entry)

    return {
        "source": plan.get("source"),
        "counts": counts,
        "has_failures": counts["failed"] > 0,
        "resume_keys": resume_keys,
        "items": report_items,
        "rate_limit": rate,
        "audit_errors": audit_errors,
    }
