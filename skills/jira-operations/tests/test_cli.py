# -*- coding: utf-8 -*-
"""jira_cli.py 测试：输出契约 catch-all、退出码 0/1/2、create 预览门禁。

HTTP 打桩 client.request，不连真 Jira。
"""
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

import client
import jira_cli

CONFIG = {
    "default_source": "主",
    "sources": [{"name": "主", "base_url": "http://jira.local",
                 "username": "u", "password": "p"}],
}


def run_cli(argv):
    """跑 main 并捕获 stdout，返回 (退出码, 解析后的 JSON)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = jira_cli.main(argv)
    text = buf.getvalue().strip()
    return code, json.loads(text) if text else None


class TestCliContract(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.config_path = os.path.join(self.dir, "config.json")
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f)

    def test_成功退出码0(self):
        with mock.patch("client.request",
                        return_value={"name": "u", "displayName": "用户"}):
            code, out = run_cli(["--config", self.config_path, "whoami"])
        self.assertEqual(code, 0, "成功退出码应为 0")
        self.assertTrue(out["ok"])
        self.assertIn("script_version", out, "whoami 应回带脚本版本号")

    def test_配置错误退出码2(self):
        code, out = run_cli(["--config", "/nonexistent/x.json", "whoami"])
        self.assertEqual(code, 2, "配置错误退出码应为 2")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error_code"], "CONFIG_ERROR")
        self.assertIn("hint", out)

    def test_业务失败退出码1(self):
        with mock.patch("client.request",
                        side_effect=client.JiraError("NOT_FOUND", "不存在", "检查 key")):
            code, out = run_cli(["--config", self.config_path, "get", "T-1"])
        self.assertEqual(code, 1, "业务失败退出码应为 1")
        self.assertEqual(out["error_code"], "NOT_FOUND")

    def test_catch_all输出合法JSON(self):
        with mock.patch("client.load_config", side_effect=RuntimeError("boom")):
            code, out = run_cli(["--config", self.config_path, "whoami"])
        self.assertIsNotNone(out, "未预期异常时 stdout 仍必须是合法 JSON")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error_code"], "INTERNAL_ERROR")
        self.assertEqual(code, 1)

    def test_create无preview拒绝(self):
        code, out = run_cli(["--config", self.config_path, "create",
                             "--project", "T", "--type", "任务", "--summary", "x"])
        self.assertEqual(code, 2)
        self.assertEqual(out["error_code"], "PREVIEW_REQUIRED",
                         "create 不带 --preview 必须拒绝")

    def test_create_preview生成plan(self):
        plans_dir = os.path.join(self.dir, "plans")
        meta = {"projects": [{"issuetypes": [{"fields": {
            "summary": {"required": True, "name": "摘要"}}}]}]}
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch("client.request", return_value=meta):
            code, out = run_cli(["--config", self.config_path, "create",
                                 "--project", "T", "--type", "任务",
                                 "--summary", "测试", "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "preview")
        self.assertTrue(out["plan_id"].startswith("plan_"))
        self.assertTrue(os.path.isfile(os.path.join(plans_dir, out["plan_id"] + ".json")),
                        "preview 应落盘 plan 文件")

    def test_create_缺必填字段报错(self):
        meta = {"projects": [{"issuetypes": [{"fields": {
            "summary": {"required": True, "name": "摘要"},
            "customfield_10001": {"required": True, "name": "需求来源"}}}]}]}
        with mock.patch("client.request", return_value=meta):
            code, out = run_cli(["--config", self.config_path, "create",
                                 "--project", "T", "--type", "任务",
                                 "--summary", "x", "--preview"])
        self.assertEqual(code, 2)
        self.assertEqual(out["error_code"], "MISSING_REQUIRED_FIELDS",
                         "必填字段缺失必须直接报错")
        self.assertIn("customfield_10001", out["error"])

    def test_apply_不存在plan拒绝并记审计(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        os.makedirs(plans_dir)
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log):
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", "plan_00000000"])
        self.assertEqual(code, 1)
        self.assertEqual(out["error_code"], "PLAN_REJECTED")
        with open(audit_log, encoding="utf-8") as f:
            entries = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(entries), 1, "被拒的 apply 也必须写审计日志")
        self.assertEqual(entries[0]["result"], "rejected")

    def test_create_子任务_自动识别parent与project(self):
        plans_dir = os.path.join(self.dir, "plans")
        meta = {"projects": [{"issuetypes": [{"fields": {
            "summary": {"required": True, "name": "摘要"}}}]}]}
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch("client.request", return_value=meta):
            code, out = run_cli(["--config", self.config_path, "create",
                                 "--parent", "XMKFB-12099",
                                 "--summary", "需要后端支持", "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "preview")
        plan_path = os.path.join(plans_dir, out["plan_id"] + ".json")
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
        self.assertEqual(plan["project"], "XMKFB")
        self.assertEqual(plan["type"], "子任务")
        self.assertEqual(plan["fields"]["parent"], {"key": "XMKFB-12099"})

    def test_comment_preview与apply(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "comment",
                                 "--key", "TRS-123", "--body", "这是备注", "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "preview")
        plan_id = out["plan_id"]

        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log), \
             mock.patch("client.request", return_value={"id": "10001"}):
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", plan_id])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "applied")
        self.assertEqual(out["action"], "comment")
        self.assertEqual(out["comment_id"], "10001")

    def test_assign_preview与apply(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "assign",
                                 "--key", "TRS-123", "--to", "zhangsan", "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "preview")
        plan_id = out["plan_id"]

        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log), \
             mock.patch("client.request", return_value={}) as req:
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", plan_id])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "applied")
        self.assertEqual(out["assignee"], "zhangsan")
        req.assert_called_once()

    def test_link_preview与apply(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "link",
                                 "--inward", "TRS-1", "--outward", "TRS-2",
                                 "--type", "Blocks", "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "preview")
        plan_id = out["plan_id"]

        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log), \
             mock.patch("client.request", return_value={}) as req:
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", plan_id])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "applied")
        self.assertEqual(out["type"], "Blocks")

    def test_worklog_preview与apply(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "worklog",
                                 "--key", "TRS-1", "--time", "2h",
                                 "--comment", "修复缺陷", "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "preview")
        plan_id = out["plan_id"]

        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log), \
             mock.patch("client.request", return_value={"id": "50001"}):
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", plan_id])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "applied")
        self.assertEqual(out["worklog_id"], "50001")

    def test_delete_preview与apply(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "delete",
                                 "--key", "TRS-999", "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "preview")
        plan_id = out["plan_id"]

        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log), \
             mock.patch("client.request", return_value={}) as req:
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", plan_id])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "applied")
        self.assertEqual(out["action"], "delete")
        req.assert_called_once()

    def test_api_get_直接执行(self):
        with mock.patch("client.request", return_value={"watchCount": 3}) as req:
            code, out = run_cli(["--config", self.config_path, "api",
                                 "--path", "/rest/api/2/issue/TRS-1/watchers"])
        self.assertEqual(code, 0)
        self.assertEqual(out["ok"], True)
        self.assertEqual(out["action"], "api")
        self.assertEqual(out["response"], {"watchCount": 3})
        req.assert_called_once()

    def test_api_post_无preview报PREVIEW_REQUIRED(self):
        code, out = run_cli(["--config", self.config_path, "api",
                             "--method", "POST",
                             "--path", "/rest/api/2/issue/TRS-1/watchers",
                             "--data", '{"name": "zhangsan"}'])
        self.assertEqual(code, 2)
        self.assertEqual(out["error_code"], "PREVIEW_REQUIRED")

    def test_api_post_preview与apply(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "api",
                                 "--method", "POST",
                                 "--path", "/rest/api/2/issue/TRS-1/watchers",
                                 "--data", '{"name": "zhangsan"}',
                                 "--preview"])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "preview")
        plan_id = out["plan_id"]

        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log), \
             mock.patch("client.request", return_value={"ok": 1}) as req:
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", plan_id])
        self.assertEqual(code, 0)
        self.assertEqual(out["stage"], "applied")
        self.assertEqual(out["action"], "api")
        req.assert_called_once()

    def test_createmeta_无type列出可用类型(self):
        meta = {"projects": [{"issuetypes": [
            {"id": "1", "name": "任务", "subtask": False},
            {"id": "2", "name": "子任务", "subtask": True}
        ]}]}
        with mock.patch("client.request", return_value=meta):
            code, out = run_cli(["--config", self.config_path, "createmeta",
                                 "--project", "TRS"])
        self.assertEqual(code, 0)
        self.assertEqual(out["action"], "createmeta_types")
        self.assertEqual(len(out["types"]), 2)
        self.assertEqual(out["types"][0]["name"], "任务")

    def test_createmeta_带type查必填字段(self):
        meta = {"projects": [{"issuetypes": [
            {"id": "1", "name": "任务", "fields": {
                "summary": {"name": "摘要", "required": True},
                "duedate": {"name": "截止日期", "required": False},
            }}
        ]}]}
        with mock.patch("client.request", return_value=meta):
            code, out = run_cli(["--config", self.config_path, "createmeta",
                                 "--project", "TRS", "--type", "任务"])
        self.assertEqual(code, 0)
        self.assertEqual(out["action"], "createmeta")
        self.assertEqual(len(out["fields"]), 2)
        self.assertEqual(out["fields"][0]["key"], "summary")
        self.assertTrue(out["fields"][0]["required"])


    def test_create_field_覆盖核心字段拒绝(self):
        code, out = run_cli(["--config", self.config_path, "create",
                             "--project", "T", "--type", "任务",
                             "--summary", "合法标题",
                             "--field", "summary=试图篡改",
                             "--preview"])
        self.assertEqual(code, 2)
        self.assertEqual(out["error_code"], "FIELD_CONFLICT")

    def test_apply_base_url_不一致拒绝(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        import plan as planmod
        p = planmod.create_plan(plans_dir, {
            "action": "comment",
            "source": "主",
            "base_url": "http://other-jira.example",
            "key": "TRS-1",
            "body": "测试",
        })
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log):
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", p["plan_id"]])
        self.assertEqual(code, 1)
        self.assertEqual(out["error_code"], "PLAN_REJECTED")
        self.assertIn("执行源地址与预览时不一致", out["error"])

    def test_attach_file_changed_篡改拒绝(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        tmp_file = os.path.join(self.dir, "attach.txt")
        with open(tmp_file, "w") as f:
            f.write("原始内容")
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "attach",
                                 "--key", "TRS-1",
                                 "--file", tmp_file,
                                 "--preview"])
        self.assertEqual(code, 0)
        plan_id = out["plan_id"]

        # 篡改文件内容
        with open(tmp_file, "w") as f:
            f.write("篡改后的内容")

        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log):
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", plan_id])
        self.assertEqual(code, 2)
        self.assertEqual(out["error_code"], "FILE_CHANGED")

    def test_watch_不同源隔离(self):
        watch_dir = os.path.join(self.dir, "watch")
        mock_res = {"issues": [{"key": "T-1"}], "total_in_jira": 1, "returned": 1, "truncated": False, "partial": False}
        with mock.patch.object(jira_cli, "WATCH_DIR", watch_dir), \
             mock.patch("paging.search", return_value=mock_res):
            code1, out1 = run_cli(["--config", self.config_path, "--source", "主", "watch",
                                   "--name", "w1", "--jql", "project=T"])
            self.assertEqual(code1, 0)
            self.assertEqual(out1["new_count"], 1)

        # 构造第二个源
        config2 = {
            "default_source": "源2",
            "sources": [{"name": "源2", "base_url": "http://jira2.local",
                         "username": "u", "password": "p"}],
        }
        config2_path = os.path.join(self.dir, "config2.json")
        with open(config2_path, "w") as f:
            json.dump(config2, f)

        with mock.patch.object(jira_cli, "WATCH_DIR", watch_dir), \
             mock.patch("paging.search", return_value=mock_res):
            # 源2 下同名的 watch 不应被源1的 seen 记录压制
            code2, out2 = run_cli(["--config", config2_path, "--source", "源2", "watch",
                                   "--name", "w1", "--jql", "project=T"])
            self.assertEqual(code2, 0)
            self.assertEqual(out2["new_count"], 1, "不同源同名 watch 状态应独立隔离")

    def test_cmd_worklog_preview_包含started(self):
        plans_dir = os.path.join(self.dir, "plans")
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "worklog",
                                 "--key", "TRS-1", "--time", "2h",
                                 "--started", "2026-09-15T10:00:00.000+0800",
                                 "--preview"])
        self.assertEqual(code, 0)
        started_changes = [c for c in out["changes"] if c["field"] == "started"]
        self.assertEqual(len(started_changes), 1)
        self.assertEqual(started_changes[0]["to"], "2026-09-15T10:00:00.000+0800")

    def test_cmd_api_preview_全量不截断长body(self):
        plans_dir = os.path.join(self.dir, "plans")
        long_str = "x" * 600
        data_json = json.dumps({"description": long_str, "assignee": "alice"})
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir):
            code, out = run_cli(["--config", self.config_path, "api",
                                 "--path", "/rest/api/2/issue/TRS-1", "--method", "PUT",
                                 "--data", data_json, "--preview"])
        self.assertEqual(code, 0)
        body_changes = [c for c in out["changes"] if c["field"] == "body"]
        self.assertEqual(len(body_changes), 1)
        self.assertIn(long_str, body_changes[0]["to"], "长文本载荷不得截断")
        self.assertIn("alice", body_changes[0]["to"], "后续字段不得消失")

    def test_cmd_apply_comment_审计写盘失败仍报告业务成功(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        import plan as planmod
        p = planmod.create_plan(plans_dir, {
            "action": "comment",
            "source": "主",
            "base_url": "http://jira.local",
            "key": "TRS-1",
            "body": "测试评论",
        })
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log), \
             mock.patch("client.request", return_value={"id": "999"}), \
             mock.patch("plan.audit", side_effect=OSError("Disk full")):
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", p["plan_id"]])
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["comment_id"], "999")
        self.assertTrue(len(out.get("audit_errors", [])) > 0)
        self.assertIn("Disk full", out["audit_errors"][0])

    def test_cmd_apply_attach_非列表JSON响应报错(self):
        plans_dir = os.path.join(self.dir, "plans")
        audit_log = os.path.join(self.dir, "audit.log")
        tmp_file = os.path.join(self.dir, "test.png")
        with open(tmp_file, "wb") as f:
            f.write(b"png data")
        import plan as planmod
        p = planmod.create_plan(plans_dir, {
            "action": "attach",
            "source": "主",
            "base_url": "http://jira.local",
            "key": "TRS-1",
            "file_path": tmp_file,
            "filename": "test.png",
        })
        # 模拟上传接口返回非列表（如空 dict 或异常结构）
        with mock.patch.object(jira_cli, "PLANS_DIR", plans_dir), \
             mock.patch.object(jira_cli, "AUDIT_LOG", audit_log), \
             mock.patch("client.upload_file", return_value={"status": "not a list"}):
            code, out = run_cli(["--config", self.config_path, "apply",
                                 "--plan-id", p["plan_id"]])
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error_code"], "UNEXPECTED_RESPONSE")


class TestInstallSafety(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_extract_skill_保留既有配置(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "installer", os.path.join(os.path.dirname(__file__), "..", "install.py"))
        inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inst)

        target_dir = os.path.join(self.temp_dir, ".claude", "skills", "zq-jira-query")
        os.makedirs(target_dir, exist_ok=True)
        config_file = os.path.join(target_dir, "jira_config.json")
        with open(config_file, "w") as f:
            f.write("user secret config")

        inst.extract_skill(self.temp_dir)
        self.assertTrue(os.path.isfile(config_file))
        with open(config_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "user secret config", "解压技能时不得覆盖用户既有 jira_config.json")

    def test_install_user_level_保留既有配置与软链(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "installer", os.path.join(os.path.dirname(__file__), "..", "install.py"))
        inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inst)

        fake_home = os.path.join(self.temp_dir, "fake_home")
        old_skill = os.path.join(fake_home, ".agents", "skills", "zq-jira-query")
        os.makedirs(old_skill, exist_ok=True)
        old_config = os.path.join(old_skill, "jira_config.json")
        with open(old_config, "w") as f:
            f.write("pre-existing user config")

        # 构造 .claude/skills 到 .agents/skills 的软链接
        claude_skills = os.path.join(fake_home, ".claude", "skills")
        os.makedirs(os.path.dirname(claude_skills), exist_ok=True)
        os.symlink(os.path.join(fake_home, ".agents", "skills"), claude_skills)

        # 伪造 root 技能目录
        fake_root = os.path.join(self.temp_dir, "fake_root")
        fake_src = os.path.join(fake_root, ".claude", "skills", "zq-jira-query")
        os.makedirs(fake_src, exist_ok=True)
        with open(os.path.join(fake_src, "SKILL.md"), "w") as f:
            f.write("new skill")

        with mock.patch("os.path.expanduser", return_value=fake_home):
            inst.install_user_level(fake_root)

        self.assertTrue(os.path.isfile(old_config))
        with open(old_config, "r") as f:
            self.assertEqual(f.read(), "pre-existing user config", "用户级安装不得删除既有 jira_config.json")
        self.assertTrue(os.path.islink(claude_skills), "软链结构应完好无损")

    def test_install_user_level_全新空环境自动创建目录并安装(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "installer", os.path.join(os.path.dirname(__file__), "..", "install.py"))
        inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inst)

        # 构造没有任何 .agents 或 .claude 的纯空 HOME
        empty_home = os.path.join(self.temp_dir, "empty_home")
        os.makedirs(empty_home, exist_ok=True)

        fake_root = os.path.join(self.temp_dir, "fake_root2")
        fake_src = os.path.join(fake_root, ".claude", "skills", "zq-jira-query")
        os.makedirs(fake_src, exist_ok=True)
        with open(os.path.join(fake_src, "SKILL.md"), "w") as f:
            f.write("skill in blank environment")

        with mock.patch("os.path.expanduser", return_value=empty_home):
            inst.install_user_level(fake_root)

        installed_skill = os.path.join(empty_home, ".agents", "skills", "zq-jira-query", "SKILL.md")
        self.assertTrue(os.path.isfile(installed_skill), "全新空环境执行 --user 应自动创建目录并安装技能")
        with open(installed_skill, "r") as f:
            self.assertEqual(f.read(), "skill in blank environment")


if __name__ == "__main__":
    unittest.main()

