# -*- coding: utf-8 -*-
"""分页、游标推进与分组计数（对齐设计 §6.3 / §6.4）。

硬规则：startAt 必须按【实际返回条数】推进——Jira 服务端会静默钳位
maxResults，按请求值推进会跳过 issue 且无任何报错。
"""

import re
import time

DEFAULT_FIELDS = ["summary", "status", "assignee", "duedate", "priority", "fixVersions"]

# 可枚举维度：候选集来源 + JQL 字段名
ENUMERABLE = {
    "status": ("GET", "/rest/api/2/status", "status"),
    "priority": ("GET", "/rest/api/2/priority", "priority"),
    "project": ("GET", "/rest/api/2/project", "project"),
    "fixVersion": ("VERSIONS", None, "fixVersion"),
}


def search(client, source, jql, fields=None, limit=None):
    """分页执行 JQL 查询，返回 {issues, total_in_jira, returned, truncated, truncated_reason}。"""
    page_size = source["max_results_per_page"]
    hard = source["hard_result_limit"] if limit is None else min(limit, source["hard_result_limit"])
    deadline = time.time() + source["total_deadline_seconds"]
    issues = []
    total = None
    truncated_reason = None
    while True:
        want = min(page_size, hard - len(issues))
        if want <= 0:
            truncated_reason = "hard_result_limit" if hard == source["hard_result_limit"] else "limit"
            break
        resp = client.request(source, "POST", "/rest/api/2/search", body={
            "jql": jql,
            "startAt": len(issues),
            "maxResults": want,
            "fields": fields or DEFAULT_FIELDS,
        })
        batch = resp.get("issues") or []
        total = resp.get("total", 0)
        issues.extend(batch)
        # 游标按实际返回条数推进（len(issues) 即累计实际条数）
        if not batch or len(issues) >= total:
            break
        if len(issues) >= hard:
            truncated_reason = "hard_result_limit" if hard == source["hard_result_limit"] else "limit"
            break
        if time.time() > deadline:
            truncated_reason = "total_deadline_seconds"
            break
    if total is None:
        total = 0
    truncated = len(issues) < total
    result = {
        "issues": issues,
        "total_in_jira": total,
        "returned": len(issues),
        "truncated": truncated,
    }
    if truncated:
        result["truncated_reason"] = truncated_reason or "hard_result_limit"
    return result


def _candidate_values(client, source, group_by, jql):
    """取候选集，返回 [(JQL 值, 显示名), ...]。

    实测发现（Jira 8.5.16 中文语言包）：/status、/priority 返回的是本地化
    显示名（如「待办」），但 JQL 只认原始名（如 "To Do"），用显示名写 JQL
    会 400「没有该值」。因此 status/priority 一律用 id 写 JQL、显示名做分组键。
    """
    kind, path, _ = ENUMERABLE[group_by]
    if kind == "GET":
        items = client.request(source, "GET", path)
        if group_by == "project":
            return [(it["key"], it["key"]) for it in items if it.get("key")]
        if group_by in ("status", "priority"):
            return [(it["id"], it.get("name") or it["id"])
                    for it in items if it.get("id")]
        return [(it["name"], it["name"]) for it in items if it.get("name")]
    # fixVersion：从 JQL 提取 project key 后查 versions
    m = re.search(r'project\s*=\s*"?([A-Za-z0-9_]+)"?', jql)
    if not m:
        raise client.JiraError(
            "CONFIG_ERROR", "group-by fixVersion 需要 JQL 中包含 project = <KEY>",
            "在 JQL 里加 project = 项目KEY 后再试")
    items = client.request(source, "GET",
                           "/rest/api/2/project/%s/versions" % m.group(1))
    return [('"%s"' % it["name"], it["name"]) for it in items if it.get("name")]


def _strip_order_by(jql):
    """剥离 JQL 末尾的 ORDER BY 子句，方便安全放入括号内进行条件组合。"""
    if not jql:
        return ""
    return re.sub(r'\s+order\s+by\s+.*$', '', jql, flags=re.IGNORECASE).strip()


def count_by(client, source, jql, group_by):
    """分组计数。可枚举维度走 maxResults=0 计数查询；其余走翻页扫描。"""
    filter_jql = _strip_order_by(jql)
    if group_by in ENUMERABLE:
        _, _, jql_field = ENUMERABLE[group_by]
        candidates = list(_candidate_values(client, source, group_by, filter_jql))
        groups = []
        for jql_value, display in candidates:
            query = "(%s) AND %s = %s" % (filter_jql, jql_field, jql_value) if filter_jql else "%s = %s" % (jql_field, jql_value)
            resp = client.request(source, "POST", "/rest/api/2/search", body={
                "jql": query,
                "maxResults": 0,
            })
            count = resp.get("total", 0) if isinstance(resp, dict) else 0
            if count > 0:
                groups.append({"key": display, "count": count})
        groups.sort(key=lambda g: -g["count"])

        # fixVersion 是多值字段（且单据可能无版本），累加组计数会导致重复计算；单独查真实总量
        if group_by == "fixVersion":
            base_resp = client.request(source, "POST", "/rest/api/2/search", body={
                "jql": filter_jql if filter_jql else "",
                "maxResults": 0,
            })
            total_in_jira = base_resp.get("total", 0) if isinstance(base_resp, dict) else 0
        else:
            total_in_jira = sum(g["count"] for g in groups)

        return {
            "group_by": group_by,
            "method": "count_query",
            "total_in_jira": total_in_jira,
            "partial": False,
            "groups": groups,
        }
    return _count_by_scan(client, source, filter_jql or jql, group_by)


def _count_by_scan(client, source, jql, group_by):
    """不可枚举维度（如 assignee）回退翻页统计，受双重上限约束。"""
    page_size = source["max_results_per_page"]
    scan_limit = source["aggregate_scan_limit"]
    deadline = time.time() + source["total_deadline_seconds"]
    counts = {}
    scanned = 0
    total = None
    partial = False
    while True:
        if scanned >= scan_limit or time.time() > deadline:
            partial = True
            break
        resp = client.request(source, "POST", "/rest/api/2/search", body={
            "jql": jql,
            "startAt": scanned,
            "maxResults": min(page_size, scan_limit - scanned),
            "fields": [group_by],
        })
        batch = resp.get("issues") or []
        total = resp.get("total", 0)
        for issue in batch:
            value = (issue.get("fields") or {}).get(group_by)
            if isinstance(value, dict):
                key = value.get("displayName") or value.get("name") or value.get("key") or "(空)"
            elif value is None:
                key = "(未分配)" if group_by == "assignee" else "(空)"
            else:
                key = str(value)
            counts[key] = counts.get(key, 0) + 1
        scanned += len(batch)
        if not batch or scanned >= total:
            break
    groups = [{"key": k, "count": v} for k, v in counts.items()]
    groups.sort(key=lambda g: -g["count"])
    return {
        "group_by": group_by,
        "method": "scan",
        "total_in_jira": total if total is not None else scanned,
        "scanned": scanned,
        "partial": partial,
        "groups": groups,
    }
