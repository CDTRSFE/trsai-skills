#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update 能力的纯渲染层（契约 §4）。

职责边界（硬约束）：
  - 纯函数：只吃 dict、只吐 str；零网络、零文件 IO、零系统时钟调用。
  - 不做任何业务判定：能不能改、可不可达、算不算幂等，全部由 update_plan / update_exec
    在数据里定好，本模块只负责把已经定好的事实排版成中文文案。
  - 文案模板逐字冻结（契约 §4.1 / §4.2），单测按整段字符串断言，改一个字就是回归。

「旧值 → 新值」的写法由 _format_old_new 一处产出，预览与报告两处共用：
两处若各写一份格式化逻辑，用户在预览里确认过的样子和事后报告里看到的样子就会对不上。
"""

import math

# 多跳提示里的跳数上界。与 update_fields.MAX_HOPS 同值，
# 此处刻意用本地常量而不 import，保证渲染层不依赖任何其它模块（纯函数、可单独加载）。
_MAX_HOPS_DISPLAY = 2

# 空值占位符：旧值/新值为空时统一写它，不允许留空白（空白会让用户以为是排版错位）。
_EMPTY_PLACEHOLDER = "（空）"

# 多跳流转的固定提示（契约 §4.1，逐字）
_PREDICTED_SUFFIX = (
    "（需多步流转，执行时自动寻路，最多 {hops} 跳；"
    "若 {hops} 跳内到不了，该条会停在中间状态并记为失败，工具不会改回去）"
).format(hops=_MAX_HOPS_DISPLAY)

_TRUNCATE_WARNING = "若上一步查询结果标注「结果不完整」，请勿确认。"
_COMPLETE_SET_LINE = "助手声明：本清单为完整集合（非截断结果）"
_NO_UNDO_LINE = "本工具不提供撤销。"
_MULTI_HOP_NOTE = "若需多跳，后续跳的必填项按同样规则自动填充，预览无法提前列出。"
_HALF_DONE_PREFIX = "⚠ 半成品："

# TTL 秒数 → 有效期文案里的分钟数（契约 §4.1 只定义这两档）
_TTL_MINUTES = {900: 15, 300: 5}


# ---------------------------------------------------------------- 值格式化

def _display_value(value):
    """把字段值渲染成人类可读文本。

    None / 空串 / 空列表 → 「（空）」；列表 → 「[a, b]」；其余原样转字符串。
    """
    if value is None:
        return _EMPTY_PLACEHOLDER
    if isinstance(value, (list, tuple)):
        if not value:
            return _EMPTY_PLACEHOLDER
        return "[%s]" % ", ".join(str(item) for item in value)
    text = str(value)
    if text == "":
        return _EMPTY_PLACEHOLDER
    return text


def _format_old_new(old, new_display=None, new=None):
    """「旧值 → 新值」的唯一格式化入口，预览与报告共用（契约 §4.2 末条）。

    new_display 由 update_plan 预先算好（如日期带星期「2026-08-11（周二）」）；
    没给 new_display 时退回按 new 原值渲染。
    """
    if new_display is None or new_display == "":
        right = _display_value(new)
    else:
        right = str(new_display)
    return "%s → %s" % (_display_value(old), right)


DESCRIPTION_PREVIEW_CHARS = 300


def _format_description_change(change, indent):
    """描述专用行：只给新旧字符数与转换后正文前 300 字，不倾泻全文。

    设计稿场景 12 的预期业务结果就是「描述的新旧字符数与转换后正文前 300 字」。
    直接贴全文有实际危害：SKILL.md 强制模型把 preview_text 原样整段粘贴给用户，
    一篇几 KB 的描述会把条数、目标状态、有效期这些真正要复核的信息全淹掉。
    完整旧文不在预览里，但一直存在 plan 的 before 快照与审计中，出错时照样能回捞。
    """
    old = change.get("old") or ""
    new = change.get("new") if change.get("new") is not None else ""
    body = str(new)
    head = body[:DESCRIPTION_PREVIEW_CHARS].replace("\n", " ")
    if len(body) > DESCRIPTION_PREVIEW_CHARS:
        head += "……"
    lines = ["%s%s：%d 字 → %d 字" % (indent, change.get("name", "描述"),
                                     len(str(old)), len(body))]
    lines.append("%s    新正文前 %d 字：%s" % (indent, DESCRIPTION_PREVIEW_CHARS, head))
    return "\n".join(lines)


def format_change_line(change, indent="    "):
    """单条字段改动行：`<中文名>：<旧值> → <新值展示>`。

    描述走专用摘要分支（见 _format_description_change）。
    """
    if change.get("jira_field") == "description":
        return _format_description_change(change, indent)
    return "%s%s：%s" % (
        indent,
        change.get("name", change.get("jira_field", "")),
        _format_old_new(change.get("old"),
                        change.get("new_display"),
                        change.get("new")),
    )


# ---------------------------------------------------------------- 预览渲染

def _pending_count(items):
    """待执行条数：幂等短路（no_change）的条目不算，它们执行期会被直接跳过。"""
    return len([item for item in items if not item.get("no_change")])

def _estimate_minutes(pending):
    """耗时上界估算：每条至多 6 次请求 × 1 秒；不足 1 分钟也写 1 分钟。"""
    seconds = pending * 6
    return max(1, int(math.ceil(seconds / 60.0)))


def _ttl_minutes(ttl_seconds):
    """有效期分档。900 → 15 分钟，300 → 5 分钟；其余按秒换算兜底。"""
    if ttl_seconds in _TTL_MINUTES:
        return _TTL_MINUTES[ttl_seconds]
    try:
        return max(1, int(ttl_seconds) // 60)
    except (TypeError, ValueError):
        return 1


def _render_item(index, item):
    """渲染单条 issue 的明细块（条目头 + 字段行 + 状态行 + 自动填充行）。"""
    lines = ["[%d] %s" % (index, item.get("key", ""))]

    for change in item.get("field_changes") or []:
        lines.append(format_change_line(change))
        removed = change.get("removed") or []
        if removed:
            # 集合型字段被顶掉的项单起一行，缩进比字段行更深，避免和新值混读
            lines.append("        将被移除：%s" % "、".join(str(x) for x in removed))

    status_change = item.get("status_change")
    if status_change:
        line = "    状态：%s → %s" % (status_change.get("from_name", ""),
                                      status_change.get("to_name", ""))
        if status_change.get("reachability") == "predicted":
            line += _PREDICTED_SUFFIX
        lines.append(line)

        for filled in status_change.get("auto_filled") or []:
            # source 为 None 表示既无流转默认值也无候选值，本次不填，也就没什么可回显的
            if not filled.get("source"):
                continue
            lines.append("    自动填充：%s = %s（%s）" % (
                filled.get("name", filled.get("field", "")),
                filled.get("value_name", ""),
                filled.get("source"),
            ))

    return lines


def _alias_target_name(items):
    """口语别名映射到的目标状态名：取第一条带状态改动的条目。"""
    for item in items:
        status_change = item.get("status_change")
        if status_change and status_change.get("to_name"):
            return status_change["to_name"]
    return None


def render_preview(plan, meta):
    """渲染预览文案（契约 §4.1，逐字冻结）。

    plan 为 §5.1 冻结结构；meta 形如
      {"source_name", "base_date", "dup_removed", "plan_id", "ttl_seconds",
       "alias_note", "closed_count"}
    条件行（去重提示 / 别名说明 / 多跳说明 / 已关闭授权 / 完整集合断言）
    仅在条件成立时出现，不成立时整行不出现，不留空行。
    """
    items = plan.get("items") or []
    pending = _pending_count(items)
    lines = []

    # 1. 操作源回显（恒有）与基准日
    lines.append("操作源：%s" % meta.get("source_name", ""))
    lines.append("基准日：%s（本机当天）" % meta.get("base_date", ""))

    # 2. 总条数（+ 条件性的去重提示）
    dup_removed = meta.get("dup_removed") or 0
    if dup_removed > 0:
        lines.append("本次将修改 %d 条单（已去重 %d 条）：" % (len(items), dup_removed))
    else:
        lines.append("本次将修改 %d 条单：" % len(items))
    lines.append("")

    # 3. 逐条明细
    for index, item in enumerate(items, start=1):
        lines.extend(_render_item(index, item))
    lines.append("")

    # 4. 条件说明行：口语别名映射
    alias_note = meta.get("alias_note")
    target_name = _alias_target_name(items)
    if alias_note and target_name:
        lines.append("你说的「%s」已按约定映射为目标状态「%s」。" % (alias_note, target_name))

    # 5. 条件说明行：存在多跳条目时提醒后续跳无法提前列出
    has_predicted = any(
        (item.get("status_change") or {}).get("reachability") == "predicted"
        for item in items
    )
    if has_predicted:
        lines.append(_MULTI_HOP_NOTE)

    # 6. 耗时上界（批量执行无中途进度输出，这行是用户唯一的耗时预期来源）
    lines.append("预计执行耗时：约 %d 分钟（上界估算）" % _estimate_minutes(pending))

    # 7. 条件行：已显式授权对完成类单推状态（必须排在通知行之前）
    if plan.get("allow_closed_transition"):
        closed_count = meta.get("closed_count")
        if closed_count is None:
            closed_count = len([item for item in items if item.get("closed")])
        lines.append(
            "本次包含 %d 条已处于完成类状态的单，你已显式授权对它们推状态；"
            "这类流转在多数工作流里推不回来" % closed_count)

    # 8. 通知提示（固定措辞：不写「N 封邮件」、不逐单查关注人）
    lines.append("本次将对 %d 条单产生变更通知（按待执行条数估算，未逐单统计关注人；"
                 "一条单可能触达多名关注人）" % pending)

    # 9. 完整集合断言（条件）与截断警示（恒有）
    if plan.get("complete_set_declared"):
        lines.append(_COMPLETE_SET_LINE)
    lines.append(_TRUNCATE_WARNING)

    # 10. 有效期与免责末行
    lines.append("本预览 %d 分钟内有效（plan_id: %s）" % (
        _ttl_minutes(meta.get("ttl_seconds")), meta.get("plan_id", "")))
    lines.append(_NO_UNDO_LINE)

    return "\n".join(lines)


# ---------------------------------------------------------------- 报告渲染

def _item_reason(item):
    """取该条目的原因文案。

    正常路径由 update_exec 写好 reason；万一没写，用与预览逐字同源的
    _format_old_new 拼出「旧值 → 新值」兜底，保证两处写法永远一致。
    """
    reason = item.get("reason") or ""
    if reason:
        return reason
    changes = item.get("field_changes") or []
    if changes:
        return "；".join(format_change_line(change, indent="") for change in changes)
    return ""


def _render_report_entry(item):
    """报告里的单条：`    <单号> [⚠ 半成品：]<原因>`。"""
    parts = ["    %s" % item.get("key", "")]
    tail = ""
    if item.get("half_done"):
        tail += _HALF_DONE_PREFIX
    tail += _item_reason(item)
    if tail:
        parts.append(" %s" % tail)
    return "".join(parts)


def render_result(report):
    """渲染执行报告文案（契约 §4.2，逐字冻结）。

    第 2 行的三个数字恒出现（即使为 0）—— 模型不能靠「没提到失败」推断全都成功。
    「失败：」「跳过：」两段仅在该类非空时出现；成功条不逐条列。
    """
    counts = report.get("counts") or {}
    items = report.get("items") or []
    lines = []

    # 1. 操作源回显（与预览同口径）
    lines.append("操作源：%s" % (report.get("source") or report.get("source_name") or ""))

    # 2. 三分统计行（三个数字恒出现）
    lines.append("成功 %d 条 / 跳过 %d 条 / 失败 %d 条" % (
        counts.get("success", 0), counts.get("skipped", 0), counts.get("failed", 0)))

    failed = [item for item in items if item.get("result") == "failed"]
    skipped = [item for item in items if item.get("result") == "skipped"]
    resume_keys = report.get("resume_keys") or []
    audit_errors = report.get("audit_errors") or []

    body = []
    if failed:
        body.append("失败：")
        body.extend(_render_report_entry(item) for item in failed)
    if skipped:
        body.append("跳过：")
        body.extend(_render_report_entry(item) for item in skipped)
    if resume_keys:
        body.append("可补做的单号：%s" % ", ".join(resume_keys))
    if audit_errors:
        body.append("警告（审计落盘失败）：%s" % "；".join(audit_errors))

    if body:
        lines.append("")
        lines.extend(body)

    return "\n".join(lines)
