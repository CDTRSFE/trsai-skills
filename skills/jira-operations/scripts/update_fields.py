# -*- coding: utf-8 -*-
"""update 能力的值域解析层。

职责边界（实现契约 §2 §3）：
    - 定义 update 全链路共用的结构化异常 `UpdateError` 与模块级常量；
    - 字段白名单 `FIELD_SPECS` 与 `--set` 的本地强校验（零网络）；
    - 日期闭集词表解析（纯函数，基准日显式传入）；
    - 抢改复核的逐字段比对口径；
    - 名称解析（经办人 / 优先级 / 修复版本，唯一需要联网的部分）；
    - 写源准入（零网络）与 PUT 载荷构造。

不做的事：不组装预览、不落盘、不渲染文案、不发起写请求。
"""

import calendar
import re
from datetime import date, timedelta


# ---------------------------------------------------------------- 异常

class UpdateError(Exception):
    """update 专用结构化错误。

    exit_code 由抛出方定死，不靠 main 推断；payload 用于附带 candidates /
    blockers 等结构化载荷，emit 时展开到顶层。
    """

    def __init__(self, error_code, error, hint="", exit_code=2, payload=None):
        super(UpdateError, self).__init__(error)
        self.error_code = error_code
        self.error = error
        self.hint = hint
        self.exit_code = exit_code
        self.payload = payload or {}


# ---------------------------------------------------------------- 模块级常量

WRITE_ALLOWED_SOURCES = {"Jira1", "Jira2"}   # 允许对配置的双源执行写操作
BATCH_LIMIT = 50                     # 去重后条数上限
TTL_SINGLE_SECONDS = 300
TTL_BATCH_SECONDS = 900
MAX_HOPS = 2                         # 设计点 5 跳数上限
CATEGORY_RANK = {"new": 0, "indeterminate": 1, "done": 2}
TERMINAL_KEYWORDS = ("取消", "拒绝", "作废", "驳回", "关闭", "无效", "重复")
AUDIT_TRUNCATE_LIMIT = 2000          # 只对 summary/description 之外的字段生效
ISSUE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")

# 2026-08-12 实测回填：Jira2 完成类状态的显示名就是「完成」（statusCategory=done，
# 由 search / transitions 实测确认），口语「完成」原样透传、不再映射为「已完成」。
# 映射机制本身保留，将来接入显示名不同的源时按该源实测值填本表。
STATUS_ALIASES = {}

# 写源准入被拒时的固定 hint
WRITE_SOURCE_HINT = (
    "请在配置中确认源名，当前写能力允许在配置的 Jira1 与 Jira2 上执行"
)


# ---------------------------------------------------------------- 字段白名单

FIELD_SPECS = {
    "duedate":     {"cn": "截止日期", "type": str,  "clearable": "null", "batch": True,  "resolve": "date"},
    "assignee":    {"cn": "经办人",   "type": str,  "clearable": "null", "batch": True,  "resolve": "user"},
    "priority":    {"cn": "优先级",   "type": str,  "clearable": None,   "batch": True,  "resolve": "priority"},
    "fixVersions": {"cn": "修复版本", "type": list, "clearable": "empty", "batch": True, "resolve": "version"},
    "labels":      {"cn": "标签",     "type": list, "clearable": "empty", "batch": True, "resolve": "labels"},
    "summary":     {"cn": "标题",     "type": str,  "clearable": None,   "batch": False, "resolve": "raw"},
    "description": {"cn": "描述",     "type": str,  "clearable": None,   "batch": False, "resolve": "raw"},
}

# 中文名 → 英文字段名反查表。**只用于 hint 增强，不放宽拒绝**。
FIELD_CN_TO_NAME = {spec["cn"]: name for name, spec in FIELD_SPECS.items()}

# 各字段「人类可读入参形态」的提示语，用于用户直接塞 REST 载荷时的纠偏
FIELD_VALUE_HINTS = {
    "duedate": "截止日期请填 明天 或 2026-08-11 这类人类可读的值，不要填 REST 载荷",
    "assignee": "经办人请填人名或账号，不要填 REST 载荷",
    "priority": "优先级请填名称（如 高），不要填 REST 载荷",
    "fixVersions": '修复版本请填名称数组（如 ["v1.2.0"]），不要填 REST 载荷',
    "labels": '标签请填字符串数组（如 ["线上问题"]），不要填 REST 载荷',
    "summary": "标题请填一段文本，不要填 REST 载荷",
    "description": "描述只能走 --description-file",
}

# 类型名的中文说明，拼错误文案用
_TYPE_CN = {str: "字符串", list: "字符串数组"}


# ---------------------------------------------------------------- key 处理

def normalize_keys(raw_keys):
    """归一化 → 正则校验 → 按首次出现顺序去重 → 判上限。

    返回 (keys, dup_removed)。顺序不可调换：先归一化（strip + upper）再正则，
    否则小写 key 在 get 下能查、在 update 下被拒；归一化先于去重还能顺带消除
    大小写造成的重复计数。
    """
    import client  # 延迟导入，避免与 jira_cli 的导入顺序耦合

    normalized = []
    for raw in raw_keys or []:
        key = client.normalize_issue_key(raw)
        if not ISSUE_KEY_PATTERN.match(key):
            raise UpdateError(
                "INVALID_ISSUE_KEY",
                "issue key 格式非法: %s" % raw,
                "issue key 形如 XMKFB-123（项目前缀全大写 + 短横线 + 数字）",
                exit_code=2)
        normalized.append(key)

    keys = []
    for key in normalized:
        if key not in keys:
            keys.append(key)
    dup_removed = len(normalized) - len(keys)

    if len(keys) > BATCH_LIMIT:
        raise UpdateError(
            "BATCH_LIMIT_EXCEEDED",
            "单次最多修改 %d 条，本次去重后有 %d 条" % (BATCH_LIMIT, len(keys)),
            "先把筛选条件收窄",
            exit_code=2)
    return keys, dup_removed


# ---------------------------------------------------------------- --set 解析

def parse_set_args(raw_pairs, is_batch):
    """校验并收拢 `--set` 键值对，返回 {字段名: 解析后的原始值}（尚未转成 REST 载荷）。

    raw_pairs 为 jira_cli._parse_field_kv 解析后的 [(key, value), ...]，
    其中 value 已经过 json.loads（失败则保持原字符串）。

    校验顺序严格按契约 §3.3 的 12 步执行：先本地、零网络开销，
    任何一步不过即抛，全部 exit_code=2。
    """
    parsed = {}
    for raw_key, value in raw_pairs or []:
        name = (raw_key or "").strip()

        # 1. 同一字段出现两次 —— 不做「后者覆盖」的静默处理
        if name in parsed:
            raise UpdateError(
                "FIELD_VALUE_INVALID",
                "字段 %s 在本次 --set 里出现了两次" % name,
                "同一个字段只写一次；确实要改成哪个值请自己定，工具不替你选",
                exit_code=2)

        # 2. 状态不走 --set
        if name in ("status", "状态"):
            raise UpdateError(
                "FIELD_NOT_ALLOWED",
                "状态不允许通过 --set 修改: %s" % name,
                "推状态请用 --status，例如 --status 完成",
                exit_code=2)

        # 3. 中文名命中 —— 仍然拒绝，只做提示增强
        if name in FIELD_CN_TO_NAME:
            raise UpdateError(
                "FIELD_NOT_ALLOWED",
                "--set 的键必须是 Jira 英文字段名，不接受中文名: %s" % name,
                "你可能想用 --set %s=" % FIELD_CN_TO_NAME[name],
                exit_code=2)

        # 4. 白名单检查（支持标准字段与 customfield_*）
        if name not in FIELD_SPECS:
            if name.startswith("customfield_"):
                spec = {"cn": name, "type": type(value) if value is not None else str, "clearable": "null", "batch": True, "resolve": "raw"}
            else:
                raise UpdateError(
                    "FIELD_NOT_ALLOWED",
                    "字段 %s 不在可修改白名单内" % name,
                    "本期可改字段：%s，以及 customfield_* 自定义字段" % "、".join(sorted(FIELD_SPECS)),
                    exit_code=2)
        else:
            spec = FIELD_SPECS[name]

        # 5. 描述只能走 --description-file
        if name == "description":
            raise UpdateError(
                "FIELD_NOT_ALLOWED",
                "描述不允许通过 --set 修改",
                "描述只能走 --description-file",
                exit_code=2)

        # 6. 直接塞 REST 载荷（dict、或元素含 dict 的 list）一律拒绝
        if isinstance(value, dict) or (
                isinstance(value, list) and any(isinstance(x, dict) for x in value)):
            raise UpdateError(
                "FIELD_VALUE_INVALID",
                "字段 %s 的值看起来是 REST 载荷，不是人类可读的值" % name,
                FIELD_VALUE_HINTS.get(name, "请填人类可读的值，不要填 REST 载荷"),
                exit_code=2)

        # 7. null 清空语义
        if value is None:
            if spec["clearable"] != "null":
                raise UpdateError(
                    "FIELD_VALUE_INVALID",
                    "字段 %s（%s）不支持清空" % (name, spec["cn"]),
                    "该字段不支持清空；如确需调整可通过 api 接口或手动操作",
                    exit_code=2)
        # 8. 空数组清空语义
        elif isinstance(value, list) and len(value) == 0:
            if spec["clearable"] != "empty":
                raise UpdateError(
                    "FIELD_VALUE_INVALID",
                    "字段 %s（%s）不支持清空" % (name, spec["cn"]),
                    "该字段不支持清空；如确需调整可通过 api 接口或手动操作",
                    exit_code=2)
        else:
            # 9. 类型强校验 —— json.loads 会把 --set summary=2026 变成 int 2026，必须挡住
            if not isinstance(value, spec["type"]):
                raise UpdateError(
                    "FIELD_VALUE_INVALID",
                    "字段 %s（%s）需要%s，实际给的是 %r"
                    % (name, spec["cn"], _TYPE_CN.get(spec["type"], "合法值"), value),
                    FIELD_VALUE_HINTS.get(name, "请按该字段要求的形态填值"),
                    exit_code=2)

            # 10. list 型元素必须全是 str
            if spec["type"] is list:
                for item in value:
                    if not isinstance(item, str):
                        raise UpdateError(
                            "FIELD_VALUE_INVALID",
                            "字段 %s（%s）的数组元素必须都是字符串，实际含 %r"
                            % (name, spec["cn"], item),
                            FIELD_VALUE_HINTS.get(name, "请按该字段要求的形态填值"),
                            exit_code=2)

            # 11. labels 元素不得含空格
            if name == "labels":
                for item in value:
                    if any(ch.isspace() for ch in item):
                        raise UpdateError(
                            "FIELD_VALUE_INVALID",
                            "标签不能含空格: %r" % item,
                            "Jira 标签是单个词，多个词请拆成多个标签或用短横线连接",
                            exit_code=2)

        # 12. 正文字段禁批量（判据是去重后条数 ≥ 2）
        if is_batch and spec["batch"] is False:
            raise UpdateError(
                "BATCH_BODY_FIELD_FORBIDDEN",
                "字段 %s（%s）只能单条修改，不允许批量" % (name, spec["cn"]),
                "把 %s 拆成单条 --key 的命令分别执行" % spec["cn"],
                exit_code=2)

        parsed[name] = value
    return parsed


# ---------------------------------------------------------------- 日期解析

_WEEKDAY_CN = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

_RE_WEEK = re.compile(r"^(本周|下周)([一二三四五六日天])$")
_RE_N_DAYS = re.compile(r"^(\d+)天后$")
_RE_ABSOLUTE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_DATE_HINT = "改用绝对日期 YYYY-MM-DD"


def _bad_date(expr):
    return UpdateError(
        "INVALID_DATE_EXPRESSION",
        "看不懂的日期表达式: %s" % expr,
        _DATE_HINT,
        exit_code=2)


def resolve_date(expr, today):
    """把日期表达式换算成 "YYYY-MM-DD"。

    expr: str；today: datetime.date（**必须由调用方显式传入**，
    函数内部绝不调用 date.today() —— 这是单测不 mock 系统时钟的硬前提）。

    闭集词表（仅此，其余一律拒绝）：
        今天 / 明天 / 后天 / 本周X / 下周X / 月底 / N天后 / YYYY-MM-DD
    口径：周首为周一；本周X 早于今天直接报错（绝不静默顺延）；
    精确到天、不含时刻、不跳周末不跳节假日。
    """
    if not isinstance(expr, str):
        raise _bad_date(expr)
    text = expr.strip()
    if not text:
        raise _bad_date(expr)

    if text == "今天":
        return _fmt(today)
    if text == "明天":
        return _fmt(today + timedelta(days=1))
    if text == "后天":
        return _fmt(today + timedelta(days=2))
    if text == "月底":
        last = calendar.monthrange(today.year, today.month)[1]
        return _fmt(date(today.year, today.month, last))

    m = _RE_WEEK.match(text)
    if m:
        prefix, cn = m.group(1), m.group(2)
        monday = today - timedelta(days=today.weekday())
        target = monday + timedelta(days=_WEEKDAY_CN[cn])
        if prefix == "下周":
            target = target + timedelta(days=7)
        elif target < today:
            raise UpdateError(
                "INVALID_DATE_EXPRESSION",
                "「%s」在本自然周里已经过去了（今天是 %s）" % (text, _fmt(today)),
                "改用「下周%s」或绝对日期 YYYY-MM-DD" % cn,
                exit_code=2)
        return _fmt(target)

    m = _RE_N_DAYS.match(text)
    if m:
        days = int(m.group(1))
        if days <= 0:
            raise _bad_date(expr)
        try:
            return _fmt(today + timedelta(days=days))
        except (OverflowError, ValueError):
            raise _bad_date(expr)

    if _RE_ABSOLUTE.match(text):
        year, month, day = (int(p) for p in text.split("-"))
        try:
            return _fmt(date(year, month, day))
        except ValueError:
            raise _bad_date(expr)

    raise _bad_date(expr)


def _fmt(value):
    return value.strftime("%Y-%m-%d")


def format_date_display(date_str):
    """ "2026-08-11" → "2026-08-11（周二）"；周六周日 → "2026-08-15（周六·周末）"。"""
    if not date_str:
        return date_str
    try:
        year, month, day = (int(p) for p in str(date_str).split("-"))
        value = date(year, month, day)
    except (ValueError, TypeError):
        return date_str
    weekday = value.weekday()
    name = _WEEKDAY_NAMES[weekday]
    if weekday >= 5:
        return "%s（%s·周末）" % (date_str, name)
    return "%s（%s）" % (date_str, name)


# ---------------------------------------------------------------- 值比对

def _sub(value, key):
    """取 dict 的子键；非 dict 原样返回（None 保持 None）。"""
    if isinstance(value, dict):
        return value.get(key)
    return value


def _text(value):
    return "" if value is None else str(value).strip()


def _name_set(value):
    """集合型字段归一成名字集合：元素是 dict 取 name，否则取字符串本身。"""
    out = set()
    for item in value or []:
        out.add(item.get("name") if isinstance(item, dict) else item)
    return out


def compare_field(field, snapshot_value, current_value):
    """抢改复核的逐字段比对（设计点 7 第 1 步）。返回 True 表示「未被他人改动」。

    口径写死，不做模糊匹配：日期归一化后字符串相等（None 与 "" 等价）、
    经办人比 name、优先级比 id、标签与修复版本按集合比（忽略顺序）、
    标题与描述按原文相等、状态比 status.id。
    """
    if field == "duedate":
        return _text(snapshot_value) == _text(current_value)
    if field == "assignee":
        return _text(_sub(snapshot_value, "name")) == _text(_sub(current_value, "name"))
    if field == "priority":
        return _text(_sub(snapshot_value, "id")) == _text(_sub(current_value, "id"))
    if field == "labels":
        return set(snapshot_value or []) == set(current_value or [])
    if field == "fixVersions":
        return _name_set(snapshot_value) == _name_set(current_value)
    if field in ("summary", "description"):
        a = "" if snapshot_value is None else snapshot_value
        b = "" if current_value is None else current_value
        return a == b
    if field == "status":
        return _text(_sub(snapshot_value, "id")) == _text(_sub(current_value, "id"))
    return snapshot_value == current_value


# ---------------------------------------------------------------- 名称解析（联网）

def _no_match(field, keyword):
    return UpdateError(
        "FIELD_VALUE_NO_MATCH",
        "%s「%s」在 Jira 里没有匹配项" % (FIELD_SPECS[field]["cn"], keyword),
        "换一个更准确的值重试；不确定就先用只读命令查一下有哪些可选值",
        exit_code=1,
        payload={"field": field, "candidates": []})


def _ambiguous(field, keyword, candidates):
    shown = candidates[:10]
    return UpdateError(
        "FIELD_VALUE_AMBIGUOUS",
        "%s「%s」匹配到多个结果，无法确定用哪一个"
        % (FIELD_SPECS[field]["cn"], keyword),
        "从候选里挑一个更精确的值重新发起预览",
        exit_code=1,
        payload={"field": field, "candidates": shown,
                 "has_more": len(candidates) > len(shown)})


def resolve_user(client_mod, source, keyword):
    """经办人解析：GET /rest/api/2/user/search?username=<encoded>&maxResults=11。

    Jira Server 8.5 用 username 参数（Cloud 的 query 在 Server 上直接 400）；
    取 11 条是为了判断「候选是否超过 10 个」。
    先取完全等于（name / displayName / emailAddress 任一完全命中），
    无完全命中则退回接口本身给出的包含匹配结果。
    """
    path = ("/rest/api/2/user/search?username=%s&maxResults=11"
            % client_mod.url_quote(keyword))
    resp = client_mod.request(source, "GET", path)
    users = resp if isinstance(resp, list) else []

    exact = [u for u in users
             if keyword in (u.get("name"), u.get("displayName"), u.get("emailAddress"))]
    pool = exact or users

    if not pool:
        raise _no_match("assignee", keyword)
    if len(pool) > 1:
        raise _ambiguous("assignee", keyword,
                         [{"display": u.get("displayName") or u.get("name"),
                           "id": u.get("name")} for u in pool])
    hit = pool[0]
    return {"name": hit.get("name"), "displayName": hit.get("displayName")}


def resolve_priority(client_mod, source, name):
    """优先级解析：GET /rest/api/2/priority，按 name 完全匹配，取到 id 后用 id 写入。"""
    resp = client_mod.request(source, "GET", "/rest/api/2/priority")
    items = resp if isinstance(resp, list) else []
    hits = [p for p in items if p.get("name") == name]

    if not hits:
        raise _no_match("priority", name)
    if len(hits) > 1:
        raise _ambiguous("priority", name,
                         [{"display": p.get("name"), "id": p.get("id")} for p in hits])
    return {"id": hits[0].get("id"), "name": hits[0].get("name")}


def resolve_versions(client_mod, source, project_key, names):
    """修复版本解析：GET /rest/api/2/project/{projectKey}/versions，逐个按 name 完全匹配。

    返回 [{"id":..., "name":...}, ...]，保持传入顺序；任一项 0 命中 / 多命中即抛。
    跨项目已在预览的本地校验阶段被拒，此处只会面对单一项目。
    """
    path = "/rest/api/2/project/%s/versions" % client_mod.url_quote(project_key)
    resp = client_mod.request(source, "GET", path)
    items = resp if isinstance(resp, list) else []

    resolved = []
    for name in names or []:
        hits = [v for v in items if v.get("name") == name]
        if not hits:
            raise _no_match("fixVersions", name)
        if len(hits) > 1:
            raise _ambiguous("fixVersions", name,
                             [{"display": v.get("name"), "id": v.get("id")} for v in hits])
        resolved.append({"id": hits[0].get("id"), "name": hits[0].get("name")})
    return resolved


# ---------------------------------------------------------------- 写源准入

def check_write_source(config, source_name):
    """写源准入（设计点 10）。零网络，必须在任何联网请求之前调用。

    判据是显式常量 WRITE_ALLOWED_SOURCES，不借用 default_source 的语义
    —— 决策 D5 已拍板「默认源指向非主用源」，按 default_source 判会把写能力
    精确地开到不该写的那个源上。

    边界：config["sources"] 恰好 1 个且未显式指定源时，按该唯一源名判定
    （对齐 client.pick_source 在这种配置下返回 sources[0] 的行为）。
    """
    sources = (config or {}).get("sources") or []
    if source_name is None and len(sources) == 1:
        source_name = sources[0].get("name")

    if source_name in WRITE_ALLOWED_SOURCES:
        return

    raise UpdateError(
        "WRITE_SOURCE_NOT_ALLOWED",
        "源 [%s] 不允许执行修改操作" % source_name,
        WRITE_SOURCE_HINT,
        exit_code=2)


# ---------------------------------------------------------------- 载荷构造

def build_payload(field, resolved_value):
    """把解析后的值转成 PUT /issue 的 fields 载荷值。

    duedate -> "2026-08-11" 或 None；assignee -> {"name": ...} 或 None；
    priority -> {"id": ...}；fixVersions -> [{"id": ...}, ...] 或 []；
    labels -> ["a", "b"] 或 []；summary / description -> str
    （description 的 wiki 转换由调用方在此之前完成）。
    """
    if field == "duedate":
        return resolved_value if resolved_value else None
    if field == "assignee":
        if resolved_value is None:
            return None
        return {"name": _sub(resolved_value, "name")}
    if field == "priority":
        return {"id": _sub(resolved_value, "id")}
    if field == "fixVersions":
        return [{"id": _sub(v, "id")} for v in (resolved_value or [])]
    if field == "labels":
        return list(resolved_value or [])
    return resolved_value
