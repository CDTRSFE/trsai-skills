# -*- coding: utf-8 -*-
"""paging.py 测试：分页游标推进、截断标记、双路径分组计数。

用 StubClient 替代 client 模块，手工构造响应样本（不含真实业务数据）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import client
import paging


def make_issues(start, count):
    return [{"key": "T-%d" % i, "fields": {"summary": "s%d" % i}}
            for i in range(start, start + count)]


class StubClient:
    """按队列返回响应，并记录每次请求参数。JiraError 透传 client 模块的。"""

    JiraError = client.JiraError

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def request(self, source, method, path, body=None):
        self.calls.append({"method": method, "path": path, "body": body})
        return self.handler(method, path, body)


SOURCE = client.normalize_source({
    "name": "t", "base_url": "http://jira.local", "username": "u", "password": "p",
    "max_results_per_page": 50, "hard_result_limit": 500,
    "aggregate_scan_limit": 5000, "total_deadline_seconds": 120,
})


class TestSearchPaging(unittest.TestCase):
    def test_游标按实际返回条数推进(self):
        """服务端钳位只返回 30 条时，第二页 startAt 必须是 30 而非 50。"""
        pages = {
            0: {"issues": make_issues(0, 30), "total": 70},
            30: {"issues": make_issues(30, 40), "total": 70},
        }
        stub = StubClient(lambda m, p, b: pages[b["startAt"]])
        result = paging.search(stub, SOURCE, "project = T")
        self.assertEqual(result["returned"], 70)
        self.assertFalse(result["truncated"])
        starts = [c["body"]["startAt"] for c in stub.calls]
        self.assertEqual(starts, [0, 30], "startAt 必须按实际返回条数推进")

    def test_跨页数据全部计入(self):
        pages = {
            0: {"issues": make_issues(0, 50), "total": 80},
            50: {"issues": make_issues(50, 30), "total": 80},
        }
        stub = StubClient(lambda m, p, b: pages[b["startAt"]])
        result = paging.search(stub, SOURCE, "project = T")
        keys = [i["key"] for i in result["issues"]]
        self.assertIn("T-79", keys, "第 2 页的记录必须被计入")

    def test_硬上限截断标记(self):
        source = dict(SOURCE, hard_result_limit=100)
        stub = StubClient(lambda m, p, b: {"issues": make_issues(b["startAt"], b["maxResults"]),
                                           "total": 1832})
        result = paging.search(stub, source, "project = T")
        self.assertTrue(result["truncated"], "超过硬上限必须显式标注截断")
        self.assertEqual(result["returned"], 100)
        self.assertEqual(result["truncated_reason"], "hard_result_limit")

    def test_用户limit截断(self):
        stub = StubClient(lambda m, p, b: {"issues": make_issues(b["startAt"], b["maxResults"]),
                                           "total": 500})
        result = paging.search(stub, SOURCE, "project = T", limit=10)
        self.assertEqual(result["returned"], 10)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["truncated_reason"], "limit")

    def test_空结果(self):
        stub = StubClient(lambda m, p, b: {"issues": [], "total": 0})
        result = paging.search(stub, SOURCE, "project = T")
        self.assertEqual(result["total_in_jira"], 0)
        self.assertFalse(result["truncated"])


class TestCountBy(unittest.TestCase):
    def test_可枚举维度走计数查询不拉明细(self):
        def handler(method, path, body):
            if path == "/rest/api/2/status":
                return [{"id": "1", "name": "待办"}, {"id": "2", "name": "完成"}]
            if body and body.get("maxResults") == 0:
                return {"total": 7 if "status = 1" in body["jql"] else 3}
            raise AssertionError("count_query 路径不应拉取明细: %s" % body)
        stub = StubClient(handler)
        result = paging.count_by(stub, SOURCE, "project = T", "status")
        self.assertEqual(result["method"], "count_query")
        self.assertEqual(result["total_in_jira"], 10)
        self.assertEqual(result["groups"], [{"key": "待办", "count": 7},
                                            {"key": "完成", "count": 3}])
        self.assertTrue(all(c["body"] is None or c["body"].get("maxResults") == 0
                            for c in stub.calls))
        jqls = [c["body"]["jql"] for c in stub.calls if c["body"]]
        self.assertTrue(all("status = 1" in j or "status = 2" in j for j in jqls),
                        "JQL 必须用状态 id 而非本地化显示名（防中文语言包 400）")

    def test_fixVersion_单独查真实总数(self):
        def handler(method, path, body):
            if path == "/rest/api/2/project/T/versions":
                return [{"name": "v1.0"}, {"name": "v2.0"}]
            if body and body.get("maxResults") == 0:
                if body.get("jql") == "project = T":
                    return {"total": 5}
                return {"total": 4}
            raise AssertionError("不应拉取明细: %s" % body)
        stub = StubClient(handler)
        result = paging.count_by(stub, SOURCE, "project = T", "fixVersion")
        self.assertEqual(result["total_in_jira"], 5, "fixVersion 必须查基线真实总数而非简单累加")

    def test_assignee扫描_空值归入未分配(self):
        batch = [{"key": "T-1", "fields": {"assignee": {"displayName": "张三"}}},
                 {"key": "T-2", "fields": {"assignee": None}}]
        stub = StubClient(lambda m, p, b: {"issues": batch, "total": 2})
        result = paging.count_by(stub, SOURCE, "project = T", "assignee")
        self.assertEqual(result["method"], "scan")
        groups = {g["key"]: g["count"] for g in result["groups"]}
        self.assertEqual(groups.get("(未分配)"), 1, "assignee 为 null 应归入(未分配)")
        self.assertEqual(groups.get("张三"), 1)

    def test_扫描超限返回partial(self):
        source = dict(SOURCE, aggregate_scan_limit=60)
        stub = StubClient(lambda m, p, b: {"issues": make_issues(b["startAt"], b["maxResults"]),
                                           "total": 500})
        result = paging.count_by(stub, source, "project = T", "assignee")
        self.assertTrue(result["partial"], "超 aggregate_scan_limit 必须 partial: true")
        self.assertEqual(result["scanned"], 60)

    def test_fixVersion需要project(self):
        stub = StubClient(lambda m, p, b: [])
        with self.assertRaises(client.JiraError):
            paging.count_by(stub, SOURCE, "status = Open", "fixVersion")

    def test_count_by_带有orderby子句安全剥离(self):
        def handler(method, path, body):
            if path == "/rest/api/2/status":
                return [{"id": "1", "name": "待办"}, {"id": "2", "name": "完成"}]
            if body and body.get("maxResults") == 0:
                jql = body.get("jql", "")
                self.assertNotIn("ORDER BY", jql)
                self.assertNotIn("order by", jql)
                return {"total": 3}
            raise AssertionError("不应拉取明细: %s" % body)
        stub = StubClient(handler)
        result = paging.count_by(stub, SOURCE, "project = TEST ORDER BY updated DESC", "status")
        self.assertEqual(result["method"], "count_query")
        self.assertTrue(all("ORDER BY" not in c["body"]["jql"] for c in stub.calls if c["body"]))


if __name__ == "__main__":
    unittest.main()
