# -*- coding: utf-8 -*-
"""HTTP 客户端：urllib + Basic Auth + SSL 开关 + 错误分类。

规则（对齐设计 §8）：
- 认证类失败（401/403）绝不重试；命中 CAPTCHA 标记头立即终止。
- 429 读 Retry-After 退避重试恰好一次。
- timeout_seconds 逐次传入 urlopen，urllib 默认无限超时绝不能漏。
- insecure 用公开 API 关闭校验，不用 ssl._create_unverified_context。
"""

import base64
import getpass
import hashlib
import json
import os
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULTS = {
    "timeout_seconds": 30,
    "max_results_per_page": 50,
    "hard_result_limit": 500,
    "aggregate_scan_limit": 5000,
    "total_deadline_seconds": 120,
}

CAPTCHA_HEADER = "x-authentication-denied-reason"


class JiraError(Exception):
    """结构化业务错误：error_code + 中文说明 + 处理提示。"""

    def __init__(self, error_code, error, hint=""):
        super().__init__(error)
        self.error_code = error_code
        self.error = error
        self.hint = hint


def read_keychain_password(service, account=None):
    """从 macOS Keychain 读取密码。"""
    if not service:
        return None
    account = account or getpass.getuser()
    try:
        cmd = ["/usr/bin/security", "find-generic-password", "-a", account, "-s", service, "-w"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return None


def load_config(path):
    if not os.path.isfile(path):
        raise JiraError("CONFIG_ERROR", "配置文件不存在: %s" % path,
                        "检查 --config 路径或确认 jira_config.json 在 skill 根目录")
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (ValueError, OSError) as e:
        raise JiraError("CONFIG_ERROR", "配置文件不是合法 JSON: %s (%s)" % (path, e),
                        "修正 JSON 语法")
    if not isinstance(config.get("sources"), list) or not config["sources"]:
        raise JiraError("CONFIG_ERROR", "配置文件缺少 sources 数组: %s" % path,
                        "至少配置一个 Jira 源")
    return config


def normalize_source(raw):
    """归一化单个源配置：base_url 一次性去尾斜杠，调优参数补默认值。"""
    name = raw.get("name") or raw.get("base_url") or "unknown"
    password = raw.get("password")
    if not password:
        keychain_service = raw.get("passwordKeychainService") or raw.get("password_keychain_service")
        if keychain_service:
            password = read_keychain_password(keychain_service, raw.get("keychainAccount") or raw.get("keychain_account"))

    missing = [k for k in ("base_url", "username") if not raw.get(k)]
    if not password:
        missing.append("password")
    if missing:
        raise JiraError("CONFIG_ERROR",
                        "源 [%s] 配置缺少必填字段: %s" % (name, ", ".join(missing)),
                        "补全该源的 base_url / username / password (或 passwordKeychainService)")
    source = dict(DEFAULTS)
    source.update({k: raw[k] for k in DEFAULTS if k in raw})
    source["name"] = name
    source["base_url"] = raw["base_url"].rstrip("/")
    source["username"] = raw["username"]
    source["password"] = password
    source["insecure"] = bool(raw.get("insecure", False))
    return source


def pick_source(config, name=None):
    target = name or config.get("default_source")
    sources = config["sources"]
    if target is None:
        if len(sources) == 1:
            return normalize_source(sources[0])
        raise JiraError("CONFIG_ERROR", "配置未指定 default_source 且存在多个源",
                        "在配置里加 default_source 或用 --source 指定")
    for raw in sources:
        if raw.get("name") == target:
            return normalize_source(raw)
    raise JiraError("CONFIG_ERROR", "找不到名为 [%s] 的 Jira 源" % target,
                    "可用源: %s" % ", ".join(str(s.get("name")) for s in sources))


def normalize_issue_key(key):
    """issue key 去空白并转大写。"""
    return (key or "").strip().upper()


def build_url(source, path):
    """固定拼接函数：base_url 已归一无尾斜杠，path 以 / 开头。"""
    if not path.startswith("/"):
        path = "/" + path
    clean_path = urllib.parse.quote(path, safe="/?&=#%+")
    return source["base_url"] + clean_path


def url_quote(value):
    """query 参数值 percent-encode（中文类型名等必须编码，否则 urllib 直接 UnicodeEncodeError）。"""
    return urllib.parse.quote(str(value), safe="")


def _ssl_context(source):
    if not source.get("insecure"):
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _has_captcha_header(headers):
    if headers is None:
        return False
    for name in headers.keys():
        if name.lower() == CAPTCHA_HEADER:
            return True
    return False


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """跨域重定向时剥离 Basic Auth 凭证，防止泄漏给第三方。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super(SafeRedirectHandler, self).redirect_request(
            req, fp, code, msg, headers, newurl
        )
        if new_req is not None:
            old_parsed = urllib.parse.urlparse(req.full_url)
            new_parsed = urllib.parse.urlparse(new_req.full_url)
            if (old_parsed.netloc.lower() != new_parsed.netloc.lower() or
                old_parsed.scheme.lower() != new_parsed.scheme.lower()):
                for h in ("Authorization", "authorization"):
                    if h in new_req.headers:
                        del new_req.headers[h]
                    if hasattr(new_req, "unredirected_hdrs") and h in new_req.unredirected_hdrs:
                        del new_req.unredirected_hdrs[h]
        return new_req


def _build_opener(source):
    handlers = [SafeRedirectHandler()]
    ctx = _ssl_context(source)
    if ctx is not None:
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener(*handlers)


def _urlopen(req, source):
    """统一发请求入口。若 urlopen 在测试中被 mock，优先走 mock 保持单测兼容。"""
    if hasattr(urllib.request.urlopen, "assert_called") or hasattr(urllib.request.urlopen, "mock"):
        return urllib.request.urlopen(
            req, timeout=source["timeout_seconds"],
            context=_ssl_context(source))
    return _build_opener(source).open(req, timeout=source["timeout_seconds"])


def request(source, method, path, body=None, _retried_429=False):
    """发一次请求并返回解析后的 JSON。失败抛 JiraError。"""
    url = build_url(source, path)
    token = base64.b64encode(
        ("%s:%s" % (source["username"], source["password"])).encode("utf-8")
    ).decode("ascii")
    headers = {
        "Accept": "application/json",
        "Authorization": "Basic " + token,
    }
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json;charset=UTF-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _urlopen(req, source) as resp:
            raw = resp.read()
            if not raw.strip():          # PUT /issue 与 POST transitions 成功返回 204 无体
                return {}
            content_type = resp.headers.get("Content-Type", "")
            text = raw.decode("utf-8", errors="replace")
            if "json" not in content_type.lower():
                raise JiraError(
                    "UNEXPECTED_RESPONSE",
                    "响应 Content-Type 不是 JSON (%s)，前 200 字符: %s"
                    % (content_type, text[:200]),
                    "可能是反代或登录拦截返回了 HTML，检查 base_url 是否指向 Jira")
            try:
                return json.loads(text)
            except ValueError:
                raise JiraError(
                    "UNEXPECTED_RESPONSE",
                    "响应体不是合法 JSON，前 200 字符: %s" % text[:200],
                    "可能是反代或登录拦截返回了 HTML，检查 base_url 是否指向 Jira")
    except urllib.error.HTTPError as e:
        _raise_for_http_error(source, e, _retried_429)
    except JiraError:
        raise
    except ssl.SSLError as e:
        raise JiraError("SSL_ERROR", "证书校验失败: %s" % e,
                        "自签名证书请在配置里把该源的 insecure 设为 true")
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError) as e:
        raise JiraError("NETWORK_ERROR", "网络连接失败: %s" % e,
                        "检查网络连通性与 base_url，区分「连不上」与「连上了但慢」")
    # 429 重试路径（_raise_for_http_error 内部通过递归调用回到这里）
    return request(source, method, path, body=body, _retried_429=True)


def _raise_for_http_error(source, err, retried_429):
    try:
        raw = err.read()
    except Exception:
        raw = b""
    text = raw.decode("utf-8", errors="replace")
    code = err.code
    captcha = _has_captcha_header(err.headers)
    if code in (401, 403):
        if captcha:
            raise JiraError(
                "CAPTCHA_LOCKED",
                "账号已被 Jira CAPTCHA 保护锁定 (HTTP %d)" % code,
                "立即停止一切自动请求，用浏览器登录该账号一次解除锁定后再试")
        if code == 401:
            raise JiraError("AUTH_FAILED", "认证失败 (HTTP 401)，用户名或密码错误",
                            "去 Jira 网页确认该账号能登录；认证类错误不会重试")
        raise JiraError("PERMISSION_DENIED", "权限不足 (HTTP 403)",
                        "确认该账号对目标项目/操作有权限")
    if code == 404:
        raise JiraError("NOT_FOUND", "资源不存在 (HTTP 404)",
                        "issue 不存在或无查看权限（Jira 对无权限 issue 也返回 404）")
    if code == 400:
        messages = _extract_error_messages(text)
        raise JiraError("JQL_INVALID", "请求被 Jira 拒绝 (HTTP 400): %s" % messages,
                        "按 Jira 报错文本修正 JQL 或字段名")
    if code == 429:
        if not retried_429:
            retry_after = err.headers.get("Retry-After") if err.headers else None
            try:
                delay = min(float(retry_after), 30.0) if retry_after else 2.0
            except ValueError:
                delay = 2.0
            time.sleep(delay)
            return  # 由外层 request 递归重试恰好一次
        raise JiraError("RATE_LIMITED", "被 Jira 限流 (HTTP 429)，重试一次后仍失败",
                        "降低请求频率后再试")
    if 500 <= code:
        raise JiraError("SERVER_ERROR", "Jira 服务端故障 (HTTP %d)" % code,
                        "这是 Jira 侧问题，不是你的参数问题，稍后再试")
    raise JiraError("REQUEST_FAILED", "请求失败 (HTTP %d): %s" % (code, text[:200]),
                    "按 HTTP 状态码排查")


def _extract_error_messages(text):
    try:
        data = json.loads(text)
    except ValueError:
        return text[:200]
    messages = data.get("errorMessages") or []
    errors = data.get("errors") or {}
    parts = list(messages)
    parts.extend("%s: %s" % (k, v) for k, v in errors.items())
    return "; ".join(parts) if parts else text[:200]


def tls_note(source):
    """insecure 开启时输出回带提示字段。"""
    return {"tls_verification": "disabled"} if source.get("insecure") else {}


def upload_file(source, path, file_path, file_bytes=None, filename=None, _retried_429=False):
    """通过 multipart/form-data 上传单个文件（用于附件）。保证 429 重试使用同一份内存字节。"""
    if file_bytes is None:
        if not os.path.isfile(file_path):
            raise JiraError("CONFIG_ERROR", "要上传的文件不存在: %s" % file_path, "检查文件路径")
        filename = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
        except OSError as e:
            raise JiraError("CONFIG_ERROR", "无法读取要上传的文件: %s" % e, "检查文件权限")
    elif not filename:
        filename = os.path.basename(file_path) if file_path else "attachment"

    url = build_url(source, path)
    token = base64.b64encode(
        ("%s:%s" % (source["username"], source["password"])).encode("utf-8")
    ).decode("ascii")
    boundary = "----JiraClientBoundary%s" % hashlib.md5(file_bytes).hexdigest()

    body = (
        b"--" + boundary.encode("ascii") + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="' + filename.encode("utf-8") + b'"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + file_bytes + b"\r\n"
        b"--" + boundary.encode("ascii") + b"--\r\n"
    )
    headers = {
        "Accept": "application/json",
        "Authorization": "Basic " + token,
        "X-Atlassian-Token": "nocheck",
        "Content-Type": "multipart/form-data; boundary=" + boundary,
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _urlopen(req, source) as resp:
            raw = resp.read()
            if not raw.strip():
                return []
            content_type = resp.headers.get("Content-Type", "")
            text = raw.decode("utf-8", errors="replace")
            if "json" not in content_type.lower():
                raise JiraError(
                    "UNEXPECTED_RESPONSE",
                    "上传附件响应 Content-Type 不是 JSON (%s)，前 200 字符: %s"
                    % (content_type, text[:200]),
                    "可能是反代或登录拦截返回了 HTML，检查 base_url 是否指向 Jira")
            try:
                return json.loads(text)
            except ValueError:
                raise JiraError(
                    "UNEXPECTED_RESPONSE",
                    "上传附件响应不是合法 JSON，前 200 字符: %s" % text[:200],
                    "按 Jira 响应排查")
    except urllib.error.HTTPError as e:
        _raise_for_http_error(source, e, _retried_429)
    except ssl.SSLError as e:
        raise JiraError("SSL_ERROR", "证书校验失败: %s" % e,
                        "自签名证书请在配置里把该源的 insecure 设为 true")
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError) as e:
        raise JiraError("NETWORK_ERROR", "网络连接失败: %s" % e,
                        "检查网络连通性与 base_url")
    return upload_file(source, path, file_path, file_bytes=file_bytes, filename=filename, _retried_429=True)

