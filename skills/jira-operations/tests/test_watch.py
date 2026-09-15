# -*- coding: utf-8 -*-
"""watch 命令测试：增量三态、JQL 变更保护、--peek 不标记、名称消毒。"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import jira_cli

CONFIG = {
    "default_source": "主",
    "sources": [{"name": "主", "base_url": "http://jira.local",
                 "username": "u", "password": "p"}],
}

ISSUES = [{"key": "T-1", "fields": {"summary": "甲"}},
          {"key": "T-2", "fields": {"summary": "乙"}}]


def run_watch(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = jira_cli.main(argv)
    text = buf.getvalue().strip()
    return code, json.loads(text) if text else None


class TestWatch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.config_path = os.path.join(self.dir, "config.json")
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f)
        self.watch_dir = os.path.join(self.dir, "watch")
        patcher = mock.patch.object(jira_cli, "WATCH_DIR", self.watch_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        req = mock.patch("client.request", return_value={"issues": ISSUES, "total": 2})
        req.start()
        self.addCleanup(req.stop)

    def _argv(self, name, jql="project = T", extra=None):
        return ["--config", self.config_path, "watch",
                "--jql", jql, "--name", name] + (extra or [])

    def test_三态(self):
        code, out = run_watch(self._argv("逾期任务"))
        self.assertEqual(out["new_count"], 2, "首次应全返")
        code, out = run_watch(self._argv("逾期任务"))
        self.assertEqual(out["new_count"], 0, "第二次应无新增")
        code, out = run_watch(self._argv("逾期任务"))
        self.assertEqual(out["new_count"], 0)

    def test_peek不标记(self):
        run_watch(self._argv("监控A", extra=["--peek"]))
        code, out = run_watch(self._argv("监控A"))
        self.assertEqual(out["new_count"], 2, "--peek 只看不标记已见")

    def test_jql变更保护(self):
        run_watch(self._argv("监控B", jql="project = T"))
        code, out = run_watch(self._argv("监控B", jql="project = X"))
        self.assertEqual(code, 2)
        self.assertEqual(out["error_code"], "WATCH_JQL_CHANGED",
                         "同名换 JQL 必须报错要求 --reset")
        code, out = run_watch(self._argv("监控B", jql="project = X", extra=["--reset"]))
        self.assertEqual(code, 0, "--reset 后应可用新 JQL")

    def test_名称消毒(self):
        code, out = run_watch(self._argv("../etc/passwd"))
        self.assertEqual(code, 0)
        files = os.listdir(self.watch_dir)
        self.assertEqual(len(files), 1)
        self.assertNotIn("..", files[0], "watch 名称不得产生路径穿越")

    def test_state损坏降级不崩(self):
        os.makedirs(self.watch_dir, exist_ok=True)
        import hashlib
        name = "损坏监控"
        fname = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12] + ".json"
        with open(os.path.join(self.watch_dir, fname), "w") as f:
            f.write("{broken json")
        code, out = run_watch(self._argv(name))
        self.assertEqual(code, 0, "state 文件损坏时应降级为空状态继续")
        self.assertEqual(out["new_count"], 2)


if __name__ == "__main__":
    unittest.main()
