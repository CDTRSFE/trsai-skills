# -*- coding: utf-8 -*-
"""plan.py 测试：两阶段门禁三态、并发归属、审计双路径。"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import plan


class TestPlanGate(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _create(self, ttl=300):
        return plan.create_plan(self.dir, {"action": "create", "fields": {"summary": "s"}},
                                ttl_seconds=ttl)

    def test_创建并消费成功(self):
        p = self._create()
        loaded = plan.consume_plan(self.dir, p["plan_id"])
        self.assertEqual(loaded["plan_id"], p["plan_id"])
        consumed = os.path.join(self.dir, p["plan_id"] + ".consumed.json")
        self.assertTrue(os.path.isfile(consumed), "apply 后应 rename 为 consumed")

    def test_过期拒绝(self):
        p = self._create(ttl=-1)
        with self.assertRaises(plan.PlanRejected) as cm:
            plan.consume_plan(self.dir, p["plan_id"])
        self.assertIn("已过期", str(cm.exception))

    def test_重复使用拒绝(self):
        p = self._create()
        plan.consume_plan(self.dir, p["plan_id"])
        with self.assertRaises(plan.PlanRejected) as cm:
            plan.consume_plan(self.dir, p["plan_id"])
        self.assertIn("已被使用", str(cm.exception))

    def test_不存在拒绝(self):
        with self.assertRaises(plan.PlanRejected) as cm:
            plan.consume_plan(self.dir, "plan_00000000")
        self.assertIn("不存在", str(cm.exception))

    def test_非法id拒绝(self):
        with self.assertRaises(plan.PlanRejected):
            plan.consume_plan(self.dir, "../etc/passwd")

    def test_并发apply恰有一次成功(self):
        p = self._create()
        results = []

        def worker():
            try:
                plan.consume_plan(self.dir, p["plan_id"])
                results.append("ok")
            except plan.PlanRejected:
                results.append("rejected")

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), ["ok", "rejected"],
                         "同一 plan 并发 apply 恰有一次成功")

    def test_审计双路径(self):
        log = os.path.join(self.dir, "audit.log")
        plan.audit(log, {"action": "create", "result": "success", "issue_key": "T-1"})
        plan.audit(log, {"action": "apply", "result": "rejected", "reason": "已过期"})
        with open(log, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 2, "成功与被拒两种情况都必须写审计日志")
        self.assertEqual(lines[0]["result"], "success")
        self.assertEqual(lines[1]["result"], "rejected")
        self.assertIn("ts", lines[0])


if __name__ == "__main__":
    unittest.main()
