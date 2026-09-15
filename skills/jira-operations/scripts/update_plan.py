# -*- coding: utf-8 -*-
"""update 能力的预览组装层（契约 §5，联网）。

职责边界：
  - 自行解析 `GET /issue/{key}/transitions` 的**原始响应**（设计点 5 第 0 步）；
  - 状态寻路选边（直达优先 + statusCategory 单调 + 终态黑名单 + 防环）；
  - 流转必填项自动填充求值；
  - 预览主流程：本地校验 → 跨项目拦截 → 批量读单 → 名称解析 → 状态判定
    → blocker 整份拒绝 / 落 plan → 渲染 preview_text。

不做的事：不发任何写请求（PUT / POST transitions 全在 update_exec），
不重复实现值域解析（一律走 update_fields）、不重复实现文案（一律走 update_render）。

顺序即正确性（不得调换，见设计稿「预览阶段的判定顺序」）：
    幂等短路(1) → 完成类判定(2) → 项目 statuses 复核(3) → 可达性三档(4)。
幂等短路若不最先做，已处于目标状态的单会因为「没有指向自身的出边」被判不可达，
触发整份拒绝，与「已是目标值记跳过」的拍板正面冲突。
"""

import json

import plan as planmod
import update_fields
import update_render


# ---------------------------------------------------------------- 流转解析

def parse_transitions(resp):
    """解析 GET /issue/{key}/transitions?expand=transitions.fields 的**原始响应**。

    禁止复用 jira_cli.cmd_transitions 的裁剪结果：它只留了 id / name / to.name /
    required_fields 四项，把本层依赖的判据全丢了 —— to.statusCategory.key（档位）、
    to.id（审计要记）、必填项的 defaultValue 与 allowedValues（自动填充三分支）。

    返回 [{"id", "name", "to_id", "to_name", "to_category",
           "required": [{"field", "name", "default", "allowed"}]}]
    """
    out = []
    for item in (resp or {}).get("transitions") or []:
        to = item.get("to") or {}
        required = []
        for field_key, field_def in (item.get("fields") or {}).items():
            field_def = field_def or {}
            if not field_def.get("required"):
                continue
            required.append({
                "field": field_key,
                "name": field_def.get("name") or field_key,
                # 原始 defaultValue / allowedValues 一律原样保留，不做任何裁剪
                "default": field_def.get("defaultValue"),
                "allowed": list(field_def.get("allowedValues") or []),
            })
        out.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "to_id": to.get("id"),
            "to_name": to.get("name"),
            "to_category": ((to.get("statusCategory") or {}).get("key")),
            "required": required,
        })
    return out


# ---------------------------------------------------------------- 选边

def _has_terminal_keyword(name):
    """中间跳终态黑名单：这些状态在工作流里通常推不回来，且与用户意图无关。"""
    text = name or ""
    return any(word in text for word in update_fields.TERMINAL_KEYWORDS)


def _hop_sort_key(transition):
    """同档多条的排序键：数值 id 升序在前，非纯数字 id 按字符串排在全部数值项之后。

    必须按数值排 —— id 是 Jira 原样透传的字符串，直接字符串升序会得到
    "10" < "100" < "11" < "2"，选边结果依赖 id 的位数分布，可复现性就没了。
    """
    raw = "" if transition.get("id") is None else str(transition["id"])
    if raw.isdigit():
        return (0, int(raw), "")
    return (1, 0, raw)


def pick_next_hop(transitions, current_category, target_name, target_category, visited):
    """设计点 5 的选边算法。返回选中的 transition dict，无合规候选返回 None。

    1) 直达优先：存在 to_name 逐字等于 target_name 的流转 → 直接返回它（优先于一切规则）；
    2) 否则候选须同时满足档位「≥ 当前档 且 **严格小于** 目标档」、
       to_name 不含终态黑名单词、to_name 不在 visited；
    3) 同档多条按 int(id) 数值升序取第一条。

    档位取严格小于而不是「≤ 目标档」：目标为「已完成」（done）时，一个叫「已解决」的
    done 档状态既不在黑名单里、档位也合规，会被选作第一跳，而从「已解决」往往走不到
    「已完成」，单据就停在一个用户没要求的完结态上。
    """
    rank = update_fields.CATEGORY_RANK
    items = list(transitions or [])

    # 1) 直达优先：用户点名的目标状态本身是什么档都照走
    for transition in items:
        if transition.get("to_name") == target_name:
            return transition

    current_rank = rank.get(current_category, 0)
    # 目标档拿不到时按 done（2）兜底：这是最常见的目标档，且会把候选收得最紧
    target_rank = rank.get(target_category, rank["done"])

    candidates = []
    for transition in items:
        to_category = transition.get("to_category")
        if to_category not in rank:
            # 档位判据缺失就不敢选它 —— 宁可判不可达，也不在真实单据上乱走
            continue
        to_rank = rank[to_category]
        if to_rank < current_rank or to_rank >= target_rank:
            continue
        to_name = transition.get("to_name")
        if _has_terminal_keyword(to_name):
            continue
        if to_name in (visited or set()):
            continue
        candidates.append(transition)

    if not candidates:
        return None
    candidates.sort(key=_hop_sort_key)
    return candidates[0]


# ---------------------------------------------------------------- 自动填充

def _fill_value_payload(value):
    """把候选值转成 REST 载荷：带 id 的用 {"id": ...}，否则原样透传该元素。"""
    if isinstance(value, dict) and value.get("id") is not None:
        return {"id": value["id"]}
    return value


def _fill_value_names(value):
    """取候选值的 (id, 展示名) 用于预览回显。"""
    if isinstance(value, dict):
        return value.get("id"), (value.get("name") or value.get("value") or "")
    return None, "" if value is None else str(value)


def auto_fill(required_items):
    """流转必填项自动填充（结论 14 的显式让步）。

    对每项：有 defaultValue → 用它（source="流转默认值"）；
    否则取 allowedValues 首项（source="候选列表首项"）；两者都无 → 该项不填、source=None。

    返回 (fields_payload, display_items)。display_items 会把 source=None 的项也带上，
    渲染层自行跳过 —— 保留它是为了让「工具知道有个必填项没填」这件事不被静默吞掉。
    """
    payload = {}
    display = []
    for item in required_items or []:
        field = item.get("field")
        default = item.get("default")
        allowed = item.get("allowed") or []

        if default is not None:
            value, source = default, "流转默认值"
        elif allowed:
            value, source = allowed[0], "候选列表首项"
        else:
            value, source = None, None

        if source is not None:
            payload[field] = _fill_value_payload(value)
            value_id, value_name = _fill_value_names(value)
        else:
            value_id, value_name = None, ""

        display.append({
            "field": field,
            "name": item.get("name") or field,
            "value_id": value_id,
            "value_name": value_name,
            "source": source,
        })
    return payload, display


# ---------------------------------------------------------------- 预览辅助

def _project_prefix(key):
    return key.split("-", 1)[0]


def _fetch_project_statuses(client_mod, source, project_key, cache):
    """GET /rest/api/2/project/{key}/statuses —— 每项目一次，进程内缓存。"""
    if project_key not in cache:
        path = "/rest/api/2/project/%s/statuses" % client_mod.url_quote(project_key)
        resp = client_mod.request(source, "GET", path)
        cache[project_key] = resp if isinstance(resp, list) else []
    return cache[project_key]


def _statuses_of_issuetype(groups, issuetype):
    """按该 issue 自身的 issuetype 过滤出状态子集，**不取全项目并集**。

    取并集会把「只存在于缺陷工作流的状态」误判为任务单也可达，于是预览放行、
    执行期开始多跳乱走。找不到对应类型时返回 None，表示「判不了」，调用方跳过该项检查
    （判不了就不判，比按并集乱判安全）。
    """
    issuetype = issuetype or {}
    type_id = "" if issuetype.get("id") is None else str(issuetype["id"])
    type_name = issuetype.get("name") or ""
    for group in groups or []:
        group_id = "" if group.get("id") is None else str(group.get("id"))
        if (type_id and group_id == type_id) or (type_name and group.get("name") == type_name):
            return group.get("statuses") or []
    return None


def _shell_token(text):
    """把命令行片段包成可直接粘贴执行的形态（含空格/引号时套单引号）。"""
    text = "" if text is None else str(text)
    if text and all(ch.isalnum() or ch in "-_=./:" for ch in text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"


def _set_value_literal(value):
    """把 --set 的解析后值还原成命令行可用的字面量（能被 json.loads 还原回同一个值）。"""
    if isinstance(value, str):
        try:
            if json.loads(value) == value:
                return value
        except ValueError:
            # 不是合法 JSON，原样回填即可还原（_parse_field_kv 解析失败时保留原字符串）
            return value
    return json.dumps(value, ensure_ascii=False)


def _retry_command(source, keys, set_fields, opts):
    """拼一条「剔除 blocker 条目后可原样执行的完整命令行」。

    不给可执行命令行的话，50 条批量被一条 blocker 作废后，模型只能拿一堆 key 重拼，
    拼错一次就是又一轮请求。keys 为空（全部条目都是 blocker）时返回空串。
    """
    if not keys:
        return ""
    parts = ["jira_cli.py", "--source", _shell_token(source.get("name")), "update"]
    for key in keys:
        parts += ["--key", _shell_token(key)]
    for field, value in set_fields.items():
        parts += ["--set", _shell_token("%s=%s" % (field, _set_value_literal(value)))]
    if opts.get("status"):
        parts += ["--status", _shell_token(opts["status"])]
    if len(keys) >= 2:
        parts.append("--complete-set")
    if opts.get("allow_closed"):
        parts.append("--allow-closed-transition")
    parts.append("--preview")
    return " ".join(parts)


def _old_display_value(field, raw):
    """把 issue 上的原始字段值转成预览用的人类可读旧值。"""
    if raw is None:
        return None
    if field == "assignee":
        if isinstance(raw, dict):
            return raw.get("displayName") or raw.get("name")
        return raw
    if field == "priority":
        if isinstance(raw, dict):
            return raw.get("name")
        return raw
    if field == "fixVersions":
        return [v.get("name") if isinstance(v, dict) else v for v in raw or []]
    if field == "labels":
        return list(raw or [])
    return raw


def _new_display_value(field, resolved):
    """新值的人类可读形态 + 需要额外排版时的 new_display（不需要时给 None，由渲染层兜底）。"""
    if field == "duedate":
        if not resolved:
            return None, None
        return resolved, update_fields.format_date_display(resolved)
    if field == "assignee":
        if resolved is None:
            return None, None
        name = resolved.get("displayName") or resolved.get("name")
        return name, "%s（账号 %s）" % (name, resolved.get("name"))
    if field == "priority":
        return (resolved or {}).get("name"), None
    if field == "fixVersions":
        return [v.get("name") for v in resolved or []], None
    return resolved, None


def _removed_items(field, old_display, new_display):
    """集合型字段被顶掉的项（覆盖语义显式化：「加个标签」不能静默清掉原有标签）。"""
    if field not in ("labels", "fixVersions"):
        return []
    old_list = old_display or []
    new_list = new_display or []
    return [item for item in old_list if item not in new_list]


def _resolve_values(client_mod, source, set_fields, project_key, today):
    """名称/日期解析：同一个值只解析一次，结果给全部 key 共用。

    --set 对本次全部 key 是同一份，因此逐字段解析一次即可；
    跨项目改修复版本已在本地校验阶段被拒，这里只会面对单一项目。
    """
    resolved = {}
    for field, value in set_fields.items():
        if value is None:
            resolved[field] = None
            continue
        if field == "duedate":
            resolved[field] = update_fields.resolve_date(value, today)
        elif field == "assignee":
            resolved[field] = update_fields.resolve_user(client_mod, source, value)
        elif field == "priority":
            resolved[field] = update_fields.resolve_priority(client_mod, source, value)
        elif field == "fixVersions":
            resolved[field] = update_fields.resolve_versions(
                client_mod, source, project_key, value)
        else:
            resolved[field] = value
    return resolved


# ---------------------------------------------------------------- 预览主流程

def build_preview(client_mod, source, opts, plans_dir, today):
    """预览主流程，返回 (out_dict, exit_code) 供 cmd_update 直接 emit。

    opts: {"keys", "set_pairs", "status", "description", "complete_set",
           "allow_closed", "config"}
    失败一律抛 update_fields.UpdateError（由 cmd_update 统一转 emit）。
    """
    # ---------- 1. 本地校验（零网络）----------
    keys, dup_removed = update_fields.normalize_keys(opts.get("keys") or [])
    if opts.get("dup_removed") is not None:
        # cmd_update 已经归一化去重过时，以它算出的去重条数为准，避免预览少报
        dup_removed = opts["dup_removed"]
    is_batch = len(keys) >= 2

    raw_set = opts.get("set_pairs")
    if isinstance(raw_set, dict):
        set_fields = dict(raw_set)          # cmd_update 已经校验过就不重复走一遍
    else:
        set_fields = update_fields.parse_set_args(raw_set, is_batch)
    if opts.get("description") is not None:
        # 描述只能走 --description-file，内容由 cmd_update 读文件 + wiki 转换后传进来
        set_fields["description"] = opts["description"]

    update_fields.check_write_source(opts.get("config"), source.get("name"))

    # ---------- 2. 跨项目 fixVersions 拦截（仍在联网之前）----------
    if "fixVersions" in set_fields:
        prefixes = sorted({_project_prefix(k) for k in keys})
        if len(prefixes) > 1:
            raise update_fields.UpdateError(
                "CROSS_PROJECT_VERSION_FORBIDDEN",
                "修复版本是项目内实体，本次 key 跨了多个项目: %s" % "、".join(prefixes),
                "按项目拆成多条命令分别执行",
                exit_code=2)

    # ---------- 2.5 日期换算（纯本地，失败零网络开销）----------
    # 设计稿边界表把「日期词表外 / 本周X 已过去」归在**本地**判定阶段、退出码 2。
    # 放到联网之后解析会有一个很坏的后果：网络不通时先撞 NETWORK_ERROR（退出码 1），
    # 把「日期写错了」这个真正原因整个盖掉，用户只会去查网络。
    # resolve_date 对绝对日期是幂等的（YYYY-MM-DD 原样返回），后面 _resolve_values
    # 再解析一次不会有副作用，这里保留双重调用以防其它调用路径绕过本地校验。
    if set_fields.get("duedate") is not None:
        set_fields["duedate"] = update_fields.resolve_date(set_fields["duedate"], today)

    # ---------- 3. 批量读单 ----------
    fields = ["status", "issuetype", "project"]
    for field in sorted(set_fields):
        if field not in fields:
            fields.append(field)
    # JQL 只用 key in (...)：中文语言包下 JQL 不认状态/优先级显示名，写进去会直接 400
    jql = "key in (%s)" % ",".join(keys)
    resp = client_mod.request(source, "POST", "/rest/api/2/search",
                              body={"jql": jql, "fields": fields,
                                    "maxResults": len(keys)})
    found = {}
    for issue in (resp or {}).get("issues") or []:
        found[issue.get("key")] = issue
    missing = [k for k in keys if k not in found]
    if missing:
        raise update_fields.UpdateError(
            "NOT_FOUND",
            "以下 issue 查不到或无查看权限: %s" % ", ".join(missing),
            "Jira 对无权限的 issue 也返回查不到，确认单号与账号权限",
            exit_code=1)

    # ---------- 4. 名称解析（同值只解析一次）----------
    first_project = (found[keys[0]].get("fields") or {}).get("project") or {}
    resolved = _resolve_values(client_mod, source, set_fields,
                               first_project.get("key"), today)

    # ---------- 5. 逐条组装（含状态判定）----------
    raw_status = opts.get("status")
    target_name = update_fields.STATUS_ALIASES.get(raw_status, raw_status) if raw_status else None
    alias_note = raw_status if (raw_status and target_name != raw_status) else None

    statuses_cache = {}
    items = []
    blockers = []

    for key in keys:
        issue_fields = found[key].get("fields") or {}
        project_key = (issue_fields.get("project") or {}).get("key") or _project_prefix(key)

        field_changes = []
        put_payload = {}
        before = {}
        for field in sorted(set_fields):
            spec = update_fields.FIELD_SPECS.get(field, {
                "cn": field,
                "type": type(resolved[field]) if resolved[field] is not None else str,
                "clearable": "null",
                "batch": True,
                "resolve": "raw"
            })
            old_raw = issue_fields.get(field)
            old_display = _old_display_value(field, old_raw)
            new_value, new_display = _new_display_value(field, resolved[field])
            field_changes.append({
                "name": spec["cn"],
                "jira_field": field,
                "old": old_display,
                "new": new_value,
                "new_display": new_display,
                "removed": _removed_items(field, old_display, new_value),
            })
            put_payload[field] = update_fields.build_payload(field, resolved[field])
            # before 存的是**原始 Jira 值**，供执行期 compare_field 逐字段比对；
            # summary / description 存完整原文、不截断（写错即原文丢失且不提供撤销）
            before[field] = old_raw

        status_raw = issue_fields.get("status") or {}
        current_category = (status_raw.get("statusCategory") or {}).get("key")
        before["status"] = {"id": status_raw.get("id"),
                            "name": status_raw.get("name"),
                            "category": current_category}
        closed = current_category == "done"

        status_change = None
        if target_name:
            status_change, blocker = _plan_status(
                client_mod, source, key, issue_fields, status_raw, current_category,
                project_key, target_name, bool(opts.get("allow_closed")), statuses_cache)
            if blocker:
                blockers.append(blocker)

        items.append({
            "key": key,
            "project_key": project_key,
            "field_changes": field_changes,
            "put_payload": put_payload,
            "before": before,
            "status_change": status_change,
            # 无字段改动、也无需推状态 → 执行期直接记跳过（幂等短路条目就落在这里）
            "no_change": not put_payload and status_change is None,
            "closed": closed,
        })

    # ---------- 6. 任一 blocker → 整份拒绝，不落 plan ----------
    if blockers:
        blocked_keys = {b["key"] for b in blockers}
        survivors = [k for k in keys if k not in blocked_keys]
        raise update_fields.UpdateError(
            "PREVIEW_HAS_BLOCKERS",
            "有 %d 条单无法按本次要求修改，整份预览已拒绝（不落计划）" % len(blockers),
            "剔除这几条后重新预览，或改用它们当前可走的目标状态",
            exit_code=1,
            payload={"blockers": blockers,
                     "retry_command": _retry_command(source, survivors, set_fields, opts)})

    # ---------- 7. 落 plan（TTL 分档复用 plan.py 现有参数，plan.py 零改动）----------
    ttl_seconds = (update_fields.TTL_BATCH_SECONDS if is_batch
                   else update_fields.TTL_SINGLE_SECONDS)
    payload = {
        "action": "update",
        "source": source.get("name"),
        "base_url": source.get("base_url"),
        "ttl_seconds": ttl_seconds,
        "complete_set_declared": bool(opts.get("complete_set")),
        "allow_closed_transition": bool(opts.get("allow_closed")),
        # 本次是否带了 --status：执行期用它决定 status 要不要进抢改复核的比对键集合。
        # 不能靠「有没有条目带 status_change」反推 —— 幂等短路会把 status_change 置空，
        # 全部条目都已是目标状态时反推结果为假，status 被排除出比对，
        # 于是他人在预览与执行之间把状态改回去也检不出来，会误报成功。
        "status_requested": opts.get("status") is not None,
        "base_date": today.strftime("%Y-%m-%d"),
        "items": items,
        "totals": {"issues": len(items)},
    }
    plan = planmod.create_plan(plans_dir, payload, ttl_seconds=ttl_seconds)

    # ---------- 8. 渲染 ----------
    meta = {
        "source_name": source.get("name"),
        "base_date": payload["base_date"],
        "dup_removed": dup_removed,
        "plan_id": plan["plan_id"],
        "ttl_seconds": ttl_seconds,
        "alias_note": alias_note,
        "closed_count": len([i for i in items if i["closed"]]),
    }
    out = {
        "ok": True,
        "stage": "preview",
        "action": "update",
        "plan_id": plan["plan_id"],
        "expires_at": plan["expires_at"],
        "ttl_seconds": ttl_seconds,
        "preview_text": update_render.render_preview(payload, meta),
        "preview": payload,
        "hint": "确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"],
    }
    return out, 0


def _plan_status(client_mod, source, key, issue_fields, status_raw, current_category,
                 project_key, target_name, allow_closed, statuses_cache):
    """单条 issue 的状态判定，返回 (status_change, blocker)，两者最多一个非 None。

    判定顺序严格按设计稿：幂等短路(1) → 完成类判定(2) → 项目 statuses 复核(3)
    → 可达性三档(4)。顺序本身是正确性的一部分，不得调换。
    """
    current_name = status_raw.get("name")

    # 5.0 先拿原始流转（blocker 载荷里的「当前可走目标状态候选」也要靠它）
    resp = client_mod.request(
        source, "GET",
        "/rest/api/2/issue/%s/transitions?expand=transitions.fields" % key)
    transitions = parse_transitions(resp)
    available_targets = [t.get("to_name") for t in transitions if t.get("to_name")]

    # 5.1 幂等短路：必须最先做。已处于目标状态的单通常没有指向自身的出边，
    #     若先跑寻路必然得出「不可达 → blocker → 整份拒绝」，与「已是目标值记跳过」相悖。
    if current_name == target_name:
        return None, None

    # 5.2 完成类判定：用 statusCategory 结构化枚举，不用中文名（绕开本地化坑）
    if current_category == "done" and not allow_closed:
        return None, {
            "key": key,
            "code": "CLOSED_WITHOUT_AUTHORIZATION",
            "reason": "已是完成类状态「%s」，未获显式授权推状态" % current_name,
            "available_targets": available_targets,
        }

    # 5.3 项目状态清单复核：按该 issue 自身的 issuetype 过滤，不取全项目并集
    groups = _fetch_project_statuses(client_mod, source, project_key, statuses_cache)
    subset = _statuses_of_issuetype(groups, issue_fields.get("issuetype"))
    target_category = None
    if subset is not None:
        hit = [s for s in subset if s.get("name") == target_name]
        if not hit:
            return None, {
                "key": key,
                "code": "STATUS_NOT_IN_PROJECT",
                "reason": "目标状态「%s」不在该单所属类型「%s」的状态集合内"
                          % (target_name, (issue_fields.get("issuetype") or {}).get("name")),
                "available_targets": available_targets,
            }
        target_category = (hit[0].get("statusCategory") or {}).get("key")

    if target_category is None:
        # statuses 判不出目标档时退回从流转出边推断，仍推不出就交给 pick_next_hop 兜底
        for transition in transitions:
            if transition.get("to_name") == target_name:
                target_category = transition.get("to_category")
                break

    # 5.4 可达性三档
    direct = None
    for transition in transitions:
        if transition.get("to_name") == target_name:
            direct = transition
            break

    if direct is not None:
        reachability, hop = "direct", direct
    elif current_category == "done":
        # 带 --allow-closed-transition 的完成类单**只判直达一跳**：
        # done 档内 statusCategory 单调推进规则本身失效，再探索就是乱走
        return None, {
            "key": key,
            "code": "STATUS_UNREACHABLE",
            "reason": "已是完成类状态「%s」，且没有直达「%s」的流转（完成类单不做多跳探索）"
                      % (current_name, target_name),
            "available_targets": available_targets,
        }
    else:
        hop = pick_next_hop(transitions, current_category, target_name,
                            target_category, set())
        if hop is None:
            return None, {
                "key": key,
                "code": "STATUS_UNREACHABLE",
                "reason": "当前状态「%s」没有通向「%s」的合规流转" % (current_name, target_name),
                "available_targets": available_targets,
            }
        reachability = "predicted"

    _, auto_filled = auto_fill(hop.get("required"))
    return {
        "from_id": status_raw.get("id"),
        "from_name": current_name,
        "to_name": target_name,
        # to_category 是给执行期寻路用的目标档位判据（update_exec._target_category 会先读它）。
        # 不记的话执行期只能从「首跳的出边里按名字反查」，而 predicted 条目的首跳出边里
        # 恰恰没有目标状态，只能退回按 done 兜底 —— 目标本身是中间档时会放宽选边条件。
        "to_category": target_category,
        "reachability": reachability,
        "auto_filled": auto_filled,
    }, None
