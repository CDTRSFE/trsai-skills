#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jira_cli：Jira 读 + 单条创建命令行入口（纯标准库）。

输出契约（设计 §8.3）：stdout 恒为单个 JSON 对象；
成功 {"ok": true, ...}，失败 {"ok": false, "error_code", "error", "hint"}；
退出码：成功 0 / 业务失败 1 / 配置参数错误 2。
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _atomic
import client
import paging
import plan as planmod
import update_exec
import update_fields
import update_plan
import update_render
import wiki

__version__ = "1.0.0"
BUILT_AT = "2026-08-05"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_CONFIG = os.path.join(SKILL_DIR, "jira_config.json")
STATE_DIR = os.path.join(SKILL_DIR, "state")
PLANS_DIR = os.path.join(STATE_DIR, "plans")
WATCH_DIR = os.path.join(STATE_DIR, "watch")
AUDIT_LOG = os.path.join(STATE_DIR, "audit.log")

WATCH_RETENTION_DAYS = 90


def emit(obj, exit_code=0):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return exit_code


def fail(error_code, error, hint="", exit_code=1):
    return emit({"ok": False, "error_code": error_code, "error": error, "hint": hint},
                exit_code)


def _script_info():
    return {"script_version": __version__, "built_at": BUILT_AT}


def _browse_url(source, key):
    return client.build_url(source, "/browse/" + key)


def _slim_issue(source, issue):
    fields = issue.get("fields") or {}
    key = issue.get("key", "")
    return {"key": key, "fields": fields, "url": _browse_url(source, key)}


# ---------------------------------------------------------------- 只读命令

def cmd_search(args, config):
    source = client.pick_source(config, args.source)
    fields = list(paging.DEFAULT_FIELDS)
    if args.fields:
        for f in args.fields.split(","):
            f = f.strip()
            if f and f not in fields:
                fields.append(f)
    result = paging.search(client, source, args.jql, fields=fields, limit=args.limit)
    out = {"ok": True, "action": "search", "source": source["name"],
           "jql": args.jql,
           "total_in_jira": result["total_in_jira"],
           "returned": result["returned"],
           "truncated": result["truncated"],
           "issues": [_slim_issue(source, i) for i in result["issues"]]}
    if result["truncated"]:
        out["truncated_reason"] = result.get("truncated_reason")
    out.update(client.tls_note(source))
    return emit(out)


def cmd_get(args, config):
    source = client.pick_source(config, args.source)
    key = client.normalize_issue_key(args.key)
    issue = client.request(source, "GET", "/rest/api/2/issue/" + key)
    return emit({"ok": True, "action": "get", "source": source["name"],
                 "issue": _slim_issue(source, issue)})


def cmd_count_by(args, config):
    source = client.pick_source(config, args.source)
    result = paging.count_by(client, source, args.jql, args.group_by)
    out = {"ok": True, "action": "count-by", "source": source["name"]}
    out.update(result)
    out.update(client.tls_note(source))
    return emit(out)


def cmd_transitions(args, config):
    source = client.pick_source(config, args.source)
    key = client.normalize_issue_key(args.key)
    resp = client.request(source, "GET",
                          "/rest/api/2/issue/%s/transitions?expand=transitions.fields" % key)
    transitions = []
    for t in resp.get("transitions") or []:
        required = [fk for fk, fv in (t.get("fields") or {}).items()
                    if (fv or {}).get("required")]
        transitions.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "to": (t.get("to") or {}).get("name"),
            "required_fields": required,
        })
    return emit({"ok": True, "action": "transitions", "source": source["name"],
                 "key": key, "transitions": transitions})


def _createmeta_path(project, issuetype=None):
    if issuetype:
        return ("/rest/api/2/issue/createmeta?projectKeys=%s&issuetypeNames=%s"
                "&expand=projects.issuetypes.fields"
                % (client.url_quote(project), client.url_quote(issuetype)))
    return ("/rest/api/2/issue/createmeta?projectKeys=%s"
            "&expand=projects.issuetypes.fields"
            % client.url_quote(project))


def cmd_createmeta(args, config):
    source = client.pick_source(config, args.source)
    resp = client.request(source, "GET", _createmeta_path(args.project, args.type))
    projects = resp.get("projects") or []
    if not projects:
        return fail("NOT_FOUND", "createmeta 未返回项目 [%s]" % args.project,
                    "确认项目 KEY 存在且账号可见")
    issuetypes = projects[0].get("issuetypes") or []
    if not args.type:
        types = [{"id": it.get("id"), "name": it.get("name"), "subtask": bool(it.get("subtask"))}
                 for it in issuetypes]
        return emit({"ok": True, "action": "createmeta_types", "source": source["name"],
                     "project": args.project, "count": len(types), "types": types})
    if not issuetypes:
        return fail("NOT_FOUND",
                    "项目 [%s] 下未找到 issue 类型 [%s]" % (args.project, args.type),
                    "运行 createmeta --project %s 确认可用类型名" % args.project)
    fields = []
    for fkey, fdef in (issuetypes[0].get("fields") or {}).items():
        fields.append({"key": fkey,
                       "name": (fdef or {}).get("name"),
                       "required": bool((fdef or {}).get("required"))})
    fields.sort(key=lambda f: (not f["required"], f["key"]))
    return emit({"ok": True, "action": "createmeta", "source": source["name"],
                 "project": args.project, "type": args.type, "fields": fields})


def cmd_fields(args, config):
    source = client.pick_source(config, args.source)
    items = client.request(source, "GET", "/rest/api/2/field")
    if args.grep:
        kw = args.grep.lower()
        items = [it for it in items
                 if kw in (it.get("id", "") + " " + it.get("name", "")).lower()]
    if args.full:
        fields = items
    else:
        fields = [{"id": it.get("id"), "name": it.get("name"),
                   "custom": bool(it.get("custom"))} for it in items]
    return emit({"ok": True, "action": "fields", "source": source["name"],
                 "count": len(fields), "fields": fields})


def cmd_whoami(args, config):
    source = client.pick_source(config, args.source)
    user = client.request(source, "GET", "/rest/api/2/myself")
    out = {"ok": True, "action": "whoami", "source": source["name"],
           "user": {"name": user.get("name"),
                    "displayName": user.get("displayName"),
                    "emailAddress": user.get("emailAddress")}}
    out.update(_script_info())
    out.update(client.tls_note(source))
    return emit(out)


def cmd_serverinfo(args, config):
    source = client.pick_source(config, args.source)
    info = client.request(source, "GET", "/rest/api/2/serverInfo")
    out = {"ok": True, "action": "serverinfo", "source": source["name"],
           "version": info.get("version"),
           "buildNumber": info.get("buildNumber"),
           "serverTitle": info.get("serverTitle")}
    out.update(_script_info())
    out.update(client.tls_note(source))
    return emit(out)


# ---------------------------------------------------------------- watch

def _watch_state_path(source_name, name):
    key = "%s:%s" % (source_name, name)
    return os.path.join(WATCH_DIR, hashlib.sha256(key.encode("utf-8")).hexdigest()[:12] + ".json")


def _load_watch_state(path, name):
    """state 文件损坏时降级为空状态，不崩。"""
    if not os.path.isfile(path):
        return {"name": name, "seen": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state.get("seen"), dict):
            raise ValueError("seen 字段非法")
        return state
    except (ValueError, OSError):
        return {"name": name, "seen": {}}


def cmd_watch(args, config):
    source = client.pick_source(config, args.source)
    jql_hash = hashlib.sha256(args.jql.encode("utf-8")).hexdigest()
    path = _watch_state_path(source["name"], args.name)
    state = _load_watch_state(path, args.name)
    if state.get("jql_sha256") and state["jql_sha256"] != jql_hash and not args.reset:
        return fail("WATCH_JQL_CHANGED",
                    "监控 [%s] 已绑定不同的 JQL，旧状态不会静默压掉新结果" % args.name,
                    "确认要换 JQL 请加 --reset 重置状态", exit_code=2)
    if args.reset:
        state = {"name": args.name, "seen": {}}
    result = paging.search(client, source, args.jql)
    now = datetime.now(timezone.utc).astimezone()
    seen = state["seen"]
    new_issues = []
    for issue in result["issues"]:
        if issue.get("key") not in seen:
            new_issues.append(_slim_issue(source, issue))
    out = {"ok": True, "action": "watch", "source": source["name"],
           "name": args.name, "peek": bool(args.peek),
           "total_in_jira": result["total_in_jira"],
           "returned": result["returned"],
           "truncated": result["truncated"],
           "new_count": len(new_issues), "issues": new_issues}
    code = emit(out)
    # 「已见」标记推迟到 stdout 成功写完之后；--peek 只看不标记
    if code == 0 and not args.peek:
        cutoff = (now - timedelta(days=WATCH_RETENTION_DAYS)).isoformat()
        for issue in result["issues"]:
            seen.setdefault(issue.get("key"), now.isoformat())
        state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
        state["name"] = args.name
        state["jql_sha256"] = jql_hash
        _atomic.atomic_write(path, json.dumps(state, ensure_ascii=False, indent=2))
    return code


# ---------------------------------------------------------------- 写命令（两阶段）

def _parse_field_kv(raw, opt_name="--field"):
    """解析 k=v 参数。opt_name 只影响报错文案：create 用 --field，update 用 --set。"""
    if "=" not in raw:
        raise client.JiraError("CONFIG_ERROR",
                               "%s 参数必须是 k=v 形式: %s" % (opt_name, raw),
                               "例如 %s labels=test" % opt_name)
    key, value = raw.split("=", 1)
    try:
        value = json.loads(value)
    except ValueError:
        pass
    return key, value


def cmd_create(args, config):
    source = client.pick_source(config, args.source)
    if not args.preview:
        return fail("PREVIEW_REQUIRED",
                    "创建必须先 --preview 生成预览，再由人确认后 apply",
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行",
                    exit_code=2)
    project_key = getattr(args, "project", None)
    type_name = getattr(args, "type", None)
    parent_key = getattr(args, "parent", None)

    if parent_key:
        parent_key = client.normalize_issue_key(parent_key)
        if not project_key and "-" in parent_key:
            project_key = parent_key.split("-")[0]
        if not type_name:
            type_name = "子任务"

    if not project_key or not type_name:
        return fail("CONFIG_ERROR", "必须提供 --project 和 --type（或提供 --parent）",
                    "例如: create --project TRS --type 任务 --summary '...' --preview，或 create --parent TRS-1 --summary '...' --preview",
                    exit_code=2)

    fields = {
        "project": {"key": project_key},
        "issuetype": {"name": type_name},
        "summary": args.summary,
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}

    if args.description_file:
        try:
            with open(args.description_file, "r", encoding="utf-8") as f:
                description = f.read()
        except OSError as e:
            return fail("CONFIG_ERROR", "读取描述文件失败: %s" % e,
                        "检查 --description-file 路径", exit_code=2)
        if args.description_format == "md":
            description = wiki.md_to_wiki(description)
        fields["description"] = description
    for raw in args.field or []:
        key, value = _parse_field_kv(raw)
        if key in ("project", "issuetype", "summary", "parent", "description"):
            return fail("FIELD_CONFLICT",
                        "核心字段 %s 请直接使用专用参数，禁止通过 --field 覆盖" % key,
                        "例如: --summary、--project、--type、--parent、--description-file", exit_code=2)
        fields[key] = value
    # 用 createmeta 校验必填字段，缺失直接报错，不允许模型填占位内容
    meta = client.request(source, "GET", _createmeta_path(project_key, type_name))
    projects = meta.get("projects") or []
    issuetypes = projects[0].get("issuetypes") if projects else []
    if not issuetypes:
        return fail("NOT_FOUND",
                    "项目 [%s] 或类型 [%s] 不存在（createmeta 为空）" % (project_key, type_name),
                    "用 createmeta --project <KEY> 确认可用的项目与类型名")
    required = [fkey for fkey, fdef in (issuetypes[0].get("fields") or {}).items()
                if (fdef or {}).get("required")]
    missing = [fkey for fkey in required if fkey not in fields]
    if missing:
        return fail("MISSING_REQUIRED_FIELDS",
                    "缺少创建必填字段: %s" % ", ".join(missing),
                    "用 --field k=v 补齐；不允许编造占位内容", exit_code=2)
    plan = planmod.create_plan(PLANS_DIR, {
        "action": "create",
        "source": source["name"],
        "base_url": source.get("base_url"),
        "project": project_key,
        "type": type_name,
        "parent": parent_key,
        "fields": fields,
    })
    preview = {"summary": args.summary}
    if parent_key:
        preview["parent"] = parent_key
    if "description" in fields:
        preview["description"] = fields["description"]
    for k, v in fields.items():
        if k not in ("project", "issuetype", "summary", "description", "parent"):
            preview[k] = v
    target_str = "%s / %s" % (project_key, type_name)
    if parent_key:
        target_str += " (父单: %s)" % parent_key
    return emit({"ok": True, "stage": "preview",
                 "plan_id": plan["plan_id"],
                 "expires_at": plan["expires_at"],
                 "action": "create",
                 "target": target_str,
                 "changes": [{"field": k, "to": v} for k, v in preview.items()],
                 "hint": "确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"]})


def cmd_comment(args, config):
    source = client.pick_source(config, args.source)
    key = client.normalize_issue_key(args.key)
    if args.list:
        resp = client.request(source, "GET", "/rest/api/2/issue/%s/comment" % client.url_quote(key))
        comments = resp.get("comments") or []
        slim = []
        for c in comments:
            author = (c.get("author") or {}).get("displayName") or (c.get("author") or {}).get("name")
            slim.append({
                "id": c.get("id"),
                "author": author,
                "created": c.get("created"),
                "updated": c.get("updated"),
                "body": c.get("body"),
            })
        return emit({"ok": True, "action": "comment_list", "source": source["name"],
                     "key": key, "total": resp.get("total", len(slim)), "comments": slim})

    if not args.body and not args.body_file:
        return fail("MISSING_ARGUMENT", "请指定 --body 或 --body-file",
                    "例如: comment --key TRS-1 --body '备注内容' --preview", exit_code=2)
    if not args.preview:
        return fail("PREVIEW_REQUIRED", "添加备注必须先 --preview 生成预览，再由人确认后 apply",
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行", exit_code=2)

    body_text = args.body or ""
    if args.body_file:
        try:
            with open(args.body_file, "r", encoding="utf-8") as f:
                body_text = f.read()
        except OSError as e:
            return fail("CONFIG_ERROR", "读取备注文件失败: %s" % e, "检查 --body-file 路径", exit_code=2)
    if getattr(args, "body_format", "md") == "md":
        body_text = wiki.md_to_wiki(body_text)

    plan = planmod.create_plan(PLANS_DIR, {
        "action": "comment",
        "source": source["name"],
        "base_url": source.get("base_url"),
        "key": key,
        "body": body_text,
    })
    return emit({"ok": True, "stage": "preview",
                 "plan_id": plan["plan_id"],
                 "expires_at": plan["expires_at"],
                 "action": "comment",
                 "target": key,
                 "changes": [{"field": "comment", "to": body_text[:200] + ("..." if len(body_text) > 200 else "")}],
                 "hint": "确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"]})


def cmd_assign(args, config):
    source = client.pick_source(config, args.source)
    key = client.normalize_issue_key(args.key)
    target_user = None
    if args.to_me:
        who = client.request(source, "GET", "/rest/api/2/myself")
        target_user = who.get("name")
        if not target_user:
            return fail("SERVER_ERROR", "无法获取当前用户名", "检查 whoami 接口")
    elif args.unassign:
        target_user = None
    elif args.to:
        target_user = args.to
    else:
        return fail("MISSING_ARGUMENT", "请指定 --to <用户名>、--to-me 或 --unassign", exit_code=2)

    if not args.preview:
        return fail("PREVIEW_REQUIRED", "分配经办人必须先 --preview 生成预览，再由人确认后 apply",
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行", exit_code=2)

    plan = planmod.create_plan(PLANS_DIR, {
        "action": "assign",
        "source": source["name"],
        "base_url": source.get("base_url"),
        "key": key,
        "assignee": target_user,
    })
    return emit({"ok": True, "stage": "preview",
                 "plan_id": plan["plan_id"],
                 "expires_at": plan["expires_at"],
                 "action": "assign",
                 "target": key,
                 "changes": [{"field": "assignee", "to": target_user or "未分配"}],
                 "hint": "确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"]})


def cmd_link(args, config):
    source = client.pick_source(config, args.source)
    if args.list_types:
        resp = client.request(source, "GET", "/rest/api/2/issueLinkType")
        types = resp.get("issueLinkTypes") or []
        slim = [{"id": t.get("id"), "name": t.get("name"), "inward": t.get("inward"), "outward": t.get("outward")} for t in types]
        return emit({"ok": True, "action": "link_types", "source": source["name"], "types": slim})

    if not args.inward or not args.outward:
        return fail("MISSING_ARGUMENT", "建立关联必须指定 --inward <KEY> 和 --outward <KEY>", exit_code=2)
    link_type = args.type or "Relates"
    inward_key = client.normalize_issue_key(args.inward)
    outward_key = client.normalize_issue_key(args.outward)

    if not args.preview:
        return fail("PREVIEW_REQUIRED", "关联单据必须先 --preview 生成预览，再由人确认后 apply",
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行", exit_code=2)

    plan = planmod.create_plan(PLANS_DIR, {
        "action": "link",
        "source": source["name"],
        "base_url": source.get("base_url"),
        "inward": inward_key,
        "outward": outward_key,
        "type": link_type,
    })
    return emit({"ok": True, "stage": "preview",
                 "plan_id": plan["plan_id"],
                 "expires_at": plan["expires_at"],
                 "action": "link",
                 "target": "%s -> %s" % (inward_key, outward_key),
                 "changes": [{"field": "link_type", "to": link_type}],
                 "hint": "确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"]})


def cmd_worklog(args, config):
    source = client.pick_source(config, args.source)
    key = client.normalize_issue_key(args.key)
    if args.list:
        resp = client.request(source, "GET", "/rest/api/2/issue/%s/worklog" % client.url_quote(key))
        worklogs = resp.get("worklogs") or []
        slim = [{
            "id": w.get("id"),
            "author": (w.get("author") or {}).get("displayName") or (w.get("author") or {}).get("name"),
            "timeSpent": w.get("timeSpent"),
            "timeSpentSeconds": w.get("timeSpentSeconds"),
            "started": w.get("started"),
            "comment": w.get("comment"),
        } for w in worklogs]
        return emit({"ok": True, "action": "worklog_list", "source": source["name"], "key": key,
                     "total": resp.get("total", len(slim)), "worklogs": slim})

    if not args.time:
        return fail("MISSING_ARGUMENT", "登记工时必须提供 --time（如 '2h 30m'）", exit_code=2)
    if not args.preview:
        return fail("PREVIEW_REQUIRED", "登记工时必须先 --preview 生成预览，再由人确认后 apply",
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行", exit_code=2)

    payload = {"timeSpent": args.time}
    if args.comment:
        payload["comment"] = args.comment
    if args.started:
        payload["started"] = args.started

    plan = planmod.create_plan(PLANS_DIR, {
        "action": "worklog",
        "source": source["name"],
        "base_url": source.get("base_url"),
        "key": key,
        "payload": payload,
    })
    changes = [{"field": "timeSpent", "to": args.time}]
    if args.started:
        changes.append({"field": "started", "to": args.started})
    if args.comment:
        changes.append({"field": "comment", "to": args.comment})
    return emit({"ok": True, "stage": "preview",
                 "plan_id": plan["plan_id"],
                 "expires_at": plan["expires_at"],
                 "action": "worklog",
                 "target": key,
                 "changes": changes,
                 "hint": "确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"]})


def cmd_attach(args, config):
    source = client.pick_source(config, args.source)
    key = client.normalize_issue_key(args.key)
    if args.list:
        resp = client.request(source, "GET", "/rest/api/2/issue/%s?fields=attachment" % client.url_quote(key))
        attachments = (resp.get("fields") or {}).get("attachment") or []
        slim = [{
            "id": a.get("id"),
            "filename": a.get("filename"),
            "size": a.get("size"),
            "created": a.get("created"),
            "author": (a.get("author") or {}).get("displayName") or (a.get("author") or {}).get("name"),
            "content": a.get("content"),
        } for a in attachments]
        return emit({"ok": True, "action": "attach_list", "source": source["name"], "key": key, "attachments": slim})

    if not args.file:
        return fail("MISSING_ARGUMENT", "请指定 --file <文件路径> 或 --list", exit_code=2)
    file_path = os.path.abspath(args.file)
    if not os.path.isfile(file_path):
        return fail("CONFIG_ERROR", "文件不存在: %s" % file_path, exit_code=2)

    if not args.preview:
        return fail("PREVIEW_REQUIRED", "上传附件必须先 --preview 生成预览，再由人确认后 apply",
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行", exit_code=2)

    try:
        with open(file_path, "rb") as f:
            file_sha256 = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        return fail("CONFIG_ERROR", "无法读取附件文件: %s" % e, exit_code=2)

    plan = planmod.create_plan(PLANS_DIR, {
        "action": "attach",
        "source": source["name"],
        "base_url": source.get("base_url"),
        "key": key,
        "file_path": file_path,
        "filename": os.path.basename(file_path),
        "file_size": os.path.getsize(file_path),
        "sha256": file_sha256,
    })
    return emit({"ok": True, "stage": "preview",
                 "plan_id": plan["plan_id"],
                 "expires_at": plan["expires_at"],
                 "action": "attach",
                 "target": key,
                 "changes": [{"field": "file", "to": "%s (%d 字节)" % (os.path.basename(file_path), os.path.getsize(file_path))}],
                 "hint": "确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"]})


def cmd_delete(args, config):
    source = client.pick_source(config, args.source)
    key = client.normalize_issue_key(args.key)
    if not args.preview:
        return fail("PREVIEW_REQUIRED", "删除单据属于高危操作，必须先 --preview 生成预览，再由人确认后 apply",
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行", exit_code=2)

    plan = planmod.create_plan(PLANS_DIR, {
        "action": "delete",
        "source": source["name"],
        "base_url": source.get("base_url"),
        "key": key,
    })
    return emit({"ok": True, "stage": "preview",
                 "plan_id": plan["plan_id"],
                 "expires_at": plan["expires_at"],
                 "action": "delete",
                 "target": key,
                 "changes": [{"field": "delete_issue", "to": key}],
                 "hint": "危险操作：确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"]})


def cmd_api(args, config):
    """通用 REST 接口调用逃生通道：覆盖 Jira 全量内置及插件 REST API。"""
    source = client.pick_source(config, args.source)
    method = (args.method or "GET").upper()
    path = args.path
    if not path.startswith("/"):
        path = "/" + path

    body = None
    if args.data:
        try:
            body = json.loads(args.data)
        except ValueError:
            body = args.data
    elif args.data_file:
        try:
            with open(args.data_file, "r", encoding="utf-8") as f:
                content = f.read()
            try:
                body = json.loads(content)
            except ValueError:
                body = content
        except OSError as e:
            return fail("CONFIG_ERROR", "读取载荷文件失败: %s" % e, "检查 --data-file 路径", exit_code=2)

    # 读请求直接执行
    if method in ("GET", "HEAD"):
        resp = client.request(source, method, path)
        return emit({"ok": True, "action": "api", "source": source["name"],
                     "method": method, "path": path, "response": resp})

    # 写请求必须两阶段确认
    if not args.preview:
        return fail("PREVIEW_REQUIRED",
                    "通用接口写操作（%s）必须先 --preview 生成预览，再由人确认后 apply" % method,
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行", exit_code=2)

    plan = planmod.create_plan(PLANS_DIR, {
        "action": "api",
        "source": source["name"],
        "base_url": source.get("base_url"),
        "method": method,
        "path": path,
        "body": body,
    })
    preview_body = body
    if isinstance(preview_body, (dict, list)):
        preview_body = json.dumps(preview_body, ensure_ascii=False, indent=2)

    return emit({"ok": True, "stage": "preview",
                 "plan_id": plan["plan_id"],
                 "expires_at": plan["expires_at"],
                 "action": "api",
                 "target": "[%s] %s" % (method, path),
                 "changes": [{"field": "method", "to": method},
                             {"field": "path", "to": path},
                             {"field": "body", "to": preview_body}],
                 "hint": "确认无误后执行: jira_cli.py apply --plan-id %s" % plan["plan_id"]})




def cmd_update(args, config):
    """修改 issue 字段与状态：只产出预览计划，真正下笔仍走 apply --plan-id。"""
    # --preview 判定必须在 pick_source 之前：不带 --preview 时不做任何多余动作
    if not args.preview:
        return fail("PREVIEW_REQUIRED",
                    "修改必须先 --preview 生成预览，再由人确认后 apply",
                    "加 --preview 生成 plan，确认无误后用 apply --plan-id 执行",
                    exit_code=2)
    if not args.set_ and not args.description_file and not args.status:
        return fail("EMPTY_CHANGESET", "本次没有指定任何要修改的内容",
                    "用 --set 字段名=值 指定字段改动，或用 --status 指定目标状态",
                    exit_code=2)
    try:
        # 批量判据统一按「归一去重后的 key 条数 >= 2」，不按 --key 出现次数
        keys, dup_removed = update_fields.normalize_keys(args.key or [])
        is_batch = len(keys) >= 2
        if is_batch and args.description_file:
            raise update_fields.UpdateError(
                "BATCH_BODY_FIELD_FORBIDDEN",
                "描述是正文字段，一次改多条单时不允许统一覆盖",
                "描述请一条一条改；批量只支持截止日期、经办人、优先级、修复版本、标签",
                exit_code=2)
        if is_batch and not args.complete_set:
            raise update_fields.UpdateError(
                "BATCH_ASSERTION_REQUIRED",
                "本次要改 %d 条单，必须显式声明这份清单是完整集合" % len(keys),
                "确认上一步的查询结果没有被截断后，加 --complete-set 重新预览",
                exit_code=2)
        description = None
        if args.description_file:
            try:
                with open(args.description_file, "r", encoding="utf-8") as f:
                    description = f.read()
            except OSError as e:
                return fail("CONFIG_ERROR", "读取描述文件失败: %s" % e,
                            "检查 --description-file 路径", exit_code=2)
            if not description.strip():
                raise update_fields.UpdateError(
                    "FIELD_VALUE_INVALID", "描述文件内容为空",
                    "描述不支持通过本命令清空（防误删）；如确需清空可使用 api 接口或手动调整", exit_code=2)
            if args.description_format == "md":
                description = wiki.md_to_wiki(description)
        set_pairs = [_parse_field_kv(raw, "--set") for raw in args.set_ or []]
        source = client.pick_source(config, args.source)
        opts = {"keys": keys, "dup_removed": dup_removed, "set_pairs": set_pairs,
                "status": args.status, "description": description,
                "complete_set": bool(args.complete_set),
                "allow_closed": bool(args.allow_closed_transition),
                "config": config}
        out, exit_code = update_plan.build_preview(
            client, source, opts, PLANS_DIR, datetime.now().date())
    except update_fields.UpdateError as e:
        out = {"ok": False, "error_code": e.error_code, "error": e.error,
               "hint": e.hint}
        out.update(e.payload)          # candidates / blockers 等载荷展开到顶层
        return emit(out, e.exit_code)
    return emit(out, exit_code)


def _safe_audit(record, audit_errors=None):
    """安全落审计日志：写盘失败不打断业务主流程，记录到 audit_errors 回传。"""
    try:
        planmod.audit(AUDIT_LOG, record)
    except Exception as e:
        if audit_errors is not None:
            audit_errors.append("%s: %s" % (type(e).__name__, e))


def _apply_update(plan, config):
    """apply 的 update 分支：结构校验 → 写源准入 → 执行时间轴 → 报告。"""
    missing = [k for k in ("action", "source", "items") if plan.get(k) is None]
    if missing or not isinstance(plan.get("items"), list):
        reason = "update 计划结构不合法，缺少或非法字段: %s" % ", ".join(missing or ["items"])
        _safe_audit({"action": "apply", "plan_id": plan.get("plan_id"),
                     "result": "rejected", "reason": reason})
        return fail("PLAN_MALFORMED", reason,
                    "重新走 update --preview 生成新 plan", exit_code=1)
    try:
        # 判据取 plan 里记下的源名：按 args.source / default_source 判会开错源
        update_fields.check_write_source(config, plan.get("source"))
    except update_fields.UpdateError as e:
        _safe_audit({"action": "apply", "plan_id": plan.get("plan_id"),
                     "result": "rejected", "reason": e.error})
        return fail(e.error_code, e.error, e.hint, exit_code=e.exit_code)
    source = client.pick_source(config, plan.get("source"))
    if plan.get("base_url") and source.get("base_url") != plan["base_url"]:
        reason = "执行源地址与预览时不一致 (预览: %s, 当前配置: %s)" % (plan.get("base_url"), source.get("base_url"))
        _safe_audit({"action": "apply", "plan_id": plan.get("plan_id"),
                     "result": "rejected", "reason": reason})
        return fail("PLAN_REJECTED", reason, "配置已变更，请重新生成 preview 后再 apply")
    report = update_exec.execute(client, source, plan,
                                 lambda record: planmod.audit(AUDIT_LOG, record))
    # 整批跑完一律 ok/退出码 0，逐条成败只体现在报告里
    return emit({"ok": True, "stage": "applied", "action": "update",
                 "plan_id": plan["plan_id"],
                 "counts": report["counts"],
                 "has_failures": report["has_failures"],
                 "resume_keys": report["resume_keys"],
                 "items": report["items"],
                 "audit_errors": report.get("audit_errors", []),
                 "result_text": update_render.render_result(report)}, 0)


def cmd_apply(args, config):
    try:
        plan = planmod.consume_plan(PLANS_DIR, args.plan_id)
    except planmod.PlanRejected as e:
        _safe_audit({"action": "apply", "plan_id": args.plan_id,
                     "result": "rejected", "reason": str(e)})
        return fail("PLAN_REJECTED", str(e),
                    "重新走预览生成新 plan")

    action = plan.get("action")
    allowed_actions = ("create", "update", "comment", "assign", "link", "worklog", "attach", "delete", "api")
    if action not in allowed_actions:
        _safe_audit({"action": "apply", "plan_id": args.plan_id,
                     "result": "rejected",
                     "reason": "不支持的 plan 动作: %s" % action})
        return fail("PLAN_REJECTED", "不支持的 plan 动作: %s" % action,
                    "本期支持: %s" % " / ".join(allowed_actions))

    if action == "update":
        return _apply_update(plan, config)

    source = client.pick_source(config, plan.get("source"))
    if plan.get("base_url") and source.get("base_url") != plan["base_url"]:
        reason = "执行源地址与预览时不一致 (预览: %s, 当前配置: %s)" % (plan.get("base_url"), source.get("base_url"))
        _safe_audit({"action": "apply", "plan_id": args.plan_id,
                     "result": "rejected", "reason": reason})
        return fail("PLAN_REJECTED", reason, "配置已变更，请重新生成 preview 后再 apply")

    if action == "create":
        record = {"action": "create", "target": plan.get("project"),
                  "plan_id": plan["plan_id"],
                  "summary": (plan.get("fields") or {}).get("summary")}
        try:
            resp = client.request(source, "POST", "/rest/api/2/issue",
                                  body={"fields": plan["fields"]})
        except client.JiraError as e:
            record.update({"result": "failed", "error_code": e.error_code,
                            "error": e.error})
            _safe_audit(record)
            raise
        key = resp.get("key", "")
        record.update({"result": "success", "issue_key": key})
        audit_errors = []
        _safe_audit(record, audit_errors)
        res = {"ok": True, "stage": "applied", "action": "create",
               "plan_id": plan["plan_id"], "issue_key": key,
               "url": _browse_url(source, key)}
        if audit_errors:
            res["audit_errors"] = audit_errors
        return emit(res)

    if action == "comment":
        key = plan.get("key")
        if not key or "body" not in plan:
            return fail("PLAN_MALFORMED", "comment 计划缺少 key 或 body", exit_code=1)
        record = {"action": "comment", "target": key, "plan_id": plan["plan_id"]}
        try:
            resp = client.request(source, "POST", "/rest/api/2/issue/%s/comment" % client.url_quote(key),
                                  body={"body": plan["body"]})
        except client.JiraError as e:
            record.update({"result": "failed", "error_code": e.error_code, "error": e.error})
            _safe_audit(record)
            raise
        record.update({"result": "success", "comment_id": resp.get("id")})
        audit_errors = []
        _safe_audit(record, audit_errors)
        res = {"ok": True, "stage": "applied", "action": "comment",
               "plan_id": plan["plan_id"], "key": key, "comment_id": resp.get("id"),
               "url": _browse_url(source, key)}
        if audit_errors:
            res["audit_errors"] = audit_errors
        return emit(res)

    if action == "assign":
        key = plan.get("key")
        if not key:
            return fail("PLAN_MALFORMED", "assign 计划缺少 key", exit_code=1)
        record = {"action": "assign", "target": key, "assignee": plan.get("assignee"), "plan_id": plan["plan_id"]}
        try:
            client.request(source, "PUT", "/rest/api/2/issue/%s/assignee" % client.url_quote(key),
                           body={"name": plan.get("assignee")})
        except client.JiraError as e:
            record.update({"result": "failed", "error_code": e.error_code, "error": e.error})
            _safe_audit(record)
            raise
        record.update({"result": "success"})
        audit_errors = []
        _safe_audit(record, audit_errors)
        res = {"ok": True, "stage": "applied", "action": "assign",
               "plan_id": plan["plan_id"], "key": key, "assignee": plan.get("assignee"),
               "url": _browse_url(source, key)}
        if audit_errors:
            res["audit_errors"] = audit_errors
        return emit(res)

    if action == "link":
        if not plan.get("inward") or not plan.get("outward"):
            return fail("PLAN_MALFORMED", "link 计划缺少 inward 或 outward", exit_code=1)
        record = {"action": "link", "inward": plan["inward"], "outward": plan["outward"], "type": plan["type"], "plan_id": plan["plan_id"]}
        body = {
            "type": {"name": plan["type"]},
            "inwardIssue": {"key": plan["inward"]},
            "outwardIssue": {"key": plan["outward"]},
        }
        try:
            client.request(source, "POST", "/rest/api/2/issueLink", body=body)
        except client.JiraError as e:
            record.update({"result": "failed", "error_code": e.error_code, "error": e.error})
            _safe_audit(record)
            raise
        record.update({"result": "success"})
        audit_errors = []
        _safe_audit(record, audit_errors)
        res = {"ok": True, "stage": "applied", "action": "link",
               "plan_id": plan["plan_id"], "inward": plan["inward"], "outward": plan["outward"],
               "type": plan["type"]}
        if audit_errors:
            res["audit_errors"] = audit_errors
        return emit(res)

    if action == "worklog":
        key = plan.get("key")
        if not key or not plan.get("payload"):
            return fail("PLAN_MALFORMED", "worklog 计划缺少 key 或 payload", exit_code=1)
        record = {"action": "worklog", "target": key, "plan_id": plan["plan_id"]}
        try:
            resp = client.request(source, "POST", "/rest/api/2/issue/%s/worklog" % client.url_quote(key),
                                  body=plan["payload"])
        except client.JiraError as e:
            record.update({"result": "failed", "error_code": e.error_code, "error": e.error})
            _safe_audit(record)
            raise
        record.update({"result": "success", "worklog_id": resp.get("id")})
        audit_errors = []
        _safe_audit(record, audit_errors)
        res = {"ok": True, "stage": "applied", "action": "worklog",
               "plan_id": plan["plan_id"], "key": key, "worklog_id": resp.get("id"),
               "url": _browse_url(source, key)}
        if audit_errors:
            res["audit_errors"] = audit_errors
        return emit(res)

    if action == "attach":
        key = plan.get("key")
        file_path = plan.get("file_path")
        if not key or not file_path:
            return fail("PLAN_MALFORMED", "attach 计划缺少 key 或 file_path", exit_code=1)
        if not os.path.isfile(file_path):
            return fail("CONFIG_ERROR", "要上传的附件文件不存在: %s" % file_path, exit_code=2)
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
        except OSError as e:
            return fail("CONFIG_ERROR", "读取附件文件失败: %s" % e, exit_code=2)

        if plan.get("sha256"):
            curr_sha256 = hashlib.sha256(file_bytes).hexdigest()
            if curr_sha256 != plan["sha256"]:
                reason = "附件文件内容在预览后已被修改，拒绝上传"
                _safe_audit({"action": "apply", "plan_id": args.plan_id,
                             "result": "rejected", "reason": reason})
                return fail("FILE_CHANGED", reason, "请重新执行 attach --preview 生成新计划", exit_code=2)

        record = {"action": "attach", "target": key, "filename": plan.get("filename"), "plan_id": plan["plan_id"]}
        try:
            resp = client.upload_file(source, "/rest/api/2/issue/%s/attachments" % client.url_quote(key),
                                      file_path, file_bytes=file_bytes, filename=plan.get("filename"))
            if not isinstance(resp, list):
                raise client.JiraError("UNEXPECTED_RESPONSE", "上传附件响应不是预期的附件列表: %s" % str(resp)[:200],
                                       "检查 Jira 响应是否正确")
        except client.JiraError as e:
            record.update({"result": "failed", "error_code": e.error_code, "error": e.error})
            _safe_audit(record)
            raise
        record.update({"result": "success"})
        audit_errors = []
        _safe_audit(record, audit_errors)
        res = {"ok": True, "stage": "applied", "action": "attach",
               "plan_id": plan["plan_id"], "key": key, "result": resp,
               "url": _browse_url(source, key)}
        if audit_errors:
            res["audit_errors"] = audit_errors
        return emit(res)

    if action == "delete":
        key = plan.get("key")
        if not key:
            return fail("PLAN_MALFORMED", "delete 计划缺少 key", exit_code=1)
        record = {"action": "delete", "target": key, "plan_id": plan["plan_id"]}
        try:
            client.request(source, "DELETE", "/rest/api/2/issue/%s" % client.url_quote(key))
        except client.JiraError as e:
            record.update({"result": "failed", "error_code": e.error_code, "error": e.error})
            _safe_audit(record)
            raise
        record.update({"result": "success"})
        audit_errors = []
        _safe_audit(record, audit_errors)
        res = {"ok": True, "stage": "applied", "action": "delete",
               "plan_id": plan["plan_id"], "key": key}
        if audit_errors:
            res["audit_errors"] = audit_errors
        return emit(res)

    if action == "api":
        path = plan.get("path")
        method = plan.get("method", "GET")
        body = plan.get("body")
        if not path:
            return fail("PLAN_MALFORMED", "api 计划缺少 path", exit_code=1)
        record = {"action": "api", "target": "[%s] %s" % (method, path), "plan_id": plan["plan_id"]}
        try:
            resp = client.request(source, method, path, body=body)
        except client.JiraError as e:
            record.update({"result": "failed", "error_code": e.error_code, "error": e.error})
            _safe_audit(record)
            raise
        record.update({"result": "success"})
        audit_errors = []
        _safe_audit(record, audit_errors)
        res = {"ok": True, "stage": "applied", "action": "api",
               "plan_id": plan["plan_id"], "source": source["name"],
               "method": method, "path": path, "response": resp}
        if audit_errors:
            res["audit_errors"] = audit_errors
        return emit(res)


# ---------------------------------------------------------------- 入口

def build_parser():
    parser = argparse.ArgumentParser(
        prog="jira_cli.py", description="Jira 读写全功能接口命令行（两阶段安全预览门禁）")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="配置文件路径")
    parser.add_argument("--source", default=None, help="Jira 源名（缺省取 default_source）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="动态 JQL 查询")
    p.add_argument("--jql", required=True)
    p.add_argument("--fields", default=None, help="追加字段，逗号分隔")
    p.add_argument("--limit", type=int, default=None, help="返回条数上限")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("get", help="单条 issue 详情")
    p.add_argument("key")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("count-by", help="分组计数")
    p.add_argument("--jql", required=True)
    p.add_argument("--group-by", required=True)
    p.set_defaults(func=cmd_count_by)

    p = sub.add_parser("transitions", help="查 issue 可用流转及必填字段")
    p.add_argument("key")
    p.set_defaults(func=cmd_transitions)

    p = sub.add_parser("createmeta", help="查创建 issue 的必填字段或项目可用类型")
    p.add_argument("--project", required=True, help="项目 KEY")
    p.add_argument("--type", default=None, help="issue 类型名，不传则列出该项目下全部可用类型")
    p.set_defaults(func=cmd_createmeta)

    p = sub.add_parser("fields", help="列字段及 customfield id")
    p.add_argument("--grep", default=None)
    p.add_argument("--full", action="store_true")
    p.set_defaults(func=cmd_fields)

    p = sub.add_parser("whoami", help="连通性与认证自检")
    p.set_defaults(func=cmd_whoami)

    p = sub.add_parser("serverinfo", help="Jira 版本自检")
    p.set_defaults(func=cmd_serverinfo)

    p = sub.add_parser("watch", help="增量监控：只返回新增 issue")
    p.add_argument("--jql", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--peek", action="store_true", help="只看不标记已见")
    p.add_argument("--reset", action="store_true", help="重置该监控的状态")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("create", help="创建单个 issue 或子任务（必须 --preview）")
    p.add_argument("--project", default=None, help="项目 key（如 TRS；若提供 --parent 可缺省）")
    p.add_argument("--type", default=None, help="issue 类型名（如 任务、缺陷；若提供 --parent 缺省为 子任务）")
    p.add_argument("--parent", default=None, help="父任务 key（创建子任务时指定，如 XMKFB-12099）")
    p.add_argument("--summary", required=True)
    p.add_argument("--description-file", default=None)
    p.add_argument("--description-format", choices=["md", "wiki"], default="md")
    p.add_argument("--field", action="append", default=None, help="k=v 形式，可重复")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("comment", help="查看或添加评论（添加必须 --preview）")
    p.add_argument("--key", required=True, help="issue key")
    p.add_argument("--list", action="store_true", help="列出已有评论")
    p.add_argument("--body", default=None, help="评论正文")
    p.add_argument("--body-file", default=None, help="评论正文文件路径")
    p.add_argument("--body-format", choices=["md", "wiki"], default="md")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_comment)

    p = sub.add_parser("assign", help="指派经办人（必须 --preview）")
    p.add_argument("--key", required=True, help="issue key")
    p.add_argument("--to", default=None, help="目标经办人用户名")
    p.add_argument("--to-me", action="store_true", help="指派给当前账号")
    p.add_argument("--unassign", action="store_true", help="设置为未分配")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_assign)

    p = sub.add_parser("link", help="关联单据（创建必须 --preview）")
    p.add_argument("--inward", default=None, help="主动关联方 issue key")
    p.add_argument("--outward", default=None, help="被动关联方 issue key")
    p.add_argument("--type", default="Relates", help="关联类型（默认 Relates）")
    p.add_argument("--list-types", action="store_true", help="列出可用关联类型")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_link)

    p = sub.add_parser("worklog", help="工时登记（登记必须 --preview）")
    p.add_argument("--key", required=True, help="issue key")
    p.add_argument("--list", action="store_true", help="列出工时记录")
    p.add_argument("--time", default=None, help="耗费时间，如 2h 30m, 1d")
    p.add_argument("--comment", default=None, help="工时说明")
    p.add_argument("--started", default=None, help="开始时间")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_worklog)

    p = sub.add_parser("attach", help="附件上传或查看（上传必须 --preview）")
    p.add_argument("--key", required=True, help="issue key")
    p.add_argument("--list", action="store_true", help="列出附件")
    p.add_argument("--file", default=None, help="上传本地文件路径")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_attach)

    p = sub.add_parser("delete", help="删除单据（必须 --preview）")
    p.add_argument("--key", required=True, help="issue key")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("api", help="通用 REST 接口逃生通道（读直出，写必须 --preview）")
    p.add_argument("--path", required=True, help="接口路径，例如 /rest/api/2/issue/KEY/watchers")
    p.add_argument("--method", choices=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"], default="GET", help="HTTP 方法，默认 GET")
    p.add_argument("--data", default=None, help="JSON 请求体字符串")
    p.add_argument("--data-file", default=None, help="JSON 请求体文件路径")
    p.add_argument("--preview", action="store_true", help="写操作必须带 --preview 生成 plan")
    p.set_defaults(func=cmd_api)

    p = sub.add_parser("update", help="修改 issue 字段与状态（必须 --preview）")
    p.add_argument("--key", action="append", required=True, help="issue key，可重复")
    p.add_argument("--set", action="append", dest="set_", default=None, help="k=v 形式，可重复")
    p.add_argument("--status", default=None, help="目标状态名")
    p.add_argument("--description-file", default=None)
    p.add_argument("--description-format", choices=["md", "wiki"], default="md")
    p.add_argument("--complete-set", action="store_true", help="声明本清单为完整集合")
    p.add_argument("--allow-closed-transition", action="store_true")
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("apply", help="执行已预览的变更")
    p.add_argument("--plan-id", required=True)
    p.set_defaults(func=cmd_apply)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        config = client.load_config(args.config)
        return args.func(args, config)
    except client.JiraError as e:
        exit_code = 2 if e.error_code == "CONFIG_ERROR" else 1
        return fail(e.error_code, e.error, e.hint, exit_code=exit_code)
    except SystemExit:
        raise
    except BaseException as e:  # catch-all：绝不让裸栈打到 stdout
        return fail("INTERNAL_ERROR", "未预期异常: %s: %s" % (type(e).__name__, e),
                    "把这条输出原样反馈给维护者")


if __name__ == "__main__":
    sys.exit(main())
