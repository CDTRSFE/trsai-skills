# -*- coding: utf-8 -*-
"""update 预览侧单元测试（TDD 红灯先行）。

测试目标
    覆盖「Jira 更新能力」预览阶段的全部本地校验、日期解析、状态寻路、
    预览门禁、TTL 档位与预览文案模板，口径以实现契约
    `scratchpad/contract.md` 为唯一事实源（对应二次设计
    `project-docs/iterations/jira技能化/2026-08-10-二次设计.md` 的「单元测试」清单）。
    执行侧（apply/写请求/半成品/429）用例不在本文件，见 tests/test_update_apply.py。

依赖环境
    无需任何外部环境：不连真实 Jira、不读真实配置、不依赖系统时钟。
    全部 HTTP 走 `client.request` 打桩；日期一律显式传入固定 today 参数。

数据准备方式
    - 配置：setUp 里写一份临时 jira_config（源 Jira2 可写、源 Jira1 不可写）。
    - plan 落盘目录：tempfile.mkdtemp() + mock.patch.object(jira_cli, "PLANS_DIR", ...)。
    - Jira 响应：FakeJira 按 (method, path) 路由返回内存里预置的 issue / 流转 /
      项目状态 / 用户 / 优先级 / 版本数据，并记录每次调用以便断言「零网络」。
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import client
import jira_cli
import plan as planmod
import update_fields
import update_plan
import update_render

# ---------------------------------------------------------------- 公共夹具

CONFIG = {
    "default_source": "Jira2",
    "sources": [
        {"name": "Jira2", "base_url": "http://jira2.local",
         "username": "u", "password": "p"},
        {"name": "Jira1", "base_url": "http://jira1.local",
         "username": "u", "password": "p"},
        {"name": "Jira3", "base_url": "http://jira3.local",
         "username": "u", "password": "p"},
    ],
}

# 项目状态集：GET /rest/api/2/project/{key}/statuses 的原始形态（按 issuetype 分组）
PROJECT_STATUSES = [{
    "id": "10001", "name": "任务",
    "statuses": [
        {"id": "10000", "name": "待办", "statusCategory": {"key": "new"}},
        {"id": "3", "name": "进行中", "statusCategory": {"key": "indeterminate"}},
        {"id": "6", "name": "已完成", "statusCategory": {"key": "done"}},
    ],
}]


def run_cli(argv):
    """跑 main 并捕获 stdout，返回 (退出码, 解析后的 JSON)。沿用 tests/test_cli.py 的写法。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = jira_cli.main(argv)
    text = buf.getvalue().strip()
    return code, json.loads(text) if text else None


def make_issue(key, status_name="待办", status_id="10000", category="new",
               project="XMKFB", **fields):
    """造一条 search 返回形态的 issue。"""
    base = {
        "status": {"id": status_id, "name": status_name,
                   "statusCategory": {"key": category}},
        "issuetype": {"id": "10001", "name": "任务"},
        "project": {"key": project},
    }
    base.update(fields)
    return {"key": key, "fields": base}


def transition(tid, name, to_id, to_name, to_category, required=None):
    """造一条 GET transitions 的原始流转项。"""
    return {"id": tid, "name": name,
            "to": {"id": to_id, "name": to_name,
                   "statusCategory": {"key": to_category}},
            "fields": required or {}}


RESOLUTION_REQUIRED = {
    "resolution": {"required": True, "name": "解决结果",
                   "hasDefaultValue": True,
                   "defaultValue": {"id": "1", "name": "已解决"},
                   "allowedValues": [{"id": "1", "name": "已解决"},
                                     {"id": "2", "name": "未解决"}]},
}


class FakeJira(object):
    """按路径路由的 client.request 替身，同时记录调用序列。"""

    def __init__(self):
        self.calls = []
        self.issues = {}            # key -> issue dict
        self.transitions = {}       # key -> [原始流转项]
        self.project_statuses = PROJECT_STATUSES
        self.users = []
        self.priorities = []
        self.versions = []

    def add_issue(self, issue, transitions=None):
        self.issues[issue["key"]] = issue
        self.transitions[issue["key"]] = transitions or []
        return issue

    def request(self, source, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if method == "POST" and path.startswith("/rest/api/2/search"):
            jql = (body or {}).get("jql", "")
            hit = [i for k, i in self.issues.items() if k in jql]
            return {"issues": hit, "total": len(hit), "startAt": 0,
                    "maxResults": len(hit)}
        if method == "GET" and "/transitions" in path:
            key = path.split("/rest/api/2/issue/")[1].split("/")[0]
            return {"expand": "transitions", "transitions": self.transitions.get(key, [])}
        if method == "GET" and path.endswith("/statuses"):
            return self.project_statuses
        if method == "GET" and "/versions" in path:
            return self.versions
        if method == "GET" and path.startswith("/rest/api/2/user/search"):
            return self.users
        if method == "GET" and path.startswith("/rest/api/2/priority"):
            return self.priorities
        raise AssertionError("预览期不应出现的请求: %s %s" % (method, path))


class UpdateCaseBase(unittest.TestCase):
    """公共 setUp：临时配置 + 临时 plans 目录 + FakeJira。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.config_path = os.path.join(self.dir, "config.json")
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f)
        self.plans_dir = os.path.join(self.dir, "plans")
        self.audit_log = os.path.join(self.dir, "audit.log")
        self.jira = FakeJira()

    def run_update(self, argv):
        """带全套打桩跑 update 子命令，返回 (退出码, JSON, mock 对象)。"""
        with mock.patch.object(jira_cli, "PLANS_DIR", self.plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", self.audit_log), \
             mock.patch("client.request", side_effect=self.jira.request) as req:
            code, out = run_cli(["--config", self.config_path] + argv)
        return code, out, req

    def plan_files(self):
        if not os.path.isdir(self.plans_dir):
            return []
        return sorted(n for n in os.listdir(self.plans_dir) if n.endswith(".json"))

    def load_only_plan(self):
        files = self.plan_files()
        self.assertEqual(len(files), 1, "预览应恰好落盘 1 个 plan 文件")
        with open(os.path.join(self.plans_dir, files[0]), encoding="utf-8") as f:
            return json.load(f)


# ---------------------------------------------------------------- 参数与白名单

class UpdateArgsTest(UpdateCaseBase):
    """预览期本地校验：零网络、退出码 2。"""

    def test_不带preview直接拒绝(self):
        code, out, req = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "duedate=2026-12-31"])
        self.assertEqual(code, 2, "缺 --preview 必须返回退出码 2")
        self.assertEqual(out["error_code"], "PREVIEW_REQUIRED",
                         "修改必须先走预览")
        self.assertEqual(req.call_count, 0, "缺 --preview 时不得发起任何请求")

    def test_既无set也无status报EMPTY_CHANGESET(self):
        code, out, req = self.run_update(["update", "--key", "XMKFB-1", "--preview"])
        self.assertEqual(code, 2, "空变更集必须返回退出码 2")
        self.assertEqual(out["error_code"], "EMPTY_CHANGESET",
                         "既无 --set 也无 --status 应报空变更集")
        self.assertEqual(req.call_count, 0, "空变更集不得发起任何请求")

    def test_日期表达式非法时零网络被拒(self):
        """日期换算属本地校验阶段，必须发生在任何联网请求之前。

        回归用例：曾把日期解析放在批量读单之后，网络不通时先撞 NETWORK_ERROR
        （退出码 1），把「日期写错了」这个真正原因整个盖掉，用户只会去查网络。
        """
        for expr in ("下下周", "季度末", "尽快"):
            with self.subTest(expr=expr):
                code, out, req = self.run_update(
                    ["update", "--key", "XMKFB-1", "--set", "duedate=" + expr,
                     "--preview"])
                self.assertEqual(code, 2, "日期词表外必须返回退出码 2")
                self.assertEqual(out["error_code"], "INVALID_DATE_EXPRESSION",
                                 "日期词表外应报 INVALID_DATE_EXPRESSION")
                self.assertEqual(req.call_count, 0,
                                 "日期解析失败时不得发起任何请求（零网络开销）")

    def test_白名单外字段被拒(self):
        code, out, req = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "reporter=zhangsan", "--preview"])
        self.assertEqual(code, 2, "白名单外字段必须返回退出码 2")
        self.assertEqual(out["error_code"], "FIELD_NOT_ALLOWED",
                         "reporter 不在可改字段白名单内")
        self.assertEqual(req.call_count, 0, "本地校验阶段不得发起请求")

    def test_中文字段名被拒且hint给出英文名建议(self):
        code, out, req = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "截止日期=明天", "--preview"])
        self.assertEqual(code, 2, "中文字段名必须返回退出码 2")
        self.assertEqual(out["error_code"], "FIELD_NOT_ALLOWED",
                         "中文字段名不放宽为可用写法")
        self.assertIn("duedate", out["hint"],
                      "hint 必须给出对应的英文字段名建议 duedate")

    def test_set_status被拒并提示改用status选项(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "status=已完成", "--preview"])
        self.assertEqual(code, 2, "--set status= 必须返回退出码 2")
        self.assertEqual(out["error_code"], "FIELD_NOT_ALLOWED",
                         "状态不允许走 --set")
        self.assertIn("--status", out["hint"], "hint 必须提示改用 --status")

    def test_set_中文状态被拒并提示改用status选项(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "状态=已完成", "--preview"])
        self.assertEqual(code, 2, "--set 状态= 必须返回退出码 2")
        self.assertEqual(out["error_code"], "FIELD_NOT_ALLOWED",
                         "中文「状态」同样不允许走 --set")
        self.assertIn("--status", out["hint"], "hint 必须提示改用 --status")

    def test_set_summary_null被拒(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "summary=null", "--preview"])
        self.assertEqual(code, 2, "标题不可清空，必须返回退出码 2")
        self.assertEqual(out["error_code"], "FIELD_VALUE_INVALID",
                         "summary 的 clearable 为 None，不接受 null")

    def test_set_summary数字被拒(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "summary=2026", "--preview"])
        self.assertEqual(code, 2, "summary=2026 被 json 解析成 int，必须挡住")
        self.assertEqual(out["error_code"], "FIELD_VALUE_INVALID",
                         "类型与 FIELD_SPECS 声明不符应报值非法")

    def test_同一字段set两次被拒(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1",
             "--set", "duedate=2026-12-30", "--set", "duedate=2026-12-31",
             "--preview"])
        self.assertEqual(code, 2, "同字段重复赋值必须返回退出码 2")
        self.assertEqual(out["error_code"], "FIELD_VALUE_INVALID",
                         "同一字段出现两次不得静默按后者覆盖")

    def test_set值为dict被拒(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1",
             "--set", 'assignee={"name": "zhang.san"}', "--preview"])
        self.assertEqual(code, 2, "直接填 REST 载荷必须返回退出码 2")
        self.assertEqual(out["error_code"], "FIELD_VALUE_INVALID",
                         "值为 dict 应被拒绝")

    def test_set值为dict数组被拒(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1",
             "--set", 'fixVersions=[{"name": "v1.0"}]', "--preview"])
        self.assertEqual(code, 2, "元素含 dict 的数组必须返回退出码 2")
        self.assertEqual(out["error_code"], "FIELD_VALUE_INVALID",
                         "list 元素含 dict 应被拒绝")

    def test_非法issue_key被拒(self):
        code, out, req = self.run_update(
            ["update", "--key", "不是单号", "--set", "duedate=2026-12-31", "--preview"])
        self.assertEqual(code, 2, "非法 issue key 必须返回退出码 2")
        self.assertEqual(out["error_code"], "INVALID_ISSUE_KEY",
                         "key 正则不过应报 INVALID_ISSUE_KEY")
        self.assertEqual(req.call_count, 0, "非法 key 不得发起请求")

    def test_超过50条被拒(self):
        keys = []
        for i in range(1, 52):
            keys += ["--key", "XMKFB-%d" % i]
        code, out, req = self.run_update(
            ["update"] + keys + ["--set", "duedate=2026-12-31",
                                 "--complete-set", "--preview"])
        self.assertEqual(code, 2, "51 条超上限必须返回退出码 2")
        self.assertEqual(out["error_code"], "BATCH_LIMIT_EXCEEDED",
                         "去重后超过 50 条应报批量上限")
        self.assertEqual(req.call_count, 0, "超上限在本地拦下，不得发起请求")

    def test_去重后正好50条通过并提示去重条数(self):
        keys = []
        for i in range(1, 51):
            keys += ["--key", "XMKFB-%d" % i]
            self.jira.add_issue(make_issue("XMKFB-%d" % i, duedate="2026-08-20"))
        keys += ["--key", "xmkfb-1"]  # 大小写不同的重复项，归一后应被去掉
        code, out, _ = self.run_update(
            ["update"] + keys + ["--set", "duedate=2026-12-31",
                                 "--complete-set", "--preview"])
        self.assertEqual(code, 0, "去重后 50 条应放行")
        self.assertEqual(out["stage"], "preview", "应返回预览阶段结果")
        self.assertIn("50 条单", out["preview_text"], "预览必须写明总条数 50")
        self.assertIn("（已去重 1 条）", out["preview_text"],
                      "预览必须提示去重掉的条数")
        self.assertEqual(len(self.load_only_plan()["items"]), 50,
                         "plan 里应恰好 50 条")

    def test_多key带set_summary被拒(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--key", "XMKFB-2",
             "--set", "summary=统一改标题", "--complete-set", "--preview"])
        self.assertEqual(code, 2, "批量改标题必须返回退出码 2")
        self.assertEqual(out["error_code"], "BATCH_BODY_FIELD_FORBIDDEN",
                         "summary 是正文字段，禁止批量")

    def test_多key带description_file被拒(self):
        desc = os.path.join(self.dir, "desc.md")
        with open(desc, "w", encoding="utf-8") as f:
            f.write("统一描述")
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--key", "XMKFB-2",
             "--description-file", desc, "--complete-set", "--preview"])
        self.assertEqual(code, 2, "批量改描述必须返回退出码 2")
        self.assertEqual(out["error_code"], "BATCH_BODY_FIELD_FORBIDDEN",
                         "description 是正文字段，禁止批量")

    def test_多key缺complete_set被拒(self):
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--key", "XMKFB-2",
             "--set", "duedate=2026-12-31", "--preview"])
        self.assertEqual(code, 2, "批量缺完整集合声明必须返回退出码 2")
        self.assertEqual(out["error_code"], "BATCH_ASSERTION_REQUIRED",
                         "多条必须显式声明 --complete-set")

    def test_fixVersions跨项目被拒(self):
        code, out, req = self.run_update(
            ["update", "--key", "XMKFB-1", "--key", "ABCD-2",
             "--set", 'fixVersions=["v1.0"]', "--complete-set", "--preview"])
        self.assertEqual(code, 2, "跨项目改修复版本必须返回退出码 2")
        self.assertEqual(out["error_code"], "CROSS_PROJECT_VERSION_FORBIDDEN",
                         "版本是项目内实体，跨项目必须拒绝")
        self.assertEqual(req.call_count, 0, "跨项目拦截应在联网之前完成")


# ---------------------------------------------------------------- 写源准入

class UpdateWriteSourceTest(UpdateCaseBase):
    """设计点 10：写能力只对 WRITE_ALLOWED_SOURCES 内的源开放。"""

    def test_写源白名单常量包含双源(self):
        self.assertEqual(update_fields.WRITE_ALLOWED_SOURCES, {"Jira1", "Jira2"},
                         "写能力允许双源 Jira1 与 Jira2")

    def test_非白名单源preview被拒且零网络(self):
        code, out, req = self.run_update(
            ["--source", "Jira3", "update", "--key", "XMKFB-1",
             "--set", "duedate=2026-12-31", "--preview"])
        self.assertEqual(code, 2, "写源不被允许时退出码应为 2")
        self.assertEqual(out["error_code"], "WRITE_SOURCE_NOT_ALLOWED",
                         "非白名单源必须拒绝写")
        self.assertEqual(req.call_count, 0,
                         "写源准入必须在任何联网请求之前完成")
        self.assertEqual(self.plan_files(), [], "被拒时不得落盘 plan")

    def test_单源配置且源名在白名单内时放行(self):
        config = {"sources": [{"name": "Jira2", "base_url": "http://jira2.local",
                               "username": "u", "password": "p"}]}
        update_fields.check_write_source(config, "Jira2")  # 不抛异常即通过


# ---------------------------------------------------------------- 日期解析

class UpdateDateTest(unittest.TestCase):
    """闭集日期词表（纯函数，一律传固定 today，不 mock 系统时钟）。"""

    MONDAY = date(2026, 8, 10)      # 周一
    THURSDAY = date(2026, 8, 13)    # 周四
    SUNDAY = date(2026, 8, 16)      # 周日

    def test_今天明天后天(self):
        self.assertEqual(update_fields.resolve_date("今天", self.MONDAY), "2026-08-10",
                         "今天应解析为基准日当天")
        self.assertEqual(update_fields.resolve_date("明天", self.MONDAY), "2026-08-11",
                         "明天应解析为基准日 +1 天")
        self.assertEqual(update_fields.resolve_date("后天", self.MONDAY), "2026-08-12",
                         "后天应解析为基准日 +2 天")

    def test_本周X取本自然周(self):
        self.assertEqual(update_fields.resolve_date("本周三", self.MONDAY), "2026-08-12",
                         "周一说本周三应落在同一自然周")
        self.assertEqual(update_fields.resolve_date("本周日", self.MONDAY), "2026-08-16",
                         "周首为周一，本周日是同周的最后一天")
        self.assertEqual(update_fields.resolve_date("本周天", self.MONDAY), "2026-08-16",
                         "「天」与「日」是同一个词")
        self.assertEqual(update_fields.resolve_date("本周一", self.MONDAY), "2026-08-10",
                         "本周X 等于今天时不算过去，正常放行")

    def test_本周X已过去报错而不静默顺延(self):
        with self.assertRaises(update_fields.UpdateError) as ctx:
            update_fields.resolve_date("本周一", self.THURSDAY)
        self.assertEqual(ctx.exception.error_code, "INVALID_DATE_EXPRESSION",
                         "本周X 已过去必须报错，绝不静默顺延到下周")
        self.assertEqual(ctx.exception.exit_code, 2, "日期表达式非法退出码为 2")

    def test_下周X取下一个自然周(self):
        self.assertEqual(update_fields.resolve_date("下周一", self.MONDAY), "2026-08-17",
                         "下周一应是下一个自然周的周一")
        self.assertEqual(update_fields.resolve_date("下周日", self.MONDAY), "2026-08-23",
                         "下周日应是下一个自然周的周日")

    def test_下周X跨周(self):
        self.assertEqual(update_fields.resolve_date("下周一", self.SUNDAY), "2026-08-17",
                         "周日说下周一应跨到紧邻的下一周")

    def test_月底(self):
        self.assertEqual(update_fields.resolve_date("月底", self.MONDAY), "2026-08-31",
                         "月底为当月最后一天")
        self.assertEqual(update_fields.resolve_date("月底", date(2026, 2, 10)), "2026-02-28",
                         "2 月月底应按实际天数算")
        self.assertEqual(update_fields.resolve_date("月底", date(2026, 8, 31)), "2026-08-31",
                         "当天就是月底时返回当天")

    def test_N天后(self):
        self.assertEqual(update_fields.resolve_date("3天后", self.MONDAY), "2026-08-13",
                         "3天后应为基准日 +3 天")
        self.assertEqual(update_fields.resolve_date("30天后", self.MONDAY), "2026-09-09",
                         "N天后应能跨月")

    def test_绝对日期原样返回(self):
        self.assertEqual(update_fields.resolve_date("2026-12-31", self.MONDAY),
                         "2026-12-31", "绝对日期不做换算")

    def test_词表外表达式报错(self):
        for expr in ["下个月", "本周八", "明年今天", "尽快", "3天前", "2026-13-45", ""]:
            with self.subTest(expr=expr):
                with self.assertRaises(update_fields.UpdateError) as ctx:
                    update_fields.resolve_date(expr, self.MONDAY)
                self.assertEqual(ctx.exception.error_code, "INVALID_DATE_EXPRESSION",
                                 "闭集词表之外一律报 INVALID_DATE_EXPRESSION：%s" % expr)
                self.assertIn("YYYY-MM-DD", ctx.exception.hint,
                              "hint 必须引导改用绝对日期")

    def test_日期展示带星期(self):
        self.assertEqual(update_fields.format_date_display("2026-08-11"),
                         "2026-08-11（周二）", "工作日只标星期")

    def test_日期展示标注周末(self):
        self.assertEqual(update_fields.format_date_display("2026-08-15"),
                         "2026-08-15（周六·周末）", "周六需标注周末")
        self.assertEqual(update_fields.format_date_display("2026-08-16"),
                         "2026-08-16（周日·周末）", "周日需标注周末")


# ---------------------------------------------------------------- 状态寻路

class UpdateStatusPathTest(unittest.TestCase):
    """设计点 5：直达优先 + statusCategory 单调选边 + 终态黑名单 + 防环。"""

    def test_跳数上限为2(self):
        self.assertEqual(update_fields.MAX_HOPS, 2, "跳数上限写死为 2 跳")

    def test_状态口语词表实测回填后不再映射(self):
        # 2026-08-12 实测 Jira2 完成类状态显示名即「完成」，口语词原样透传
        self.assertEqual(update_fields.STATUS_ALIASES.get("完成", "完成"), "完成",
                         "实测回填后口语「完成」不再映射，原样作为目标状态名")

    def test_parse_transitions保留分类与必填项(self):
        resp = {"transitions": [transition(
            "11", "开始处理", "3", "进行中", "indeterminate",
            required={"resolution": RESOLUTION_REQUIRED["resolution"],
                      "assignee": {"required": False, "name": "经办人"}})]}
        parsed = update_plan.parse_transitions(resp)
        self.assertEqual(len(parsed), 1, "应解析出 1 条流转")
        t = parsed[0]
        self.assertEqual(t["id"], "11", "流转 id 原样保留")
        self.assertEqual(t["to_id"], "3", "必须保留目标状态 id")
        self.assertEqual(t["to_name"], "进行中", "必须保留目标状态名")
        self.assertEqual(t["to_category"], "indeterminate",
                         "必须保留 statusCategory（cmd_transitions 的裁剪结果丢了它）")
        self.assertEqual([r["field"] for r in t["required"]], ["resolution"],
                         "只收 required 为真的字段")
        self.assertEqual(t["required"][0]["default"], {"id": "1", "name": "已解决"},
                         "必须保留原始 defaultValue")
        self.assertEqual(len(t["required"][0]["allowed"]), 2,
                         "必须保留原始 allowedValues")

    def test_直达优先于一切规则(self):
        ts = [
            {"id": "1", "name": "开始", "to_id": "3", "to_name": "进行中",
             "to_category": "indeterminate", "required": []},
            {"id": "9", "name": "完成", "to_id": "6", "to_name": "已完成",
             "to_category": "done", "required": []},
        ]
        picked = update_plan.pick_next_hop(ts, "new", "已完成", "done", set())
        self.assertEqual(picked["id"], "9",
                         "存在直达目标状态的流转时必须直接选它，不看 id 顺序")

    def test_无直达时按分类单调选边(self):
        ts = [
            {"id": "11", "name": "开始", "to_id": "3", "to_name": "进行中",
             "to_category": "indeterminate", "required": []},
            {"id": "21", "name": "取消", "to_id": "7", "to_name": "已取消",
             "to_category": "done", "required": []},
        ]
        picked = update_plan.pick_next_hop(ts, "new", "已完成", "done", set())
        self.assertEqual(picked["to_name"], "进行中",
                         "候选须满足 rank(to) >= rank(当前) 且 rank(to) < rank(目标)")

    def test_终态黑名单候选被排除(self):
        ts = [
            {"id": "5", "name": "驳回", "to_id": "8", "to_name": "已驳回",
             "to_category": "indeterminate", "required": []},
            {"id": "11", "name": "开始", "to_id": "3", "to_name": "进行中",
             "to_category": "indeterminate", "required": []},
        ]
        picked = update_plan.pick_next_hop(ts, "new", "已完成", "done", set())
        self.assertEqual(picked["to_name"], "进行中",
                         "命中终态关键词的候选必须排除，哪怕它的 id 更小")

    def test_同档多条按id数值升序取第一条(self):
        ts = [
            {"id": "10", "name": "转甲", "to_id": "31", "to_name": "处理中甲",
             "to_category": "indeterminate", "required": []},
            {"id": "2", "name": "转乙", "to_id": "32", "to_name": "处理中乙",
             "to_category": "indeterminate", "required": []},
        ]
        picked = update_plan.pick_next_hop(ts, "new", "已完成", "done", set())
        self.assertEqual(picked["id"], "2",
                         "同档多条按 int(id) 数值升序取第一条，不是字符串排序")

    def test_visited防环(self):
        ts = [{"id": "11", "name": "回退", "to_id": "3", "to_name": "进行中",
               "to_category": "indeterminate", "required": []}]
        picked = update_plan.pick_next_hop(ts, "new", "已完成", "done", {"进行中"})
        self.assertIsNone(picked, "已访问过的目标状态不得再选，防止兜圈子")

    def test_无合规候选返回None(self):
        ts = [{"id": "21", "name": "取消", "to_id": "7", "to_name": "已取消",
               "to_category": "done", "required": []}]
        self.assertIsNone(update_plan.pick_next_hop(ts, "new", "已完成", "done", set()),
                          "无合规候选时返回 None，由调用方判不可达")

    def test_自动填充优先取流转默认值(self):
        required = [{"field": "resolution", "name": "解决结果",
                     "default": {"id": "1", "name": "已解决"},
                     "allowed": [{"id": "9", "name": "未解决"}]}]
        payload, display = update_plan.auto_fill(required)
        self.assertEqual(payload, {"resolution": {"id": "1"}},
                         "有默认值时用默认值构造载荷")
        self.assertEqual(display[0]["source"], "流转默认值",
                         "来源应标注为流转默认值")
        self.assertEqual(display[0]["value_name"], "已解决", "展示值名取默认值的 name")
        self.assertEqual(display[0]["field"], "resolution", "展示项须带字段英文名")

    def test_自动填充无默认值取候选首项(self):
        required = [{"field": "resolution", "name": "解决结果", "default": None,
                     "allowed": [{"id": "7", "name": "未解决"},
                                 {"id": "8", "name": "无法重现"}]}]
        payload, display = update_plan.auto_fill(required)
        self.assertEqual(payload, {"resolution": {"id": "7"}},
                         "无默认值时取 allowedValues 首项")
        self.assertEqual(display[0]["source"], "候选列表首项",
                         "来源应标注为候选列表首项")

    def test_自动填充无id的候选原样透传(self):
        required = [{"field": "customfield_10010", "name": "自定义", "default": None,
                     "allowed": ["甲"]}]
        payload, display = update_plan.auto_fill(required)
        self.assertEqual(payload, {"customfield_10010": "甲"},
                         "候选元素不带 id 时原样透传该元素")
        self.assertEqual(display[0]["source"], "候选列表首项", "来源仍是候选列表首项")

    def test_自动填充无默认值无候选时不填(self):
        required = [{"field": "customfield_10011", "name": "无解", "default": None,
                     "allowed": []}]
        payload, display = update_plan.auto_fill(required)
        self.assertEqual(payload, {}, "既无默认值又无候选时该项不填")
        self.assertIsNone(display[0]["source"], "该项来源记为 None")


class UpdateStatusPreviewTest(UpdateCaseBase):
    """状态相关的预览端到端行为。"""

    def test_口语完成直达一跳(self):
        # 2026-08-12 实测回填：完成类状态显示名即「完成」，口语词原样透传、预览不再出现映射说明
        self.jira.project_statuses = [{
            "id": "10001", "name": "任务",
            "statuses": [
                {"id": "10000", "name": "待办", "statusCategory": {"key": "new"}},
                {"id": "3", "name": "进行中", "statusCategory": {"key": "indeterminate"}},
                {"id": "6", "name": "完成", "statusCategory": {"key": "done"}},
            ],
        }]
        self.jira.add_issue(
            make_issue("XMKFB-1", duedate=None),
            transitions=[transition("5", "完成", "6", "完成", "done",
                                    required=RESOLUTION_REQUIRED)])
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--status", "完成", "--preview"])
        self.assertEqual(code, 0, "直达可达时预览应成功")
        self.assertNotIn("已按约定映射", out["preview_text"],
                         "实测回填后不再做口语映射，预览不得出现映射说明")
        self.assertIn("自动填充：解决结果 = 已解决（流转默认值）", out["preview_text"],
                      "流转必填项须标注为自动填充")
        item = self.load_only_plan()["items"][0]
        self.assertEqual(item["status_change"]["to_name"], "完成",
                         "plan 里记的就是目标状态名「完成」")
        self.assertEqual(item["status_change"]["reachability"], "direct",
                         "存在直达流转时可达性为 direct")

    def test_无直达时可达性为predicted(self):
        self.jira.add_issue(
            make_issue("XMKFB-1", status_name="待办"),
            transitions=[transition("11", "开始处理", "3", "进行中", "indeterminate")])
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--status", "已完成", "--preview"])
        self.assertEqual(code, 0, "有合规首跳时预览应成功")
        item = self.load_only_plan()["items"][0]
        self.assertEqual(item["status_change"]["reachability"], "predicted",
                         "只有首跳合规时可达性为 predicted")
        self.assertIn("最多 2 跳", out["preview_text"], "多跳提示须写明跳数上限")

    def test_幂等短路不判blocker(self):
        # 当前状态已是目标状态：既不寻路也不算 blocker，哪怕一条可用流转都没有
        # （2026-08-12 实测回填：完成类状态显示名即「完成」）
        self.jira.add_issue(
            make_issue("XMKFB-1", status_name="完成", status_id="6", category="done"),
            transitions=[])
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--status", "完成", "--preview"])
        self.assertEqual(code, 0, "幂等条目不得让整份预览失败")
        self.assertTrue(out["ok"], "幂等短路应正常出预览")
        item = self.load_only_plan()["items"][0]
        self.assertTrue(item["no_change"], "当前状态等于目标状态时标记 no_change")


# ---------------------------------------------------------------- 预览门禁

class UpdatePreviewGateTest(UpdateCaseBase):
    """名称解析与可达性门禁：整份失败、不落 plan、退出码 1。"""

    def test_经办人0命中(self):
        self.jira.add_issue(make_issue("XMKFB-1", assignee=None))
        self.jira.users = []
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "assignee=查无此人", "--preview"])
        self.assertEqual(code, 1, "名称解析失败属预览联网期业务失败，退出码 1")
        self.assertEqual(out["error_code"], "FIELD_VALUE_NO_MATCH",
                         "0 命中报 FIELD_VALUE_NO_MATCH")
        self.assertEqual(out["field"], "assignee", "载荷须写明是哪个字段")
        self.assertEqual(out["candidates"], [], "0 命中时候选为空数组")
        self.assertEqual(self.plan_files(), [], "门禁失败时不得落盘 plan")

    def test_经办人多命中(self):
        self.jira.add_issue(make_issue("XMKFB-1", assignee=None))
        self.jira.users = [
            {"name": "zhang.san", "displayName": "张三", "emailAddress": "z3@x.com"},
            {"name": "zhang.wu", "displayName": "张五", "emailAddress": "z5@x.com"},
        ]
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "assignee=张", "--preview"])
        self.assertEqual(code, 1, "多命中属预览联网期业务失败，退出码 1")
        self.assertEqual(out["error_code"], "FIELD_VALUE_AMBIGUOUS",
                         "多命中报 FIELD_VALUE_AMBIGUOUS")
        self.assertEqual(out["field"], "assignee", "载荷须写明是哪个字段")
        self.assertEqual(len(out["candidates"]), 2, "候选应把两个人都列出来")
        self.assertEqual(out["candidates"][0]["id"], "zhang.san",
                         "候选项用 id 承载账号名")
        self.assertIn("display", out["candidates"][0], "候选项须带可读展示名")
        self.assertEqual(self.plan_files(), [], "门禁失败时不得落盘 plan")

    def test_目标状态不可达整份预览失败(self):
        self.jira.add_issue(make_issue("XMKFB-1", status_name="待办"), transitions=[])
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--status", "已完成", "--preview"])
        self.assertEqual(code, 1, "存在 blocker 时退出码为 1")
        self.assertEqual(out["error_code"], "PREVIEW_HAS_BLOCKERS",
                         "任一条不可达即整份预览失败")
        self.assertEqual(out["blockers"][0]["key"], "XMKFB-1", "blocker 须指明单号")
        self.assertIn("reason", out["blockers"][0], "blocker 须说明原因")
        self.assertEqual(self.plan_files(), [],
                         "整份预览失败时 state/plans 下不得产生任何文件")


# ---------------------------------------------------------------- TTL

class UpdateTtlTest(UpdateCaseBase):
    """TTL 档位：批量 900 秒 / 单条 300 秒，且不改 plan.py。"""

    def _ttl_of_plan(self):
        plan = self.load_only_plan()
        created = datetime.fromisoformat(plan["created_at"])
        expires = datetime.fromisoformat(plan["expires_at"])
        return (expires - created).total_seconds()

    def test_TTL常量(self):
        self.assertEqual(update_fields.TTL_SINGLE_SECONDS, 300, "单条预览 5 分钟")
        self.assertEqual(update_fields.TTL_BATCH_SECONDS, 900, "批量预览 15 分钟")

    def test_单条预览TTL为300秒(self):
        self.jira.add_issue(make_issue("XMKFB-1", duedate="2026-08-20"))
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--set", "duedate=2026-12-31", "--preview"])
        self.assertEqual(code, 0, "单条预览应成功")
        self.assertEqual(out["ttl_seconds"], 300, "单条预览 TTL 为 300 秒")
        self.assertAlmostEqual(self._ttl_of_plan(), 300, delta=2,
                               msg="plan 的 expires_at 应约等于 created_at + 300 秒")

    def test_批量预览TTL为900秒(self):
        self.jira.add_issue(make_issue("XMKFB-1", duedate="2026-08-20"))
        self.jira.add_issue(make_issue("XMKFB-2", duedate="2026-08-20"))
        code, out, _ = self.run_update(
            ["update", "--key", "XMKFB-1", "--key", "XMKFB-2",
             "--set", "duedate=2026-12-31", "--complete-set", "--preview"])
        self.assertEqual(code, 0, "批量预览应成功")
        self.assertEqual(out["ttl_seconds"], 900, "批量预览 TTL 为 900 秒")
        self.assertAlmostEqual(self._ttl_of_plan(), 900, delta=2,
                               msg="plan 的 expires_at 应约等于 created_at + 900 秒")

    def test_不改plan_py靠现有ttl参数达成(self):
        import inspect
        params = list(inspect.signature(planmod.create_plan).parameters)
        self.assertEqual(params, ["plans_dir", "payload", "ttl_seconds"],
                         "TTL 分档必须复用现有 create_plan(ttl_seconds=...)，不得改 plan.py")
        self.assertEqual(planmod.DEFAULT_TTL_SECONDS, 300, "plan.py 默认 TTL 保持不变")


# ---------------------------------------------------------------- 预览文案

def _plan_fixture():
    """契约 §4.1 模板对应的 plan（纯数据，供渲染层逐字比对）。"""
    return {
        "action": "update", "source": "Jira2", "base_url": "http://jira2.local",
        "ttl_seconds": 900, "complete_set_declared": True,
        "allow_closed_transition": False, "base_date": "2026-08-10",
        "items": [
            {"key": "XMKFB-123", "project_key": "XMKFB",
             "field_changes": [
                 {"name": "截止日期", "jira_field": "duedate",
                  "old": "2026-08-20", "new": "2026-08-11",
                  "new_display": "2026-08-11（周二）", "removed": []}],
             "put_payload": {"duedate": "2026-08-11"},
             "before": {"duedate": "2026-08-20",
                        "status": {"id": "10000", "name": "待办", "category": "new"}},
             "status_change": {"from_id": "10000", "from_name": "待办",
                               "to_name": "已完成", "reachability": "direct",
                               "auto_filled": [{"field": "resolution",
                                                "name": "解决结果",
                                                "value_id": "1",
                                                "value_name": "已解决",
                                                "source": "流转默认值"}]},
             "no_change": False, "closed": False},
            {"key": "XMKFB-124", "project_key": "XMKFB",
             "field_changes": [
                 {"name": "标签", "jira_field": "labels",
                  "old": ["线上问题", "二期"],
                  "new": ["线上问题", "二期", "需回归"],
                  "new_display": "[线上问题, 二期, 需回归]", "removed": []}],
             "put_payload": {"labels": ["线上问题", "二期", "需回归"]},
             "before": {"labels": ["线上问题", "二期"],
                        "status": {"id": "3", "name": "进行中",
                                   "category": "indeterminate"}},
             "status_change": {"from_id": "3", "from_name": "进行中",
                               "to_name": "已完成", "reachability": "predicted",
                               "auto_filled": []},
             "no_change": False, "closed": False},
        ],
        "totals": {"issues": 2},
    }


def _meta_fixture(**over):
    meta = {"source_name": "Jira2", "base_date": "2026-08-10", "dup_removed": 1,
            "plan_id": "plan_ab12cd34", "ttl_seconds": 900,
            "alias_note": "完成", "closed_count": 0}
    meta.update(over)
    return meta


EXPECTED_PREVIEW = """操作源：Jira2
基准日：2026-08-10（本机当天）
本次将修改 2 条单（已去重 1 条）：

[1] XMKFB-123
    截止日期：2026-08-20 → 2026-08-11（周二）
    状态：待办 → 已完成
    自动填充：解决结果 = 已解决（流转默认值）
[2] XMKFB-124
    标签：[线上问题, 二期] → [线上问题, 二期, 需回归]
    状态：进行中 → 已完成（需多步流转，执行时自动寻路，最多 2 跳；若 2 跳内到不了，该条会停在中间状态并记为失败，工具不会改回去）

你说的「完成」已按约定映射为目标状态「已完成」。
若需多跳，后续跳的必填项按同样规则自动填充，预览无法提前列出。
预计执行耗时：约 1 分钟（上界估算）
本次将对 2 条单产生变更通知（按待执行条数估算，未逐单统计关注人；一条单可能触达多名关注人）
助手声明：本清单为完整集合（非截断结果）
若上一步查询结果标注「结果不完整」，请勿确认。
本预览 15 分钟内有效（plan_id: plan_ab12cd34）
本工具不提供撤销。"""


class UpdatePreviewTextTest(unittest.TestCase):
    """契约 §4.1 预览文案模板（纯函数渲染，逐字比对）。"""

    def test_模板逐字一致(self):
        text = update_render.render_preview(_plan_fixture(), _meta_fixture())
        self.assertEqual(text.rstrip("\n"), EXPECTED_PREVIEW,
                         "preview_text 必须与契约 §4.1 模板逐字一致")

    def test_描述只给字符数与前300字不倾泻全文(self):
        """设计稿场景 12：描述预览给新旧字符数与转换后正文前 300 字。

        回归用例：曾直接把整篇 wiki 正文塞进 preview_text，而 SKILL.md 强制模型
        原样整段粘贴，几 KB 描述会把条数、目标状态、有效期这些要复核的信息全淹掉。
        """
        change = {"jira_field": "description", "name": "描述",
                  "old": "旧" * 1200, "new": "新" * 900}
        line = update_render.format_change_line(change)
        self.assertIn("1200 字 → 900 字", line, "描述行必须给出新旧字符数")
        self.assertIn("新正文前 300 字：", line, "描述行必须给出正文前 300 字")
        self.assertNotIn("旧" * 50, line, "描述行不得倾泻旧正文全文")
        body_shown = line.split("新正文前 300 字：", 1)[1]
        self.assertLessEqual(len(body_shown.rstrip("…")), 300,
                             "正文摘要不得超过 300 字")

    def test_标题仍按旧值到新值全文对照(self):
        """标题短且是覆盖式写入，必须保留完整对照，不走描述的摘要分支。"""
        change = {"jira_field": "summary", "name": "标题",
                  "old": "原标题", "new": "新标题"}
        line = update_render.format_change_line(change)
        self.assertIn("原标题 → 新标题", line, "标题必须按旧值到新值全文对照")

    def test_无去重时不出现去重提示(self):
        text = update_render.render_preview(_plan_fixture(), _meta_fixture(dup_removed=0))
        self.assertIn("本次将修改 2 条单：", text, "无去重时是干净的冒号结尾")
        self.assertNotIn("已去重", text, "dup_removed 为 0 时不得出现去重提示")

    def test_单条预览有效期写5分钟(self):
        plan = _plan_fixture()
        plan["ttl_seconds"] = 300
        plan["items"] = plan["items"][:1]
        text = update_render.render_preview(
            plan, _meta_fixture(ttl_seconds=300, dup_removed=0))
        self.assertIn("本预览 5 分钟内有效（plan_id: plan_ab12cd34）", text,
                      "单条预览有效期写死为 5 分钟")
        self.assertNotIn("15 分钟", text, "单条预览不得出现 15 分钟")

    def test_未声明完整集合时不出断言行(self):
        plan = _plan_fixture()
        plan["complete_set_declared"] = False
        text = update_render.render_preview(plan, _meta_fixture())
        self.assertNotIn("助手声明：本清单为完整集合（非截断结果）", text,
                         "未带 --complete-set 时不得伪称完整集合")
        self.assertIn("若上一步查询结果标注「结果不完整」，请勿确认。", text,
                      "截断警示行恒有")

    def test_无状态映射时不出别名说明行(self):
        text = update_render.render_preview(_plan_fixture(), _meta_fixture(alias_note=None))
        self.assertNotIn("已按约定映射为目标状态", text,
                         "未发生口语映射时不得出现别名说明行")

    def test_旧值为空写空占位(self):
        plan = _plan_fixture()
        plan["items"] = plan["items"][:1]
        plan["items"][0]["field_changes"][0]["old"] = None
        text = update_render.render_preview(plan, _meta_fixture(dup_removed=0))
        self.assertIn("    截止日期：（空） → 2026-08-11（周二）", text,
                      "旧值为空必须写「（空）」而不是空白")

    def test_集合字段被移除项单起一行(self):
        plan = _plan_fixture()
        plan["items"] = plan["items"][1:]
        plan["items"][0]["field_changes"][0]["new"] = ["需回归"]
        plan["items"][0]["field_changes"][0]["new_display"] = "[需回归]"
        plan["items"][0]["field_changes"][0]["removed"] = ["线上问题", "二期"]
        text = update_render.render_preview(plan, _meta_fixture(dup_removed=0))
        self.assertIn("    标签：[线上问题, 二期] → [需回归]", text,
                      "集合字段展示全量旧值到全量新值")
        self.assertIn("        将被移除：线上问题、二期", text,
                      "被顶掉的项必须单起一行显式列出")

    def test_授权推完成类状态时追加提示行(self):
        plan = _plan_fixture()
        plan["allow_closed_transition"] = True
        plan["items"][0]["closed"] = True
        text = update_render.render_preview(plan, _meta_fixture(closed_count=1))
        self.assertIn("本次包含 1 条已处于完成类状态的单，你已显式授权对它们推状态；"
                      "这类流转在多数工作流里推不回来", text,
                      "带 --allow-closed-transition 时必须显式提示不可逆")

    def test_末行固定为不提供撤销(self):
        text = update_render.render_preview(_plan_fixture(), _meta_fixture())
        self.assertEqual(text.rstrip("\n").splitlines()[-1], "本工具不提供撤销。",
                         "末行固定，且不得承诺任何回滚能力")

    def test_customfield_在预览中不报KeyError(self):
        import tempfile
        import shutil
        plans_dir = tempfile.mkdtemp()
        try:
            issues = [{
                "key": "TRS-1",
                "fields": {
                    "project": {"key": "TRS"},
                    "issuetype": {"id": "1", "name": "任务"},
                    "status": {"id": "1", "name": "待办", "statusCategory": {"key": "new"}},
                    "customfield_10001": "旧自定义值"
                }
            }]
            client_mod = FakeJira()
            client_mod.add_issue(issues[0])
            opts = {
                "keys": ["TRS-1"],
                "set_pairs": [("customfield_10001", "新自定义值")],
                "config": CONFIG,
            }
            out, code = update_plan.build_preview(
                client_mod, CONFIG["sources"][0], opts, plans_dir, date(2026, 8, 10))
            self.assertEqual(code, 0)
            self.assertTrue(out["ok"])
            changes = out["preview"]["items"][0]["field_changes"]
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["jira_field"], "customfield_10001")
            self.assertEqual(changes[0]["old"], "旧自定义值")
            self.assertEqual(changes[0]["new"], "新自定义值")
        finally:
            shutil.rmtree(plans_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
