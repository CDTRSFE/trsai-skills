# -*- coding: utf-8 -*-
"""client.py 测试：配置归一、URL 拼接、错误分类、重试纪律、timeout 传入。

HTTP 全部用 unittest.mock 打桩 urlopen，不起真 server。
"""
import io
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import client


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
    def __init__(self, body, content_type="application/json;charset=UTF-8"):
        self._body = body.encode("utf-8")
        self.headers = FakeHeaders({"Content-Type": content_type})

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, headers=None, body=b"{}"):
    return urllib.error.HTTPError(
        "http://x", code, "err", FakeHeaders(headers or {}), io.BytesIO(body))


SOURCE = client.normalize_source({
    "name": "t", "base_url": "http://jira.local/", "username": "u", "password": "p",
})


class TestNormalize(unittest.TestCase):
    def test_base_url_归一(self):
        for raw in ("http://a.com", "http://a.com/", "http://a.com//"):
            s = client.normalize_source({"base_url": raw, "username": "u", "password": "p"})
            self.assertEqual(s["base_url"], "http://a.com", "base_url 尾斜杠应归一")

    def test_issue_key_归一(self):
        self.assertEqual(client.normalize_issue_key("pmo-123"), "PMO-123")
        self.assertEqual(client.normalize_issue_key(" PMO-123 "), "PMO-123")

    def test_url拼接无双斜杠(self):
        self.assertEqual(client.build_url(SOURCE, "/rest/api/2/myself"),
                         "http://jira.local/rest/api/2/myself")
        self.assertEqual(client.build_url(SOURCE, "rest/x"),
                         "http://jira.local/rest/x")

    def test_query参数中文编码(self):
        self.assertEqual(client.url_quote("任务"), "%E4%BB%BB%E5%8A%A1",
                         "query 参数里的中文必须 percent-encode，否则 urllib 直接抛 UnicodeEncodeError")

    def test_缺字段报配置错(self):
        with self.assertRaises(client.JiraError) as cm:
            client.normalize_source({"name": "x", "base_url": "http://a"})
        self.assertEqual(cm.exception.error_code, "CONFIG_ERROR")


class TestRequest(unittest.TestCase):
    def _call(self, side_effect):
        with mock.patch("urllib.request.urlopen", side_effect=side_effect) as m, \
             mock.patch("client.time.sleep"):
            try:
                return client.request(SOURCE, "GET", "/rest/api/2/myself"), m
            except client.JiraError as e:
                return e, m

    def test_成功返回json(self):
        result, m = self._call([FakeResponse('{"name": "u"}')])
        self.assertEqual(result, {"name": "u"})
        _, kwargs = m.call_args
        self.assertEqual(kwargs.get("timeout"), SOURCE["timeout_seconds"],
                         "urlopen 必须逐次传入 timeout")

    def test_401无头_AUTH_FAILED且不重试(self):
        err, m = self._call([http_error(401)])
        self.assertEqual(err.error_code, "AUTH_FAILED")
        self.assertEqual(m.call_count, 1, "认证失败绝不重试")

    def test_401带头_CAPTCHA(self):
        err, m = self._call([http_error(401, {"X-Authentication-Denied-Reason": "captcha"})])
        self.assertEqual(err.error_code, "CAPTCHA_LOCKED")
        self.assertEqual(m.call_count, 1)

    def test_403带头_CAPTCHA(self):
        err, _ = self._call([http_error(403, {"x-authentication-denied-reason": "captcha"})])
        self.assertEqual(err.error_code, "CAPTCHA_LOCKED", "头名应大小写不敏感")

    def test_403无头_PERMISSION_DENIED(self):
        err, _ = self._call([http_error(403)])
        self.assertEqual(err.error_code, "PERMISSION_DENIED")

    def test_404_NOT_FOUND(self):
        err, _ = self._call([http_error(404)])
        self.assertEqual(err.error_code, "NOT_FOUND")

    def test_400_JQL_INVALID回带报错(self):
        err, _ = self._call([http_error(400, body=b'{"errorMessages": ["bad jql"]}')])
        self.assertEqual(err.error_code, "JQL_INVALID")
        self.assertIn("bad jql", err.error)

    def test_429退避重试恰好一次(self):
        result, m = self._call([
            http_error(429, {"Retry-After": "1"}),
            FakeResponse('{"ok": 1}'),
        ])
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(m.call_count, 2, "429 应恰好重试一次")

    def test_429两次_RATE_LIMITED(self):
        err, m = self._call([http_error(429), http_error(429)])
        self.assertEqual(err.error_code, "RATE_LIMITED")
        self.assertEqual(m.call_count, 2)

    def test_500_SERVER_ERROR(self):
        err, _ = self._call([http_error(500)])
        self.assertEqual(err.error_code, "SERVER_ERROR")

    def test_200但非JSON_UNEXPECTED_RESPONSE(self):
        err, _ = self._call([FakeResponse("<html>login</html>", "text/html")])
        self.assertEqual(err.error_code, "UNEXPECTED_RESPONSE")
        self.assertIn("<html>", err.error, "应回带响应前 200 字符")

    def test_tls提示(self):
        self.assertEqual(client.tls_note(SOURCE), {})
        insecure = dict(SOURCE, insecure=True)
        self.assertEqual(client.tls_note(insecure), {"tls_verification": "disabled"})

    def test_keychain_password_获取(self):
        with mock.patch("client.read_keychain_password", return_value="secret_from_keychain"):
            src = client.normalize_source({
                "base_url": "http://jira.local",
                "username": "u",
                "passwordKeychainService": "my.jira.service"
            })
        self.assertEqual(src["password"], "secret_from_keychain")

    def test_keychain_password_缺失报错(self):
        with mock.patch("client.read_keychain_password", return_value=None):
            with self.assertRaises(client.JiraError) as ctx:
                client.normalize_source({
                    "base_url": "http://jira.local",
                    "username": "u",
                    "passwordKeychainService": "nonexistent"
                })
    def test_safe_redirect_handler_跨域剥离认证头(self):
        handler = client.SafeRedirectHandler()
        req = urllib.request.Request("http://jira.corp.example/rest/api/2/issue",
                                     headers={"Authorization": "Basic secret_token"})
        # 跨 host 重定向
        new_req = handler.redirect_request(req, None, 302, "Found", {}, "http://external.attack.example/login")
        self.assertIsNotNone(new_req)
        self.assertNotIn("Authorization", new_req.headers)
        self.assertNotIn("authorization", new_req.headers)
        if hasattr(new_req, "unredirected_hdrs"):
            self.assertNotIn("Authorization", new_req.unredirected_hdrs)
            self.assertNotIn("authorization", new_req.unredirected_hdrs)

        # 同 host 重定向保留
        same_req = handler.redirect_request(req, None, 302, "Found", {}, "http://jira.corp.example/new_path")
        self.assertIsNotNone(same_req)
        self.assertEqual(same_req.headers.get("Authorization"), "Basic secret_token")

    def test_upload_file_429重试(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            tmp_path = f.name
        try:
            with mock.patch("client._urlopen", side_effect=[
                http_error(429, {"Retry-After": "0"}),
                FakeResponse('[{"id": "1001", "filename": "test"}]')
            ]), mock.patch("client.time.sleep") as m_sleep:
                resp = client.upload_file(SOURCE, "/rest/api/2/issue/TEST-1/attachments", tmp_path)
                self.assertEqual(resp, [{"id": "1001", "filename": "test"}])
                self.assertEqual(m_sleep.call_count, 1)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_upload_file_429重试_保持同一份内存字节不重新读盘(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"original_data_content")
            tmp_path = f.name
        try:
            calls = []
            def fake_urlopen(req, source):
                calls.append(req.data)
                if len(calls) == 1:
                    # 在第一次 429 之后，恶意篡改磁盘文件
                    with open(tmp_path, "wb") as f_alter:
                        f_alter.write(b"MODIFIED_UNAUTHORIZED_CONTENT")
                    raise http_error(429, {"Retry-After": "0"})
                return FakeResponse('[{"id": "1001", "filename": "test"}]')

            with mock.patch("client._urlopen", side_effect=fake_urlopen), \
                 mock.patch("client.time.sleep"):
                resp = client.upload_file(SOURCE, "/rest/api/2/issue/TEST-1/attachments", tmp_path)
                self.assertEqual(resp, [{"id": "1001", "filename": "test"}])
                self.assertEqual(len(calls), 2)
                # 两次请求的数据体中都必须包含 original_data_content，绝不能包含篡改后的 MODIFIED
                self.assertIn(b"original_data_content", calls[0])
                self.assertIn(b"original_data_content", calls[1])
                self.assertNotIn(b"MODIFIED_UNAUTHORIZED_CONTENT", calls[1])
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_upload_file_html响应报错UNEXPECTED_RESPONSE(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"data")
            tmp_path = f.name
        try:
            with mock.patch("client._urlopen", return_value=FakeResponse("<html>Login</html>", "text/html")):
                with self.assertRaises(client.JiraError) as ctx:
                    client.upload_file(SOURCE, "/rest/api/2/issue/TEST-1/attachments", tmp_path)
                self.assertEqual(ctx.exception.error_code, "UNEXPECTED_RESPONSE")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
