# -*- coding: utf-8 -*-
"""update 执行侧单测（TDD 红灯先行）。

测试目标：
  1. `update_exec.execute` 的执行时间轴：抢改复核 → 关闭单兜底 → 幂等 → 写字段 → 推状态 → 逐条审计；
  2. 报告契约（三分统计 / resume_keys / has_failures / result_text 首部）与 apply 前置门禁
     （PLAN_REJECTED / PLAN_MALFORMED / WRITE_SOURCE_NOT_ALLOWED）；
  3. `client.request` 对「成功但响应体为空」（PUT / 流转返回 204 无体）的处理。

依赖环境：无。全部离线跑，纯标准库 + unittest.mock。
  - 执行侧：打桩 `client.request`（FakeJira），一次真实 HTTP 都不发；
  - client 空体用例：打桩 `urllib.request.urlopen`，桩类写法照抄 tests/test_client.py 的 FakeResponse。

数据准备方式：plan / issue 快照全部由本文件内的构造函数就地拼装（make_plan / make_item / make_issue），
不读磁盘上的任何 plan，也不依赖 jira_config.json。涉及 CLI 的用例用 tempfile 临时目录
接管 jira_cli.PLANS_DIR / AUDIT_LOG，不污染仓库 state/ 目录。
"""

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import client
import jira_cli
import plan as planmod
import update_exec
import update_fields


# ---------------------------------------------------------------- 公共桩与构造

SOURCE = client.normalize_source({
    "name": "Jira2", "base_url": "http://jira.local", "username": "u", "password": "p",
})

CONFIG = {
    "default_source": "Jira2",
    "sources": [
        {"name": "Jira2", "base_url": "http://jira.local", "username": "u", "password": "p"},
        {"name": "Jira1", "base_url": "http://jira1.local", "username": "u", "password": "p"},
        {"name": "Jira3", "base_url": "http://jira3.local", "username": "u", "password": "p"},
    ],
}


def _key_from_path(path):
    """从 /rest/api/2/issue/XMKFB-1?fields=... 里抠出 issue key。"""
    m = re.search(r"/issue/([^/?]+)", path)
    return m.group(1) if m else ""


def _resolve(outcome):
    """桩返回值统一处理：异常实例就抛，None 视作「成功且无响应体」。"""
    if isinstance(outcome, BaseException):
        raise outcome
    return {} if outcome is None else outcome


class FakeJira:
    """`client.request` 的替身：按方法+路径分派，逐条记录调用。

    构造参数：
      get_issue      {key: 复核 GET 返回的 issue dict 或 待抛异常}
      transitions    {key: [第 1 次 GET transitions 的响应, 第 2 次, ...]}（用尽后重复最后一个）
      put            {key: None 表示写成功，异常实例表示抛出}
      do_transition  {key: [第 1 跳 POST 结果, 第 2 跳, ...]}（None 表示该跳成功）
      hook           每次调用前触发的回调 hook(method, path, body)，用于观察「调用发生的时刻」
    """

    def __init__(self, get_issue=None, transitions=None, put=None,
                 do_transition=None, hook=None):
        self.get_issue = get_issue or {}
        self.transitions = transitions or {}
        self.put = put or {}
        self.do_transition = do_transition or {}
        self.hook = hook
        self.calls = []
        self._get_transition_count = {}
        self._post_transition_count = {}

    def __call__(self, source, method, path, body=None, **kwargs):
        self.calls.append({"method": method, "path": path, "body": body})
        if self.hook is not None:
            self.hook(method, path, body)
        key = _key_from_path(path)
        if "/transitions" in path and method == "GET":
            seq = self.transitions.get(key) or [{"transitions": []}]
            idx = self._get_transition_count.get(key, 0)
            self._get_transition_count[key] = idx + 1
            return _resolve(seq[idx] if idx < len(seq) else seq[-1])
        if "/transitions" in path and method == "POST":
            seq = self.do_transition.get(key) or []
            idx = self._post_transition_count.get(key, 0)
            self._post_transition_count[key] = idx + 1
            return _resolve(seq[idx] if idx < len(seq) else None)
        if method == "GET":
            return _resolve(self.get_issue.get(key, {"key": key, "fields": {}}))
        if method == "PUT":
            return _resolve(self.put.get(key))
        raise AssertionError("桩未覆盖的请求：%s %s" % (method, path))

    # -- 断言辅助 --
    def methods(self):
        return [c["method"] for c in self.calls]

    def puts(self, key=None):
        return [c for c in self.calls
                if c["method"] == "PUT" and (key is None or _key_from_path(c["path"]) == key)]

    def transition_posts(self, key=None):
        return [c for c in self.calls
                if c["method"] == "POST" and "/transitions" in c["path"]
                and (key is None or _key_from_path(c["path"]) == key)]


def status_value(status_id, name, category):
    """构造 issue.fields.status 快照。"""
    return {"id": status_id, "name": name, "statusCategory": {"key": category}}


def make_issue(key, fields):
    return {"key": key, "fields": fields}


def make_transition(tid, name, to_id, to_name, to_category, fields=None):
    """构造 GET transitions 的一条原始 transition。"""
    return {"id": tid, "name": name, "fields": fields or {},
            "to": {"id": to_id, "name": to_name,
                   "statusCategory": {"key": to_category}}}


def make_item(key, put_payload=None, field_changes=None, before=None,
              status_change=None, no_change=False, closed=False, project_key=None):
    """按契约 §5.1 拼一条 plan item。"""
    return {
        "key": key,
        "project_key": project_key or key.split("-")[0],
        "field_changes": field_changes or [],
        "put_payload": put_payload if put_payload is not None else {},
        "before": before or {},
        "status_change": status_change,
        "no_change": no_change,
        "closed": closed,
    }


def make_plan(items, source="Jira2", allow_closed=False, complete_set=True,
              plan_id="plan_abcd1234", base_date="2026-08-10"):
    return {
        "plan_id": plan_id,
        "action": "update",
        "source": source,
        "base_url": "http://jira.local",
        "ttl_seconds": 900,
        "complete_set_declared": complete_set,
        "allow_closed_transition": allow_closed,
        "base_date": base_date,
        "items": items,
        "totals": {"issues": len(items)},
    }


def field_change(jira_field, cn, old, new, new_display=None, removed=None):
    return {"name": cn, "jira_field": jira_field, "old": old, "new": new,
            "new_display": new_display if new_display is not None else new,
            "removed": removed or []}


def run_execute(stub, plan, audit_fn=None):
    """跑 update_exec.execute，返回 (report, 审计记录列表)。"""
    records = []
    fn = audit_fn if audit_fn is not None else records.append
    with mock.patch.object(client, "request", new=stub):
        report = update_exec.execute(client, SOURCE, plan, fn)
    return report, records


def item_of(report, key):
    for it in report["items"]:
        if it.get("key") == key:
            return it
    raise AssertionError("报告里找不到条目 %s，实际条目：%s"
                         % (key, [i.get("key") for i in report["items"]]))


def _as_text(value):
    """把字段旧值折成字符串，用于长度断言（列表/字典按 JSON 计）。"""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def find_field_record(record, jira_field, cn_name):
    """在审计记录的 field_changes 里定位某字段（兼容 list 与 dict 两种落盘形态）。"""
    changes = record.get("field_changes")
    if isinstance(changes, dict):
        return changes.get(jira_field) or changes.get(cn_name)
    for c in changes or []:
        if c.get("jira_field") == jira_field or c.get("name") in (jira_field, cn_name):
            return c
    return None


def run_cli(argv):
    """跑 jira_cli.main 并捕获 stdout，返回 (退出码, 解析后的 JSON)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = jira_cli.main(argv)
    text = buf.getvalue().strip()
    return code, json.loads(text) if text else None


# ---------------------------------------------------------------- 执行时间轴

class UpdateExecuteTest(unittest.TestCase):
    """execute 的逐条时间轴：跳过判定、写字段、推状态、异常不穿透。"""

    def test_抢改复核发现值变化则跳过且不发写请求(self):
        item = make_item(
            "XMKFB-101",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20",
                    "status": status_value("10000", "待办", "new")})
        stub = FakeJira(get_issue={"XMKFB-101": make_issue("XMKFB-101", {
            "duedate": "2026-08-25",  # 他人已经改成了别的日期
            "status": status_value("10000", "待办", "new")})})
        report, _ = run_execute(stub, make_plan([item]))

        entry = item_of(report, "XMKFB-101")
        self.assertEqual(entry["result"], "skipped", "复核发现值被他人改动必须跳过该条")
        self.assertIn("他人已改动", entry["reason"], "跳过原因须写明是他人改动")
        self.assertIn("截止日期", entry["reason"], "跳过原因须点名是哪个字段（中文名）")
        self.assertEqual(stub.puts(), [], "复核不通过时绝不允许发出 PUT 写请求")
        self.assertEqual(stub.transition_posts(), [], "复核不通过时也不允许推状态")

    def test_幂等条目跳过且不发写请求(self):
        item = make_item(
            "XMKFB-102",
            put_payload={},
            field_changes=[],
            before={"status": status_value("10002", "已完成", "done")},
            no_change=True)
        stub = FakeJira(get_issue={"XMKFB-102": make_issue("XMKFB-102", {
            "status": status_value("10002", "已完成", "done")})})
        report, _ = run_execute(stub, make_plan([item]))

        entry = item_of(report, "XMKFB-102")
        self.assertEqual(entry["result"], "skipped", "值已是目标值的条目应记跳过")
        self.assertIn("值已是目标值", entry["reason"], "幂等跳过原因文案须逐字对齐契约")
        self.assertEqual(stub.puts(), [], "幂等条目不得发 PUT")
        self.assertEqual(stub.transition_posts(), [], "幂等条目不得发流转请求")

    def test_已关闭单未授权时跳过状态但普通字段照改(self):
        # 状态 id 未变（避开第 1 步抢改判定：status 按 status.id 比对），
        # 但类别已经变成 done —— 专门验第 2 步「执行前被他人关闭」的兜底。
        item = make_item(
            "XMKFB-103",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20",
                    "status": status_value("10000", "待办", "new")},
            status_change={"from_id": "10000", "from_name": "待办", "to_name": "已完成",
                           "reachability": "direct", "auto_filled": []},
            closed=False)
        stub = FakeJira(
            get_issue={"XMKFB-103": make_issue("XMKFB-103", {
                "duedate": "2026-08-20",
                "status": status_value("10000", "待办", "done")})},
            transitions={"XMKFB-103": [{"transitions": [
                make_transition("21", "完成", "10002", "已完成", "done")]}]})
        report, _ = run_execute(stub, make_plan([item], allow_closed=False))

        entry = item_of(report, "XMKFB-103")
        self.assertEqual(len(stub.puts("XMKFB-103")), 1, "已关闭单的普通字段仍要照改，PUT 必须发出")
        self.assertEqual(stub.puts("XMKFB-103")[0]["body"],
                         {"fields": {"duedate": "2026-08-11"}},
                         "普通字段载荷应原样取自 plan")
        self.assertEqual(stub.transition_posts("XMKFB-103"), [],
                         "未获显式授权时绝不允许对已关闭单推状态")
        self.assertEqual(entry["result"], "skipped", "该条按契约记跳过")
        self.assertIn("执行前已被他人关闭", entry["reason"], "跳过原因须写明是执行前被关闭")

    def test_字段写失败则不再发流转请求(self):
        item = make_item(
            "XMKFB-104",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20",
                    "status": status_value("10000", "待办", "new")},
            status_change={"from_id": "10000", "from_name": "待办", "to_name": "已完成",
                           "reachability": "direct", "auto_filled": []})
        stub = FakeJira(
            get_issue={"XMKFB-104": make_issue("XMKFB-104", {
                "duedate": "2026-08-20",
                "status": status_value("10000", "待办", "new")})},
            transitions={"XMKFB-104": [{"transitions": [
                make_transition("21", "完成", "10002", "已完成", "done")]}]},
            put={"XMKFB-104": client.JiraError("JQL_INVALID",
                                               "请求被 Jira 拒绝 (HTTP 400): 单据已归档不可写")})
        report, _ = run_execute(stub, make_plan([item]))

        entry = item_of(report, "XMKFB-104")
        self.assertEqual(entry["result"], "failed", "字段写失败该条应记失败")
        self.assertEqual(stub.transition_posts("XMKFB-104"), [],
                         "字段写失败后不得再推状态（半成品风险）")
        self.assertFalse(entry["half_done"], "字段都没写进去，不算半成品")
        self.assertIn("单据已归档不可写", entry["reason"], "失败原因应回带 Jira 原文")
        self.assertNotIn("JQL_INVALID", entry["reason"],
                         "逐条失败原因只渲染 JiraError.error 文本，不得显示 error_code 名")

    def test_流转第二跳失败时报告含half_done与停在提示(self):
        item = make_item(
            "XMKFB-105",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20",
                    "status": status_value("10000", "待办", "new")},
            status_change={"from_id": "10000", "from_name": "待办", "to_name": "已完成",
                           "reachability": "predicted", "auto_filled": []})
        stub = FakeJira(
            get_issue={"XMKFB-105": make_issue("XMKFB-105", {
                "duedate": "2026-08-20",
                "status": status_value("10000", "待办", "new")})},
            transitions={"XMKFB-105": [
                # 第 1 跳：无直达「已完成」，只能先到「进行中」
                {"transitions": [make_transition("11", "开始处理", "3", "进行中",
                                                 "indeterminate")]},
                # 第 2 跳：有直达「已完成」，但 POST 会失败
                {"transitions": [make_transition("21", "完成", "10002", "已完成", "done")]},
            ]},
            do_transition={"XMKFB-105": [
                None,
                client.JiraError("JQL_INVALID", "请求被 Jira 拒绝 (HTTP 400): 缺少必填项 解决结果"),
            ]})
        report, _ = run_execute(stub, make_plan([item]))

        entry = item_of(report, "XMKFB-105")
        self.assertEqual(entry["result"], "failed", "流转没走到目标状态该条记失败")
        self.assertTrue(entry["half_done"], "字段已改但状态卡在中途，必须标 half_done")
        self.assertIn("停在「进行中」", entry["reason"], "失败原因须写明停在哪个状态")
        self.assertIn("（原始状态 待办）", entry["reason"], "失败原因须写明原始状态")
        self.assertEqual(len(stub.transition_posts("XMKFB-105")), 2,
                         "应恰好尝试了 2 跳（上限 MAX_HOPS）")

    def test_429重试一次仍失败该条记失败且继续处理下一条(self):
        # client.request 内部已经退避重试过一次，仍失败才抛 RATE_LIMITED；
        # 这里验证执行层不熔断：第 1 条失败后第 2 条照常处理。
        first = make_item(
            "XMKFB-106",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20",
                    "status": status_value("10000", "待办", "new")})
        second = make_item(
            "XMKFB-107",
            put_payload={"duedate": "2026-08-12"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-12")],
            before={"duedate": "2026-08-20",
                    "status": status_value("10000", "待办", "new")})
        snapshot = {"XMKFB-106": make_issue("XMKFB-106", {
            "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")}),
            "XMKFB-107": make_issue("XMKFB-107", {
                "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})}
        stub = FakeJira(
            get_issue=snapshot,
            put={"XMKFB-106": client.JiraError("RATE_LIMITED",
                                               "被 Jira 限流 (HTTP 429)，重试一次后仍失败")})
        report, _ = run_execute(stub, make_plan([first, second]))

        self.assertEqual(item_of(report, "XMKFB-106")["result"], "failed",
                         "429 重试后仍失败的条目记失败")
        self.assertEqual(item_of(report, "XMKFB-107")["result"], "success",
                         "不得熔断：后续条目必须继续处理")
        self.assertEqual(len(stub.puts("XMKFB-107")), 1, "第 2 条的写请求必须真的发出去")
        self.assertIn("rate_limit", report, "报告须带 rate_limit 结构（契约 §6.1）")
        self.assertIn("count", report["rate_limit"])
        self.assertIn("retry_after_seconds", report["rate_limit"])

    def test_apply阶段直接读plan里的绝对日期不重算(self):
        # 模拟「预览与执行之间跨了零点」：plan 里的 base_date 是昨天，
        # 但写入值必须逐字等于 plan 里已算好的 duedate，绝不允许按执行时刻重算。
        item = make_item(
            "XMKFB-108",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", None, "2026-08-11",
                                        "2026-08-11（周二）")],
            before={"duedate": None, "status": status_value("10000", "待办", "new")})
        stub = FakeJira(get_issue={"XMKFB-108": make_issue("XMKFB-108", {
            "duedate": None, "status": status_value("10000", "待办", "new")})})
        report, _ = run_execute(stub, make_plan([item], base_date="2026-08-10"))

        self.assertEqual(item_of(report, "XMKFB-108")["result"], "success")
        self.assertEqual(len(stub.puts("XMKFB-108")), 1, "字段写请求只发一次")
        self.assertEqual(stub.puts("XMKFB-108")[0]["body"],
                         {"fields": {"duedate": "2026-08-11"}},
                         "PUT 载荷必须与 plan 逐字一致，执行期不得重新换算日期")


class UpdateRecheckScopeTest(unittest.TestCase):
    """复核键集合边界：status 只在本次带 --status 时才参与比对。"""

    def test_只改duedate时状态变化不导致跳过(self):
        item = make_item(
            "XMKFB-201",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20",
                    "status": status_value("10000", "待办", "new")},
            status_change=None)  # 本次不改状态
        stub = FakeJira(get_issue={"XMKFB-201": make_issue("XMKFB-201", {
            "duedate": "2026-08-20",
            "status": status_value("3", "进行中", "indeterminate")})})  # 状态被他人推过
        report, _ = run_execute(stub, make_plan([item]))

        entry = item_of(report, "XMKFB-201")
        self.assertEqual(entry["result"], "success",
                         "本次不改状态时，状态变化不属于抢改，不应跳过")
        self.assertEqual(len(stub.puts("XMKFB-201")), 1, "字段写请求必须照发")

    def test_带status时状态id变化导致跳过(self):
        item = make_item(
            "XMKFB-202",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20",
                    "status": status_value("10000", "待办", "new")},
            status_change={"from_id": "10000", "from_name": "待办", "to_name": "已完成",
                           "reachability": "direct", "auto_filled": []})
        stub = FakeJira(
            get_issue={"XMKFB-202": make_issue("XMKFB-202", {
                "duedate": "2026-08-20",
                "status": status_value("3", "进行中", "indeterminate")})},
            transitions={"XMKFB-202": [{"transitions": [
                make_transition("21", "完成", "10002", "已完成", "done")]}]})
        report, _ = run_execute(stub, make_plan([item]))

        entry = item_of(report, "XMKFB-202")
        self.assertEqual(entry["result"], "skipped",
                         "本次要推状态时，status.id 变化属于抢改，必须跳过")
        self.assertIn("他人已改动", entry["reason"])
        self.assertEqual(stub.puts(), [], "抢改跳过不得发写请求")
        self.assertEqual(stub.transition_posts(), [], "抢改跳过不得发流转请求")


class UpdateReportTest(unittest.TestCase):
    """报告契约：三分统计、resume_keys 口径。"""

    def _mixed_report(self):
        ok = make_item(
            "XMKFB-301",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})
        grabbed = make_item(
            "XMKFB-302",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})
        idempotent = make_item(
            "XMKFB-303",
            put_payload={},
            before={"status": status_value("10002", "已完成", "done")},
            no_change=True)
        failed = make_item(
            "XMKFB-304",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})
        stub = FakeJira(
            get_issue={
                "XMKFB-301": make_issue("XMKFB-301", {
                    "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")}),
                "XMKFB-302": make_issue("XMKFB-302", {
                    "duedate": "2026-08-25", "status": status_value("10000", "待办", "new")}),
                "XMKFB-303": make_issue("XMKFB-303", {
                    "status": status_value("10002", "已完成", "done")}),
                "XMKFB-304": make_issue("XMKFB-304", {
                    "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")}),
            },
            put={"XMKFB-304": client.JiraError("PERMISSION_DENIED", "权限不足 (HTTP 403)")})
        return run_execute(stub, make_plan([ok, grabbed, idempotent, failed]))[0]

    def test_三分统计正确(self):
        report = self._mixed_report()
        self.assertEqual(report["counts"],
                         {"success": 1, "skipped": 2, "failed": 1},
                         "三分统计必须逐条对齐执行结果")
        self.assertTrue(report["has_failures"], "存在失败条目时 has_failures 必须为真")

    def test_resume_keys只收失败与抢改跳过(self):
        report = self._mixed_report()
        self.assertEqual(sorted(report["resume_keys"]), ["XMKFB-302", "XMKFB-304"],
                         "resume_keys = 失败条目 ∪ 抢改跳过条目")
        self.assertNotIn("XMKFB-303", report["resume_keys"],
                         "幂等跳过（值已是目标值）不进 resume_keys，补做没有意义")
        self.assertNotIn("XMKFB-301", report["resume_keys"], "成功条目不进 resume_keys")


class UpdateAuditTest(unittest.TestCase):
    """审计：逐条追加、正文字段不截断、其余字段超限截断。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.audit_log = os.path.join(self.dir, "audit.log")

    def _read_audit(self):
        if not os.path.isfile(self.audit_log):
            return []
        with open(self.audit_log, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_审计逐条追加而不是批末统一写(self):
        items = []
        snapshot = {}
        for n in (1, 2, 3):
            key = "XMKFB-40%d" % n
            items.append(make_item(
                key,
                put_payload={"duedate": "2026-08-11"},
                field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
                before={"duedate": "2026-08-20",
                        "status": status_value("10000", "待办", "new")}))
            snapshot[key] = make_issue(key, {
                "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})

        seen = {"第二条开始时的审计条数": None}

        def hook(method, path, body):
            if _key_from_path(path) == "XMKFB-402" and seen["第二条开始时的审计条数"] is None:
                seen["第二条开始时的审计条数"] = len(self._read_audit())

        stub = FakeJira(get_issue=snapshot, hook=hook)
        run_execute(stub, make_plan(items),
                    audit_fn=lambda record: planmod.audit(self.audit_log, record))

        self.assertEqual(seen["第二条开始时的审计条数"], 1,
                         "处理第 2 条时，第 1 条的审计必须已经落盘（逐条追加，不能批末统一写）")
        self.assertEqual(len(self._read_audit()), 3, "3 条单应留下 3 条审计")

    def test_正文字段旧值全文写入且其余字段超限截断(self):
        # 说明：这里用 duedate 承载超长旧值，只是为了触发「按字符数截断」这条规则
        # （规则与字段业务含义无关），不代表真实数据形态。
        long_summary = "甲" * 2600
        long_duedate = "乙" * 2600
        item = make_item(
            "XMKFB-405",
            put_payload={"summary": "新标题", "duedate": "2026-08-11"},
            field_changes=[
                field_change("summary", "标题", long_summary, "新标题"),
                field_change("duedate", "截止日期", long_duedate, "2026-08-11"),
            ],
            before={"summary": long_summary, "duedate": long_duedate,
                    "status": status_value("10000", "待办", "new")})
        stub = FakeJira(get_issue={"XMKFB-405": make_issue("XMKFB-405", {
            "summary": long_summary, "duedate": long_duedate,
            "status": status_value("10000", "待办", "new")})})
        _, records = run_execute(stub, make_plan([item]))

        self.assertEqual(len(records), 1, "单条 issue 应产出 1 条审计记录")
        record = records[0]
        self.assertEqual(record.get("action"), "update", "审计须标明动作为 update")
        self.assertEqual(record.get("key"), "XMKFB-405")

        summary_rec = find_field_record(record, "summary", "标题")
        self.assertIsNotNone(summary_rec, "审计里应能找到 summary 的字段记录")
        self.assertEqual(_as_text(summary_rec["old"]), long_summary,
                         "summary 旧值必须全文写入、不得截断")
        self.assertFalse(summary_rec.get("truncated"), "summary 不参与截断，不应带 truncated 标记")

        duedate_rec = find_field_record(record, "duedate", "截止日期")
        self.assertIsNotNone(duedate_rec, "审计里应能找到 duedate 的字段记录")
        self.assertTrue(duedate_rec.get("truncated"),
                        "summary/description 之外的字段旧值超 %d 字符必须截断"
                        % update_fields.AUDIT_TRUNCATE_LIMIT)
        self.assertEqual(duedate_rec.get("length"), len(long_duedate),
                         "length 应记原始旧值的字符数")
        self.assertEqual(duedate_rec.get("sha1"),
                         hashlib.sha1(long_duedate.encode("utf-8")).hexdigest()[:8],
                         "sha1 取原始旧值摘要的前 8 位")
        self.assertLessEqual(len(_as_text(duedate_rec["old"])),
                             update_fields.AUDIT_TRUNCATE_LIMIT,
                             "截断后落盘的旧值长度不得超过上限")


class ApplyUpdateGateTest(unittest.TestCase):
    """apply 前置门禁与整批退出码（走 CLI，验的是对外契约）。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.config_path = os.path.join(self.dir, "config.json")
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f)
        self.plans_dir = os.path.join(self.dir, "plans")
        self.audit_log = os.path.join(self.dir, "audit.log")
        # 前置假设显式化：白名单放行 Jira1 与 Jira2
        self.assertIn("Jira2", update_fields.WRITE_ALLOWED_SOURCES,
                      "本用例假设 Jira2 在写白名单内")
        self.assertIn("Jira1", update_fields.WRITE_ALLOWED_SOURCES,
                      "本用例假设 Jira1 在写白名单内")

    def _apply(self, payload, stub=None, argv_extra=None):
        stub = stub if stub is not None else FakeJira()
        with mock.patch.object(jira_cli, "PLANS_DIR", self.plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", self.audit_log), \
             mock.patch.object(client, "request", new=stub):
            created = planmod.create_plan(self.plans_dir, payload, ttl_seconds=900)
            argv = ["--config", self.config_path]
            argv.extend(argv_extra or [])
            argv.extend(["apply", "--plan-id", created["plan_id"]])
            code, out = run_cli(argv)
        return code, out, stub

    def test_未知action仍返回PLAN_REJECTED(self):
        code, out, stub = self._apply({"action": "unknown_action", "source": "Jira2", "items": []})
        self.assertEqual(code, 1, "未知 plan 动作退出码为 1")
        self.assertEqual(out["error_code"], "PLAN_REJECTED",
                         "动作白名单之外一律 PLAN_REJECTED，不得自造新错误码")
        self.assertEqual(stub.calls, [], "被拒的 plan 不得发出任何请求")

    def test_update计划缺必需字段返回PLAN_MALFORMED(self):
        # 缺 items：结构校验必须在联网之前拦下
        code, out, stub = self._apply({"action": "update", "source": "Jira2"})
        self.assertEqual(code, 1, "计划结构不合法退出码为 1")
        self.assertEqual(out["error_code"], "PLAN_MALFORMED")
        self.assertEqual(stub.calls, [], "结构校验不通过不得发出任何请求")

    def test_plan里的源不在写白名单时apply被拒(self):
        # 关键：argv 不带 --source，配置的 default_source 是被允许的 Jira2，
        # 只有当判据取自 plan["source"]（Jira3）时本用例才会通过。
        code, out, stub = self._apply(
            {"action": "update", "source": "Jira3", "items": [
                make_item("XMKFB-501", put_payload={"duedate": "2026-08-11"})]})
        self.assertEqual(code, 2, "写源不被允许属参数级拒绝，退出码 2")
        self.assertEqual(out["error_code"], "WRITE_SOURCE_NOT_ALLOWED",
                         "写源准入判据必须取 plan 里的源名，不是 args.source、也不是 default_source")
        self.assertEqual(stub.calls, [], "写源不被允许时零网络请求")

    def test_有失败条目仍ok为真且退出码0(self):
        ok = make_item(
            "XMKFB-502",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})
        bad = make_item(
            "XMKFB-503",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})
        stub = FakeJira(
            get_issue={
                "XMKFB-502": make_issue("XMKFB-502", {
                    "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")}),
                "XMKFB-503": make_issue("XMKFB-503", {
                    "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")}),
            },
            put={"XMKFB-503": client.JiraError("JQL_INVALID",
                                               "请求被 Jira 拒绝 (HTTP 400): 字段不可编辑")})
        code, out, _ = self._apply(
            {"action": "update", "source": "Jira2", "base_url": "http://jira.local",
             "complete_set_declared": True, "allow_closed_transition": False,
             "base_date": "2026-08-10", "items": [ok, bad],
             "totals": {"issues": 2}},
            stub=stub)

        self.assertEqual(code, 0, "整批跑完无论逐条成败，退出码恒为 0")
        self.assertTrue(out["ok"], "整批跑完 ok 必须为 true，失败只体现在报告里")
        self.assertEqual(out["stage"], "applied")
        self.assertEqual(out["action"], "update")
        self.assertTrue(out["has_failures"], "有失败条目时 has_failures 为 true")
        self.assertEqual(out["counts"], {"success": 1, "skipped": 0, "failed": 1})
        head = out["result_text"].splitlines()[:2]
        # 契约 §4.2：第 1 行是「操作源：<源名>」，第 2 行是三分统计行
        self.assertTrue(any("失败 1 条" in line for line in head),
                        "result_text 首部必须直白写出失败条数，实际首部：%s" % head)
        self.assertIn("成功 1 条 / 跳过 0 条 / 失败 1 条", out["result_text"],
                      "三分统计行文案须逐字对齐契约（三个数字恒出现）")

    def test_某条抛403异常整批仍继续且退出码0(self):
        first = make_item(
            "XMKFB-504",
            put_payload={"duedate": "2026-08-11"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-11")],
            before={"duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})
        second = make_item(
            "XMKFB-505",
            put_payload={"duedate": "2026-08-12"},
            field_changes=[field_change("duedate", "截止日期", "2026-08-20", "2026-08-12")],
            before={"duedate": "2026-08-20", "status": status_value("10000", "待办", "new")})
        stub = FakeJira(
            get_issue={
                "XMKFB-504": make_issue("XMKFB-504", {
                    "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")}),
                "XMKFB-505": make_issue("XMKFB-505", {
                    "duedate": "2026-08-20", "status": status_value("10000", "待办", "new")}),
            },
            put={"XMKFB-504": client.JiraError("PERMISSION_DENIED", "权限不足 (HTTP 403)",
                                               "确认该账号对目标项目/操作有权限")})
        code, out, stub = self._apply(
            {"action": "update", "source": "Jira2", "base_url": "http://jira.local",
             "complete_set_declared": True, "allow_closed_transition": False,
             "base_date": "2026-08-10", "items": [first, second],
             "totals": {"issues": 2}},
            stub=stub)

        self.assertEqual(code, 0, "单条 403 绝不允许穿透到 main 把整批退出码变成 1")
        self.assertTrue(out["ok"])
        self.assertEqual(out["counts"]["failed"], 1)
        self.assertEqual(out["counts"]["success"], 1, "403 之后的条目必须继续处理")
        self.assertEqual(len(stub.puts("XMKFB-505")), 1, "后续条目的写请求必须真的发出去")
        failed = [i for i in out["items"] if i["key"] == "XMKFB-504"][0]
        self.assertIn("权限不足", failed["reason"], "失败原因回带 Jira 原文")
        self.assertNotIn("PERMISSION_DENIED", failed["reason"],
                         "逐条失败原因不得显示 error_code 名")


# ---------------------------------------------------------------- client 空体

class FakeHeaders:
    def __init__(self, d):
        self._d = d

    def get(self, key, default=None):
        for k, v in self._d.items():
            if k.lower() == key.lower():
                return v
        return default

    def keys(self):
        return self._d.keys()


class FakeResponse:
    """桩响应，写法照抄 tests/test_client.py（同样没有 status 属性）。"""

    def __init__(self, body, content_type="application/json;charset=UTF-8"):
        self._body = body.encode("utf-8")
        self.headers = FakeHeaders({"Content-Type": content_type})

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ClientEmptyBodyTest(unittest.TestCase):
    """PUT /issue 与 POST transitions 成功时返回 204 无体，client 必须当成功处理。"""

    def _request(self, response):
        with mock.patch("urllib.request.urlopen", return_value=response):
            return client.request(SOURCE, "PUT", "/rest/api/2/issue/XMKFB-1",
                                  body={"fields": {"duedate": "2026-08-11"}})

    def test_空体成功响应返回空dict(self):
        # 204 常常连 Content-Type 都不带，必须按 body 判空，不能依赖 resp.status
        result = self._request(FakeResponse("", ""))
        self.assertEqual(result, {}, "成功但响应体为空时应返回空 dict，不得抛异常")

    def test_只有空白的响应体也算空体(self):
        result = self._request(FakeResponse("\n  \n", ""))
        self.assertEqual(result, {}, "只含空白的响应体同样按空体处理")

    def test_非空但非JSON仍报UNEXPECTED_RESPONSE(self):
        with self.assertRaises(client.JiraError) as cm:
            self._request(FakeResponse("<html>login</html>", "text/html"))
        self.assertEqual(cm.exception.error_code, "UNEXPECTED_RESPONSE",
                         "空体放行不得放宽 HTML 拦截：非空非 JSON 仍须报错")
        self.assertIn("<html>", cm.exception.error, "应回带响应前 200 字符")

    def test_apply_update_带出audit_errors(self):
        import io
        import contextlib
        import jira_cli
        import plan as planmod

        cfg = {"sources": [{"name": "Jira1", "base_url": "http://fake.invalid", "username": "u", "password": "p"}]}
        payload = {
            "plan_id": "plan_00000000",
            "action": "update",
            "source": "Jira1",
            "base_url": "http://fake.invalid",
            "items": [{"key": "TEST-1", "before": {"labels": []}, "put_payload": {"labels": ["new"]}}]
        }
        buf = io.StringIO()
        with mock.patch("client.request", return_value={"fields": {"labels": []}}), \
             mock.patch.object(planmod, "audit", side_effect=OSError("audit disk full")), \
             contextlib.redirect_stdout(buf):
            code = jira_cli._apply_update(payload, cfg)
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertTrue(out["ok"])
        self.assertIn("audit_errors", out)
        self.assertEqual(len(out["audit_errors"]), 1)
        self.assertIn("audit disk full", out["audit_errors"][0])
        self.assertIn("警告（审计落盘失败）", out["result_text"])


if __name__ == "__main__":
    unittest.main()
