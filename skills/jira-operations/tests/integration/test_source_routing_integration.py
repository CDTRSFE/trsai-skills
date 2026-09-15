# -*- coding: utf-8 -*-
"""多 Jira 源「选源」链路 · 集成测试（不连外网，本地真起两个假 Jira 服务端）。

测试目标
--------
验证「选哪个 Jira 源」这条链路在**真实代码**上确实生效，而不是只在文档里说说：
argparse 解析 `--source` → `client.load_config` 读配置 → `client.pick_source` 选源 →
真实 `urllib` 发出 HTTP 请求 → 真实 JSON 解析 → stdout 单行 JSON 契约。覆盖 7 条业务行为：

  1. 显式 `--source Jira1` / `--source Jira2` 时，请求真的打到对应那个端口；
  2. 不传 `--source` 时落到配置里的 `default_source`（本文件把它设成非主用源，漏传参数当场现形）；
  3. 三个 `routing_` 字段不破坏配置加载，且**不会**出现在 CLI 的 stdout 里
     （它们只给模型读，`normalize_source` 不搬运它们）；
  4. `--source` 传了配置里不存在的源名 → `CONFIG_ERROR` + 退出码 2，且一次网络请求都没发出去；
  5. `--source` 写在子命令后面（`whoami --source Jira1`）直接参数报错、非 0 退出；
  6. 源名大小写敏感，`--source jira1` 报 `CONFIG_ERROR`，不做模糊匹配；
  7. 显式 `--source` 的优先级高于 `default_source`。

依赖环境
--------
**无任何外部依赖**：不连真 Jira、不读工程根 `jira_config.json`、不写 `state/`。
两个「Jira 源」由标准库 `http.server` 在 `127.0.0.1` 的随机端口上真起两个 HTTP 服务来扮演，
各自返回 Jira REST 的合法响应体（`/rest/api/2/myself` 与 `/rest/api/2/search`），
并记录收到的请求方法与路径供断言。**被测链路一行都没打桩**——只有 Jira 服务端是替身，
符合项目测试规范里「集成测试必须用真实依赖，不许拿 mock 替代被测对象」这条硬要求。
因此本文件默认就跑，不设 `JIRA_IT=1` 之类的环境变量闸门，
`python3 -m unittest discover tests` 会直接执行到。

数据准备方式
------------
用例按需用 `tempfile` 现写一份临时 `jira_config.json`（**全部是假凭据**，`base_url` 指向上面
两个本地端口，两个源各带三个 `routing_` 字段），通过 `--config` 传给 CLI；用例结束自动删除。
两个假源返回**不同的用户名与 issue key**，所以「请求到底打到了谁」既能从服务端的请求记录看出来，
也能从 CLI 输出的内容交叉印证。

跑法
----
    python3 -m unittest discover tests
    python3 -m unittest tests.integration.test_source_routing_integration -v
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JIRA_CLI = os.path.join(ROOT, "scripts", "jira_cli.py")

# 两个假源的可区分标记：谁应答了，看输出里的用户名 / issue key 就知道
JIRA1_USER = "fake-user-jira1"
JIRA1_DISPLAY = "假源一号用户"
JIRA1_ISSUE_KEY = "XJRB-101"
JIRA2_USER = "fake-user-jira2"
JIRA2_DISPLAY = "假源二号用户"
JIRA2_ISSUE_KEY = "XMKFB-202"

# routing_ 三字段的取值：形态对齐二次设计「关键设计点 1」的字段定义表
JIRA1_ROUTING = {
    "routing_business_tag": "非涉密",
    "routing_business_desc": "假源一号：一句话描述该源的业务范围",
    "routing_project_keys": ["XJRB", "XMKFB"],
}
JIRA2_ROUTING = {
    "routing_business_tag": "涉密",
    "routing_business_desc": "假源二号：一句话描述该源的业务范围",
    "routing_project_keys": ["XMKFB"],
}


class _FakeJiraHandler(http.server.BaseHTTPRequestHandler):
    """假 Jira 的请求处理器：只认 whoami 与 search 两个端点，其余一律 404。"""

    def log_message(self, fmt, *args):
        """静音：默认实现会往 stderr 打访问日志，污染测试输出。"""

    def _reply_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json;charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.server.record("GET", self.path)
        if self.path == "/rest/api/2/myself":
            self._reply_json(200, {
                "name": self.server.user_name,
                "displayName": self.server.display_name,
                "emailAddress": self.server.user_name + "@example.invalid",
            })
            return
        self._reply_json(404, {"errorMessages": ["假 Jira 未实现该端点: " + self.path]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self.server.record("POST", self.path, raw)
        if self.path == "/rest/api/2/search":
            self._reply_json(200, {
                "startAt": 0,
                "maxResults": 50,
                "total": 1,
                "issues": [{
                    "key": self.server.issue_key,
                    "fields": {"summary": "来自 " + self.server.user_name + " 的测试单",
                               "status": {"name": "待办"}},
                }],
            })
            return
        self._reply_json(404, {"errorMessages": ["假 Jira 未实现该端点: " + self.path]})


class _FakeJiraServer(http.server.ThreadingHTTPServer):
    """一台假 Jira：绑 127.0.0.1 随机端口，把收到的请求逐条记下来供断言。"""

    daemon_threads = True

    def __init__(self, user_name, display_name, issue_key):
        super().__init__(("127.0.0.1", 0), _FakeJiraHandler)
        self.user_name = user_name
        self.display_name = display_name
        self.issue_key = issue_key
        self._lock = threading.Lock()
        self.requests = []
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self):
        host, port = self.server_address[0], self.server_address[1]
        return "http://%s:%d" % (host, port)

    def record(self, method, path, body=b""):
        with self._lock:
            self.requests.append((method, path, body))

    def reset(self):
        with self._lock:
            self.requests = []

    def paths(self):
        """已收到请求的 (方法, 路径) 列表，断言「打到了谁」用它。"""
        with self._lock:
            return [(m, p) for m, p, _ in self.requests]

    def hit_count(self):
        with self._lock:
            return len(self.requests)

    def stop(self):
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=5)


class SourceRoutingIntegrationTest(unittest.TestCase):
    """选源链路集成测试：真配置文件 + 真 CLI 子进程 + 真 HTTP，只有 Jira 服务端是替身。"""

    # ------------------------------------------------------------ 基础设施

    @classmethod
    def setUpClass(cls):
        cls.jira1 = _FakeJiraServer(JIRA1_USER, JIRA1_DISPLAY, JIRA1_ISSUE_KEY)
        cls.jira2 = _FakeJiraServer(JIRA2_USER, JIRA2_DISPLAY, JIRA2_ISSUE_KEY)

    @classmethod
    def tearDownClass(cls):
        cls.jira1.stop()
        cls.jira2.stop()

    def setUp(self):
        self.jira1.reset()
        self.jira2.reset()
        self.workdir = tempfile.mkdtemp(prefix="jira_routing_it_")
        self.addCleanup(shutil.rmtree, self.workdir, True)

    def _write_config(self, default_source):
        """写一份临时配置：假凭据 + 指向两个本地假源 + 两源各带三个 routing_ 字段。"""
        config = {
            "default_source": default_source,
            "sources": [
                dict({"name": "Jira1", "base_url": self.jira1.base_url,
                      "username": "fake-account-1", "password": "fake-secret-1",
                      "insecure": False, "timeout_seconds": 10}, **JIRA1_ROUTING),
                dict({"name": "Jira2", "base_url": self.jira2.base_url,
                      "username": "fake-account-2", "password": "fake-secret-2",
                      "insecure": False, "timeout_seconds": 10}, **JIRA2_ROUTING),
            ],
        }
        path = os.path.join(self.workdir, "jira_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return path

    def _run(self, argv, timeout=60):
        """子进程调用 jira_cli.py（跟人和模型的实际用法完全一致），返回 CompletedProcess。

        代理必须掐掉：urllib 默认会读 http_proxy/HTTPS_PROXY 环境变量，
        本机若配了代理，发往 127.0.0.1 的请求会被绕走，测试就成了假阴性。
        """
        env = dict(os.environ)
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy",
                    "ALL_PROXY"):
            env.pop(key, None)
        env["no_proxy"] = "*"
        env["NO_PROXY"] = "*"
        return subprocess.run([sys.executable, JIRA_CLI] + argv, cwd=ROOT,
                              capture_output=True, text=True, timeout=timeout, env=env)

    def _run_json(self, argv, timeout=60):
        """跑 CLI 并解析 stdout 末行 JSON，返回 (退出码, JSON 字典, 原始 stdout)。"""
        proc = self._run(argv, timeout=timeout)
        lines = (proc.stdout or "").strip().splitlines()
        self.assertTrue(lines, "命令没有任何 stdout 输出，argv=%s，stderr=%s" % (argv, proc.stderr))
        try:
            out = json.loads(lines[-1])
        except ValueError:
            self.fail("命令 stdout 不是合法 JSON，argv=%s\nstdout=%s\nstderr=%s"
                      % (argv, proc.stdout, proc.stderr))
        return proc.returncode, out, proc.stdout

    # ------------------------------------------------------------ 业务行为 1

    def test_显式指定源时请求真的打到对应源(self):
        """行为 1：--source Jira1 打 Jira1 的端口，--source Jira2 打 Jira2 的端口。"""
        config = self._write_config(default_source="Jira1")

        code, out, _ = self._run_json(["--config", config, "--source", "Jira1", "whoami"])
        self.assertEqual(0, code, "指定存在的源 Jira1 应当成功，实际退出码 %d，返回=%s" % (code, out))
        self.assertTrue(out.get("ok"), "指定 Jira1 时 ok 应为 true，实际返回=%s" % out)
        self.assertEqual("Jira1", out.get("source"), "输出的 source 字段应回显 Jira1，实际=%s" % out.get("source"))
        self.assertEqual(JIRA1_DISPLAY, out["user"]["displayName"],
                         "应答内容应来自 Jira1 那台假服务，实际=%s" % out["user"])
        self.assertEqual([("GET", "/rest/api/2/myself")], self.jira1.paths(),
                         "Jira1 端口应当收到一次 whoami 请求，实际=%s" % self.jira1.paths())
        self.assertEqual(0, self.jira2.hit_count(),
                         "指定 Jira1 时 Jira2 端口应当一次请求都没收到，实际=%s" % self.jira2.paths())

        self.jira1.reset()
        self.jira2.reset()
        code, out, _ = self._run_json(["--config", config, "--source", "Jira2", "whoami"])
        self.assertEqual(0, code, "指定存在的源 Jira2 应当成功，实际退出码 %d，返回=%s" % (code, out))
        self.assertEqual("Jira2", out.get("source"), "输出的 source 字段应回显 Jira2，实际=%s" % out.get("source"))
        self.assertEqual(JIRA2_DISPLAY, out["user"]["displayName"],
                         "应答内容应来自 Jira2 那台假服务，实际=%s" % out["user"])
        self.assertEqual([("GET", "/rest/api/2/myself")], self.jira2.paths(),
                         "Jira2 端口应当收到一次 whoami 请求，实际=%s" % self.jira2.paths())
        self.assertEqual(0, self.jira1.hit_count(),
                         "指定 Jira2 时 Jira1 端口应当一次请求都没收到，实际=%s" % self.jira1.paths())

    # ------------------------------------------------------------ 业务行为 2

    def test_不传源时落到默认源(self):
        """行为 2：不传 --source 就按 default_source 走——默认源指向非主用源时漏传参数当场现形。"""
        config = self._write_config(default_source="Jira1")

        code, out, _ = self._run_json(["--config", config, "whoami"])
        self.assertEqual(0, code, "不传 --source 应当按 default_source 正常执行，实际退出码 %d，返回=%s" % (code, out))
        self.assertEqual("Jira1", out.get("source"),
                         "default_source=Jira1 时输出的 source 应为 Jira1，实际=%s" % out.get("source"))
        self.assertEqual(JIRA1_DISPLAY, out["user"]["displayName"],
                         "漏传 --source 时请求必须落到默认源 Jira1，实际应答=%s" % out["user"])
        self.assertEqual([("GET", "/rest/api/2/myself")], self.jira1.paths(),
                         "默认源 Jira1 端口应当收到这次请求，实际=%s" % self.jira1.paths())
        self.assertEqual(0, self.jira2.hit_count(),
                         "默认源是 Jira1 时 Jira2 端口不应收到任何请求，实际=%s" % self.jira2.paths())

    # ------------------------------------------------------------ 业务行为 3

    def test_routing字段不破坏配置加载且不外泄到输出(self):
        """行为 3：三个 routing_ 字段既不让配置加载报错，也不会被搬进 CLI 的 stdout。"""
        config = self._write_config(default_source="Jira1")

        code, out, raw = self._run_json(["--config", config, "--source", "Jira2", "whoami"])
        self.assertEqual(0, code, "配置里带 routing_ 字段时 CLI 应照常工作，实际退出码 %d，返回=%s" % (code, out))
        self.assertTrue(out.get("ok"), "配置里带 routing_ 字段时 ok 应为 true，实际返回=%s" % out)
        self.assertNotEqual("CONFIG_ERROR", out.get("error_code"),
                            "routing_ 字段属于额外键，不得触发 CONFIG_ERROR，实际返回=%s" % out)

        self.assertNotIn("routing_", raw, "routing_ 字段名不应出现在 CLI 输出里，实际 stdout=%s" % raw)
        for key, value in (("routing_business_tag", JIRA2_ROUTING["routing_business_tag"]),
                           ("routing_business_desc", JIRA2_ROUTING["routing_business_desc"])):
            self.assertNotIn(value, raw,
                             "%s 的取值只给模型读，不应出现在 CLI 输出里，实际 stdout=%s" % (key, raw))
        for project_key in JIRA2_ROUTING["routing_project_keys"]:
            self.assertNotIn(project_key, raw,
                             "routing_project_keys 的元素不应出现在 whoami 输出里，实际 stdout=%s" % raw)

        # 再跑一次会真发 POST 的 search，确认带 routing_ 字段的源同样能正常请求与解析
        self.jira2.reset()
        code, out, raw = self._run_json(
            ["--config", config, "--source", "Jira2", "search", "--jql", "project = XMKFB"])
        self.assertEqual(0, code, "带 routing_ 字段的源执行 search 应当成功，实际退出码 %d，返回=%s" % (code, out))
        self.assertEqual(JIRA2_ISSUE_KEY, out["issues"][0]["key"],
                         "search 结果应来自 Jira2 那台假服务，实际=%s" % out.get("issues"))
        self.assertNotIn("routing_", raw, "search 输出同样不应出现 routing_ 字段名，实际 stdout=%s" % raw)

    # ------------------------------------------------------------ 业务行为 4

    def test_源名不存在时报配置错误且零请求(self):
        """行为 4：--source Jira3 → CONFIG_ERROR + 退出码 2，且两台假服务一次请求都没收到。"""
        config = self._write_config(default_source="Jira1")

        code, out, _ = self._run_json(["--config", config, "--source", "Jira3", "whoami"])
        self.assertEqual(2, code, "源名不存在属于配置错误，退出码应为 2，实际 %d，返回=%s" % (code, out))
        self.assertFalse(out.get("ok"), "源名不存在时 ok 应为 false，实际返回=%s" % out)
        self.assertEqual("CONFIG_ERROR", out.get("error_code"),
                         "源名不存在时 error_code 应为 CONFIG_ERROR，实际=%s" % out.get("error_code"))
        self.assertEqual(0, self.jira1.hit_count(),
                         "选源失败必须在发请求之前就拦下，Jira1 端口不应收到请求，实际=%s" % self.jira1.paths())
        self.assertEqual(0, self.jira2.hit_count(),
                         "选源失败必须在发请求之前就拦下，Jira2 端口不应收到请求，实际=%s" % self.jira2.paths())

    # ------------------------------------------------------------ 业务行为 5

    def test_source写在子命令后面直接参数报错(self):
        """行为 5：`jira_cli.py whoami --source Jira1` 这种位置写法直接参数报错、非 0 退出。"""
        config = self._write_config(default_source="Jira1")

        proc = self._run(["--config", config, "whoami", "--source", "Jira1"])
        self.assertNotEqual(0, proc.returncode,
                            "--source 写在子命令后面应当非 0 退出，实际退出码 0，stdout=%s" % proc.stdout)
        self.assertEqual("", (proc.stdout or "").strip(),
                         "参数解析阶段就失败了，stdout 不应有 JSON 契约输出，实际=%s" % proc.stdout)
        self.assertIn("--source", proc.stderr or "",
                      "报错信息里应当点名 --source 这个参数，实际 stderr=%s" % proc.stderr)
        self.assertEqual(0, self.jira1.hit_count() + self.jira2.hit_count(),
                         "参数报错阶段不应发出任何请求，实际 Jira1=%s Jira2=%s"
                         % (self.jira1.paths(), self.jira2.paths()))

    # ------------------------------------------------------------ 业务行为 6

    def test_源名大小写敏感(self):
        """行为 6：--source jira1（小写）应报 CONFIG_ERROR，不做大小写模糊匹配。"""
        config = self._write_config(default_source="Jira1")

        code, out, _ = self._run_json(["--config", config, "--source", "jira1", "whoami"])
        self.assertEqual(2, code, "小写源名应按配置错误处理，退出码应为 2，实际 %d，返回=%s" % (code, out))
        self.assertEqual("CONFIG_ERROR", out.get("error_code"),
                         "小写源名不应被模糊匹配到 Jira1，error_code 应为 CONFIG_ERROR，实际=%s" % out.get("error_code"))
        self.assertEqual(0, self.jira1.hit_count(),
                         "大小写不匹配时不应退化到 Jira1 发请求，实际=%s" % self.jira1.paths())
        self.assertEqual(0, self.jira2.hit_count(),
                         "大小写不匹配时不应发出任何请求，实际=%s" % self.jira2.paths())

    # ------------------------------------------------------------ 业务行为 7

    def test_显式源优先于默认源(self):
        """行为 7：default_source=Jira1 时显式 --source Jira2，请求必须打到 Jira2。"""
        config = self._write_config(default_source="Jira1")

        code, out, _ = self._run_json(
            ["--config", config, "--source", "Jira2", "search", "--jql", "project = XMKFB"])
        self.assertEqual(0, code, "显式指定 Jira2 应当成功，实际退出码 %d，返回=%s" % (code, out))
        self.assertEqual("Jira2", out.get("source"),
                         "显式 --source 应压过 default_source=Jira1，实际 source=%s" % out.get("source"))
        self.assertEqual(JIRA2_ISSUE_KEY, out["issues"][0]["key"],
                         "返回的 issue 应来自 Jira2 那台假服务，实际=%s" % out.get("issues"))
        self.assertEqual([("POST", "/rest/api/2/search")], self.jira2.paths(),
                         "Jira2 端口应当收到一次 search 请求，实际=%s" % self.jira2.paths())
        self.assertEqual(0, self.jira1.hit_count(),
                         "显式指定 Jira2 时默认源 Jira1 不应收到任何请求，实际=%s" % self.jira1.paths())


if __name__ == "__main__":
    unittest.main()
