#!/usr/bin/env python3
"""泰山应用信息 Skill 的本地辅助脚本。

这个脚本只保存和读取必要的 Cookie，不会打印 Cookie、token、密码或数据库凭据。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import getpass
import hashlib
import json
import logging
import os
import random
import re
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(
    os.environ.get("TAISHAN_AGENT_RUNTIME_DIR", Path.cwd() / ".agent-state")
).expanduser()
DEFAULT_CONFIG_DIR = DEFAULT_RUNTIME_DIR / "taishan-agent"
DEFAULT_COOKIE_FILE = DEFAULT_CONFIG_DIR / "cookie"
DEFAULT_OK_HEARTBEAT_STATE_FILE = DEFAULT_CONFIG_DIR / "biz-error-ok-heartbeat.json"
LEGACY_CONFIG_DIR = Path.home() / ".config" / "taishan-agent"
LEGACY_COOKIE_FILE = LEGACY_CONFIG_DIR / "cookie"
LEGACY_OK_HEARTBEAT_STATE_FILE = LEGACY_CONFIG_DIR / "biz-error-ok-heartbeat.json"
DEFAULT_APP_ID = "83"
DEFAULT_APP_ENG_NAME = "pixel-studio"
DEFAULT_APP_ENV = "production"
DEFAULT_FEISHU_USER_NAME = "陈致远"
DEFAULT_TAISHAN_LOGIN_URL = (
    "https://taishan.wanmeixiangsu.cn/#taishan.H0036?"
    "engName=pixel-studio&env=production&id=83"
)
DEFAULT_CHROME_PROFILE_DIR = (
    Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default"
)
LOGCENTER_LOG_QUERY_URL = "https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/query.htm"
LOGCENTER_BIZ_LOG_QUERY_RANGE_URL = (
    "https://logcenter.wanmeixiangsu.cn/api/admin/v2/biz-log/query-range.htm"
)
LOGCENTER_ACCESS_LOG_QUERY_URL = "https://logcenter.wanmeixiangsu.cn/api/admin/v2/log/query.htm"
SERVER_MANAGER_BASE_URL = "https://server-manager.wanmeixiangsu.cn"
SQL_DBS_URL = f"{SERVER_MANAGER_BASE_URL}/api/admin/sql/dbs.htm"
SQL_QUERY_APPROVE_CREATE_URL = (
    f"{SERVER_MANAGER_BASE_URL}/api/admin/sql-query-approve/create.htm"
)
SQL_QUERY_APPROVE_LIST_URL = f"{SERVER_MANAGER_BASE_URL}/api/admin/sql-query-approve/list.htm"
SQL_QUERY_INIT_URL = f"{SERVER_MANAGER_BASE_URL}/api/admin/sql/init.htm"
SQL_QUERY_URL = f"{SERVER_MANAGER_BASE_URL}/api/admin/sql/query.htm"
SQL_QUERY_RESULT_URL = f"{SERVER_MANAGER_BASE_URL}/api/admin/sql/get-result.htm"
SQL_QUERY_CLOSE_URL = f"{SERVER_MANAGER_BASE_URL}/api/admin/sql/close.htm"
BIZ_LOG_LEVEL_ALIASES = {
    "server": {"log_file_names": ["server"], "levels": []},
    "warning": {"log_file_names": [], "levels": ["WARN"]},
    "warn": {"log_file_names": [], "levels": ["WARN"]},
    "error": {"log_file_names": [], "levels": ["ERROR"]},
}
SENSITIVE_KEYWORDS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "cookie",
    "authorization",
    "credential",
    "private",
    "phone",
    "mobile",
    "email",
    "mail",
    "idcard",
    "identity",
    "userid",
    "user_id",
    "request_args",
    "user_agent",
    "x_forwarded_for",
    "request_ip",
    "ip",
    "device_id",
    "oa_id",
    "id_fa",
    "ad_id",
    "sign",
)
LOG_MESSAGE_FULL_REDACT_KEYWORDS = tuple(
    word for word in SENSITIVE_KEYWORDS if word not in {"userid", "user_id"}
)
LOKI_LABEL_KEYS = ("log_file_name", "pod_id", "profile", "app_name")
LOKI_TEXT_FILTER_KEYS = ("trace_id", "level")
MAX_SQL_QUERY_APPLY_HOURS = 12
READONLY_SQL_STARTERS = {"select", "show", "explain"}
WRITE_SQL_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "replace",
    "merge",
    "grant",
    "revoke",
    "call",
    "exec",
    "execute",
    "load",
    "lock",
    "unlock",
    "rename",
    "analyze",
    "optimize",
    "repair",
)


@dataclass(frozen=True)
class Capability:
    key: str
    title: str
    env_template: str
    description: str
    aliases: tuple[str, ...]
    default_route: str | None = None


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        key="sql-exec-records",
        title="SQL执行记录查看",
        env_template="TAISHAN_SQL_EXEC_RECORD_URL_TEMPLATE",
        description="查看指定应用的 SQL 执行记录。",
        aliases=("sql-records", "sql-exec", "SQL执行记录", "SQL执行记录查看"),
        default_route="taishan.H0009",
    ),
    Capability(
        key="sql-query-apply",
        title="SQL查询申请",
        env_template="TAISHAN_SQL_QUERY_APPLY_URL_TEMPLATE",
        description="发起或查看指定应用的 SQL 查询申请。",
        aliases=("sql-apply", "query-apply", "SQL查询申请"),
        default_route="taishan.H0008",
    ),
    Capability(
        key="controlled-sql-query",
        title="受控SQL查询",
        env_template="TAISHAN_CONTROLLED_SQL_QUERY_URL_TEMPLATE",
        description="执行或查看指定应用的受控 SQL 查询。",
        aliases=("controlled-sql", "safe-sql", "受控SQL查询"),
        default_route="taishan.H0008",
    ),
    Capability(
        key="biz-log-query",
        title="业务日志查询",
        env_template="TAISHAN_BIZ_LOG_QUERY_URL_TEMPLATE",
        description="查询指定应用的业务日志。",
        aliases=("biz-logs", "business-log", "业务日志查询"),
        default_route="taishan.H0036",
    ),
    Capability(
        key="access-log-query",
        title="访问日志查询",
        env_template="TAISHAN_ACCESS_LOG_QUERY_URL_TEMPLATE",
        description="查询指定应用的访问日志。",
        aliases=("access-logs", "访问日志查询"),
        default_route="taishan.H0033",
    ),
)


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def normalize_name(value: str) -> str:
    return "".join(value.lower().split())


def list_capabilities() -> list[dict[str, Any]]:
    """列出当前已支持的五项泰山能力。"""
    return [
        {
            "key": capability.key,
            "title": capability.title,
            "envTemplate": capability.env_template,
            "description": capability.description,
            "defaultRoute": capability.default_route,
            "aliases": list(capability.aliases),
        }
        for capability in CAPABILITIES
    ]


def resolve_capability(name: str) -> Capability:
    """用中文能力名、key 或别名解析能力配置。"""
    normalized = normalize_name(name)
    for capability in CAPABILITIES:
        candidates = (capability.key, capability.title, *capability.aliases)
        if normalized in {normalize_name(item) for item in candidates}:
            return capability
    supported = "、".join(item.title for item in CAPABILITIES)
    raise RuntimeError(f"未知泰山能力：{name}。当前支持：{supported}")


def parse_key_value(items: list[str] | None) -> dict[str, str]:
    """解析命令行 key=value 参数，供接口模板补齐过滤条件。"""
    result: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise RuntimeError(f"参数格式错误：{item}，请使用 key=value")
        key, value = item.split("=", 1)
        if not key:
            raise RuntimeError("参数 key 不能为空")
        result[key] = value
    return result


def build_app_context(
    app: dict[str, Any] | None = None,
    app_id: str | None = None,
    eng_name: str | None = None,
) -> dict[str, Any]:
    """合成接口模板上下文，确保常用占位符始终可用。"""
    context: dict[str, Any] = {}
    if app:
        context.update(app)
    if app_id is not None:
        context["id"] = app_id
    if eng_name is not None:
        context["engName"] = eng_name
    return redact(context)


def build_capability_url(
    capability: Capability,
    app: dict[str, Any],
    params: dict[str, str],
    template: str = "",
) -> str:
    """根据能力模板生成请求 URL。

    模板来自环境变量或命令行，不在代码里硬编码未知接口，避免猜错后污染能力。
    """
    url_template = template or os.environ.get(capability.env_template, "")
    if not url_template:
        raise RuntimeError(
            f"缺少 {capability.title} 的接口模板，请设置 {capability.env_template}。"
        )

    context = {**app, **params}
    encoded_context = {
        key: urllib.parse.quote(str(value), safe="")
        for key, value in context.items()
        if value is not None
    }
    try:
        return url_template.format(**encoded_context)
    except KeyError as exc:
        raise RuntimeError(f"接口模板缺少占位符参数：{exc.args[0]}") from exc


def is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(word in lower for word in SENSITIVE_KEYWORDS)


def redact(value: Any, key: str = "") -> Any:
    """递归脱敏，避免把生产凭据写到输出里。"""
    if is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: redact(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and any(word in value.lower() for word in SENSITIVE_KEYWORDS):
        return "[REDACTED]"
    return value


def redact_log_message(message: Any) -> Any:
    """对日志正文做更细粒度脱敏，尽量保留排障上下文。"""
    if not isinstance(message, str):
        return redact(message)
    if any(word in message.lower() for word in LOG_MESSAGE_FULL_REDACT_KEYWORDS):
        return "[REDACTED]"
    return re.sub(
        r"(?i)(userId|eventUserId|createUserId|updateUserId)\s*[:=]\s*\[?[0-9a-zA-Z_-]{8,}\]?",
        r"\1=[REDACTED]",
        message,
    )


def parse_nested_json_fields(app: dict[str, Any]) -> dict[str, Any]:
    """泰山会把部分字段作为 JSON 字符串塞进 app 参数，这里做一次结构化。"""
    parsed = dict(app)
    for field in ("config", "dbConn", "metadata", "secretConfig", "templateList"):
        raw = parsed.get(field)
        if isinstance(raw, str) and raw.strip():
            try:
                parsed[field] = json.loads(raw)
            except json.JSONDecodeError:
                # 不是 JSON 时保留原值，后续统一脱敏。
                parsed[field] = raw
    return parsed


def parse_taishan_url(url: str) -> dict[str, Any]:
    parsed_url = urllib.parse.urlparse(url)
    hash_value = parsed_url.fragment
    route, _, query_string = hash_value.partition("?")
    params = urllib.parse.parse_qs(query_string, keep_blank_values=True)
    flat_params = {key: values[-1] if values else "" for key, values in params.items()}

    app: dict[str, Any] | None = None
    if flat_params.get("app"):
        app = json.loads(flat_params["app"])
        app = parse_nested_json_fields(app)

    return {
        "origin": f"{parsed_url.scheme}://{parsed_url.netloc}",
        "route": route,
        "query": redact(flat_params),
        "app": redact(app) if app else None,
    }


def app_summary(app: dict[str, Any]) -> dict[str, Any]:
    """提取最常用的应用信息，便于 Agent 稳定输出。"""
    fields = (
        "id",
        "referId",
        "chnName",
        "engName",
        "appType",
        "env",
        "description",
        "domainName",
        "internalDomainName",
        "otherDomain",
        "projectId",
        "gitProjectId",
        "apisixAppId",
        "status",
        "cpu",
        "memory",
        "disk",
        "replicas",
        "tags",
        "userName",
        "updateUserName",
        "updateTime",
        "createTime",
    )
    result = {field: app.get(field) for field in fields if field in app}
    for time_field in ("updateTime", "createTime"):
        if isinstance(result.get(time_field), (int, float)):
            result[f"{time_field}Text"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(float(result[time_field]) / 1000)
            )
    return redact(result)


def migrate_legacy_file(target: Path, legacy: Path) -> Path:
    """把旧 ~/.config 文件一次性迁移到项目运行目录，避免打断已有自动化。"""
    if target.exists() or not legacy.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(stat.S_IRUSR | stat.S_IWUSR)
    logging.info("已把旧本机私有文件迁移到当前项目运行目录。")
    return target


def cookie_file() -> Path:
    path = Path(os.environ.get("TAISHAN_COOKIE_FILE", DEFAULT_COOKIE_FILE)).expanduser()
    if "TAISHAN_COOKIE_FILE" not in os.environ:
        return migrate_legacy_file(path, LEGACY_COOKIE_FILE)
    return path


def save_cookie(cookie: str) -> Path:
    if not cookie.strip():
        raise ValueError("Cookie 不能为空")
    path = cookie_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cookie.strip() + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    logging.info("Cookie 已保存到本机私有文件，后续请求会自动读取。")
    return path


def chrome_cookie_db_path(profile_dir: str | Path) -> Path:
    """定位 Chrome Cookie 数据库，兼容不同 Chrome 版本的存放位置。"""
    profile = Path(profile_dir).expanduser()
    candidates = [profile / "Cookies", profile / "Network" / "Cookies"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"未找到 Chrome Cookie 数据库：{profile}")


def chrome_safe_storage_password() -> bytes:
    """从 macOS Keychain 读取 Chrome Cookie 解密口令。"""
    try:
        value = subprocess.check_output(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("无法读取 Chrome Safe Storage，请确认已允许访问钥匙串。") from exc
    if not value:
        raise RuntimeError("Chrome Safe Storage 为空，无法解密 Cookie。")
    return value.encode("utf-8")


def strip_chrome_cookie_host_digest(host_key: str, plaintext: bytes) -> str:
    """Chrome 新版本会在明文前拼 host_key 的 SHA256 摘要，这里剥离后再解码。"""
    digest = hashlib.sha256(host_key.encode("utf-8")).digest()
    if plaintext.startswith(digest):
        plaintext = plaintext[len(digest) :]
    return plaintext.decode("utf-8", errors="ignore")


def decrypt_chrome_cookie_value(host_key: str, encrypted_value: bytes, value: str = "") -> str:
    """解密 Chrome v10/v11 Cookie 值。

    macOS Chrome 的 Cookie 通过 Keychain 派生 AES-CBC key；解密过程只在内存中进行。
    """
    if value:
        return value
    if not encrypted_value:
        return ""
    encrypted = encrypted_value
    if encrypted.startswith(b"v10") or encrypted.startswith(b"v11"):
        encrypted = encrypted[3:]
    key = hashlib.pbkdf2_hmac("sha1", chrome_safe_storage_password(), b"saltysalt", 1003, 16)
    iv = b" " * 16
    with tempfile.NamedTemporaryFile(delete=False) as input_file:
        input_file.write(encrypted)
        input_path = input_file.name
    try:
        plaintext = subprocess.check_output(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-128-cbc",
                "-K",
                key.hex(),
                "-iv",
                iv.hex(),
                "-in",
                input_path,
            ],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Chrome Cookie 解密失败，请确认 Chrome 版本和钥匙串权限。") from exc
    finally:
        Path(input_path).unlink(missing_ok=True)
    return strip_chrome_cookie_host_digest(host_key, plaintext)


def build_cookie_header_from_pairs(
    cookie_pairs: dict[str, str],
    allowed_names: list[str],
) -> str:
    """按白名单组装 Cookie Header，避免保存无关浏览器 Cookie。"""
    parts: list[str] = []
    for name in allowed_names:
        value = cookie_pairs.get(name)
        if value:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def read_chrome_cookie_pairs(
    profile_dir: str | Path,
    domains: list[str],
    names: list[str],
) -> dict[str, str]:
    """从 Chrome Cookie DB 读取并解密指定域名和名称的 Cookie。"""
    db_path = chrome_cookie_db_path(profile_dir)
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)
    try:
        # Chrome 运行时会锁库，复制快照后只读查询更稳定。
        shutil.copy2(db_path, tmp_path)
        conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
        try:
            name_placeholders = ",".join("?" for _ in names)
            domain_clause = " OR ".join("host_key LIKE ?" for _ in domains)
            params: list[str] = list(names)
            params.extend(f"%{domain}" for domain in domains)
            query = (
                "SELECT host_key, name, value, encrypted_value "
                "FROM cookies "
                f"WHERE name IN ({name_placeholders}) AND ({domain_clause}) "
                "ORDER BY last_access_utc DESC, creation_utc DESC"
            )
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    result: dict[str, str] = {}
    for host_key, name, value, encrypted_value in rows:
        if name in result:
            continue
        result[name] = decrypt_chrome_cookie_value(host_key, encrypted_value, value)
    return result


def open_login_url_in_browser(browser: str, url: str) -> None:
    """打开登录页。扫码登录由用户完成，脚本只负责等待 Cookie 落盘。"""
    if browser != "chrome":
        raise RuntimeError(f"暂不支持的浏览器：{browser}")
    subprocess.run(["open", "-a", "Google Chrome", url], check=False)


def validate_logcenter_cookie(cookie: str) -> bool:
    """用轻量业务日志查询确认 Cookie 没有命中统一登录页。"""
    end_ms = int(time.time() * 1000)
    params = {
        "_r": int(time.time() * 1_000_000),
        "end": end_ms * 1_000_000,
        "limit": 1,
        "query": build_biz_log_loki_query(
            app_name=DEFAULT_APP_ENG_NAME,
            profile=DEFAULT_APP_ENV,
            levels=["ERROR"],
        ),
        "start": (end_ms - 60 * 1000) * 1_000_000,
        "taishanId": int(DEFAULT_APP_ID),
        "_": random.random(),
    }
    try:
        response = request_json(build_biz_log_query_range_url(params), cookie, method="GET")
    except Exception as exc:  # noqa: BLE001 - 校验失败只作为轮询条件，不暴露内部细节。
        logging.info("Cookie 校验暂未通过：%s", exc)
        return False
    payload = response.get("data", {})
    return bool(isinstance(payload, dict) and payload.get("success") is True)


def refresh_cookie_from_chrome(args: argparse.Namespace) -> Path:
    """打开 Chrome 等待扫码登录，从 Cookie 库中提取并保存 logcenter 可用 Cookie。"""
    cookie_names = split_multi_values(args.cookie_name) or ["__CLIENT_USER_TOKEN__"]
    domains = split_multi_values(args.cookie_domain) or ["wanmeixiangsu.cn"]
    if not args.no_open:
        logging.info("正在打开 Chrome 登录页，请在浏览器中完成扫码登录。")
        open_login_url_in_browser(args.browser, args.url)

    deadline = time.time() + args.timeout
    last_header = ""
    while time.time() <= deadline:
        pairs = read_chrome_cookie_pairs(args.profile_dir, domains, cookie_names)
        header = build_cookie_header_from_pairs(pairs, cookie_names)
        if header:
            last_header = header
            if not args.validate or validate_logcenter_cookie(header):
                return save_cookie(header)
        time.sleep(args.interval)
    if last_header:
        raise RuntimeError("已从 Chrome 读取到目标 Cookie，但校验未通过，可能仍未完成登录或登录态未同步。")
    raise RuntimeError("超时未从 Chrome 读取到目标 Cookie，请确认已在 Chrome 中完成泰山登录。")


def load_cookie() -> str:
    env_cookie = os.environ.get("TAISHAN_COOKIE", "").strip()
    if env_cookie:
        logging.info("已从环境变量加载 Cookie。")
        return env_cookie

    path = cookie_file()
    if not path.exists():
        raise FileNotFoundError(
            f"未找到 Cookie。请设置 TAISHAN_COOKIE，或运行 auth set-cookie 保存到 {path}"
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        logging.warning("Cookie 文件权限偏宽，建议执行 chmod 600 %s", path)
    logging.info("已从本机私有文件加载 Cookie。")
    return path.read_text(encoding="utf-8").strip()


def request_json(
    url: str,
    cookie: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """发起带 Cookie 的 HTTP JSON 请求，并保留响应元信息。

    Cookie 只放入请求 Header，不会写入返回对象，避免误打印登录凭据。
    """
    encoded_body: bytes | None = None
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "taishan-agent/0.1",
        "Referer": "https://taishan.wanmeixiangsu.cn/",
        "Origin": "https://taishan.wanmeixiangsu.cn",
        "Cookie": cookie,
    }
    if body is not None:
        encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json;charset=UTF-8"

    request = urllib.request.Request(url, data=encoded_body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("泰山接口返回未授权，Cookie 可能已失效。") from exc
        raise

    if status in (401, 403):
        raise RuntimeError("泰山接口返回未授权，Cookie 可能已失效。")

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        preview = body[:200].replace("\n", " ")
        raise RuntimeError(f"接口返回不是 JSON，可能命中了登录页或网关错误：{preview}") from exc

    return {
        "status": status,
        "url": final_url,
        "contentType": content_type,
        "data": data,
    }


def request_form_json(url: str, cookie: str, body: dict[str, Any]) -> dict[str, Any]:
    """按 logcenter 访问日志接口的表单格式发起请求。"""
    encoded_body = urllib.parse.urlencode(body).encode("utf-8")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "taishan-agent/0.1",
        "Referer": "https://taishan.wanmeixiangsu.cn/",
        "Origin": "https://taishan.wanmeixiangsu.cn",
        "Cookie": cookie,
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    }
    request = urllib.request.Request(url, data=encoded_body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("泰山接口返回未授权，Cookie 可能已失效。") from exc
        raise

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError as exc:
        preview = response_body[:200].replace("\n", " ")
        raise RuntimeError(f"接口返回不是 JSON，可能命中了登录页或网关错误：{preview}") from exc

    return {
        "status": status,
        "url": final_url,
        "contentType": content_type,
        "data": data,
    }


def fetch_json(url: str, cookie: str) -> Any:
    return request_json(url, cookie)["data"]


def build_url_with_params(url: str, params: dict[str, Any]) -> str:
    """给 GET 接口追加非空查询参数。"""
    clean = {key: value for key, value in params.items() if value not in (None, "")}
    if not clean:
        return url
    return f"{url}?{urllib.parse.urlencode(clean)}"


def require_positive_int(value: Any, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} 必须是整数") from exc
    if result <= 0:
        raise RuntimeError(f"{name} 必须大于 0")
    return result


def require_sql_apply_hours(value: Any) -> int:
    hours = require_positive_int(value, "--apply-hours")
    if hours > MAX_SQL_QUERY_APPLY_HOURS:
        raise RuntimeError(f"SQL 查询权限申请最长 {MAX_SQL_QUERY_APPLY_HOURS} 小时")
    return hours


def unwrap_taishan_data(response: dict[str, Any]) -> Any:
    """兼容泰山常见包装：request_json 返回元信息，业务体里再包 success/data。"""
    payload = response.get("data")
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def ensure_taishan_success(response: dict[str, Any]) -> None:
    payload = response.get("data")
    if not isinstance(payload, dict):
        return
    if payload.get("success") is False:
        error_code = payload.get("errorCode")
        message = payload.get("message") or payload.get("msg") or "未知错误"
        raise RuntimeError(f"泰山接口返回失败：errorCode={error_code} message={message}")


def strip_sql_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"(?m)--.*?$", " ", without_block)


def first_sql_token(sql: str) -> str:
    match = re.match(r"\s*([A-Za-z]+)", sql)
    return match.group(1).lower() if match else ""


def redact_sql_literals(sql: str) -> str:
    """输出 SQL 证据时隐藏字面量，避免把手机号、token 等写进日志。"""
    redacted = re.sub(r"'(?:''|[^'])*'", "'[REDACTED]'", sql)
    redacted = re.sub(r'"(?:""|[^"])*"', '"[REDACTED]"', redacted)
    return redacted


def prepare_readonly_sql(sql: str, max_rows: int, auto_limit: bool = True) -> str:
    """校验并准备 Taishan 受控 SQL 查询，只允许只读语句。"""
    if not sql or not sql.strip():
        raise RuntimeError("SQL 不能为空")
    max_rows = require_positive_int(max_rows, "--max-rows")
    normalized = strip_sql_comments(sql).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.rstrip(";").strip()
    if ";" in normalized:
        raise RuntimeError("只允许单条 SQL，不允许多语句")

    starter = first_sql_token(normalized)
    if starter not in READONLY_SQL_STARTERS:
        raise RuntimeError("只允许只读 SQL：SELECT / SHOW / EXPLAIN")

    lower = normalized.lower()
    if any(re.search(rf"\b{keyword}\b", lower) for keyword in WRITE_SQL_KEYWORDS):
        raise RuntimeError("只允许只读 SQL，禁止写入、DDL、授权、执行过程等操作")
    if re.search(r"\binto\s+outfile\b|\bload_file\s*\(", lower):
        raise RuntimeError("只允许只读 SQL，禁止文件读写相关操作")

    limit_match = re.search(r"\blimit\s+(\d+)\b", lower)
    if starter == "select":
        if limit_match:
            limit_value = int(limit_match.group(1))
            if limit_value > max_rows:
                raise RuntimeError(f"SQL LIMIT={limit_value} 超过最大行数 {max_rows}")
        elif auto_limit:
            normalized = f"{normalized} LIMIT {max_rows}"
        else:
            raise RuntimeError("SELECT 查询必须带 LIMIT，或启用自动 LIMIT")
    return normalized


def build_sql_query_apply_body(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "appId": require_positive_int(args.id, "--app-id"),
        "index": require_positive_int(args.db_index, "--db-index"),
        "applyHours": require_sql_apply_hours(args.apply_hours),
        "remark": args.remark.strip() if args.remark else "",
    }


def build_sql_query_apply_list_params(args: argparse.Namespace) -> dict[str, Any]:
    mapping = {
        "approveSystemId": getattr(args, "approve_system_id", ""),
        "appId": require_positive_int(args.id, "--app-id") if getattr(args, "id", None) else "",
        "address": getattr(args, "address", ""),
        "dbName": getattr(args, "db_name", ""),
        "status": getattr(args, "status", ""),
        "createUserName": getattr(args, "create_user_name", ""),
        "approveUserName": getattr(args, "approve_user_name", ""),
        "page": require_positive_int(args.page, "--page"),
        "limit": require_positive_int(args.limit, "--limit"),
    }
    return {key: value for key, value in mapping.items() if value not in (None, "")}


def extract_item_list(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = unwrap_taishan_data(response)
    if not isinstance(data, dict):
        return []
    items = data.get("itemList") or data.get("list") or data.get("records") or []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def parse_epoch_millis(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return None
    # 兼容秒级时间戳。
    if 0 < timestamp < 10_000_000_000:
        return timestamp * 1000
    return timestamp


def sql_permission_status_text(item: dict[str, Any]) -> str:
    values = [
        item.get("statusName"),
        item.get("statusText"),
        item.get("statusDesc"),
        item.get("approveStatusName"),
        item.get("status"),
    ]
    return " ".join(str(value).lower() for value in values if value not in (None, ""))


def is_sql_permission_approved(item: dict[str, Any]) -> bool:
    text = sql_permission_status_text(item)
    return any(
        keyword in text
        for keyword in ("通过", "approved", "approve", "pass", "授权", "生效")
    )


def is_sql_permission_unexpired(item: dict[str, Any], now_ms: int | None = None) -> bool:
    expires_at = parse_epoch_millis(item.get("expireTime") or item.get("expiresAt"))
    if expires_at is None:
        return True
    current = int(time.time() * 1000) if now_ms is None else now_ms
    return expires_at > current


def item_matches_sql_permission_scope(
    item: dict[str, Any],
    db_name: str | None = None,
    address: str | None = None,
) -> bool:
    if db_name and str(item.get("dbName") or "") != db_name:
        return False
    if address and str(item.get("address") or "") != address:
        return False
    return True


def find_active_sql_permission(
    response: dict[str, Any],
    db_name: str | None = None,
    address: str | None = None,
    now_ms: int | None = None,
) -> dict[str, Any] | None:
    for item in extract_item_list(response):
        if not item_matches_sql_permission_scope(item, db_name=db_name, address=address):
            continue
        if is_sql_permission_approved(item) and is_sql_permission_unexpired(item, now_ms=now_ms):
            return item
    return None


def summarize_item_list_response(response: dict[str, Any]) -> dict[str, Any]:
    data = unwrap_taishan_data(response)
    if isinstance(data, dict):
        items = data.get("itemList") or data.get("list") or data.get("records") or []
        summary: dict[str, Any] = {
            "total": data.get("total", len(items) if isinstance(items, list) else None),
            "items": redact(items),
        }
        if isinstance(items, list):
            summary["returned"] = len(items)
        return summary
    return {"data": redact(data)}


def summarize_sql_query_response(response: dict[str, Any], max_rows: int) -> dict[str, Any]:
    data = unwrap_taishan_data(response)
    if not isinstance(data, dict):
        return {"data": redact(data)}
    rows = data.get("rows")
    data_source = data.get("dataSource")
    row_values = rows if isinstance(rows, list) else data_source if isinstance(data_source, list) else []
    max_rows = require_positive_int(max_rows, "--max-rows")
    summary = {
        "finished": data.get("finished"),
        "execTime": data.get("execTime"),
        "message": data.get("message"),
        "columns": redact(data.get("columns", [])),
        "rowCount": len(row_values) if isinstance(row_values, list) else None,
        "rows": redact(row_values[:max_rows]) if isinstance(row_values, list) else [],
    }
    return summary


def split_multi_values(values: list[str] | None) -> list[str]:
    """支持逗号分隔和重复参数两种写法，过滤空值。"""
    result: list[str] = []
    for value in values or []:
        result.extend(item.strip() for item in value.split(",") if item.strip())
    return result


def normalize_biz_log_filters(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """把用户友好的业务日志级别映射成前端使用的 Loki 过滤条件。"""
    text_levels: list[str] = []
    log_file_names = split_multi_values(args.log_file_name)
    for item in split_multi_values(args.level):
        normalized = item.lower()
        if normalized in BIZ_LOG_LEVEL_ALIASES:
            mapping = BIZ_LOG_LEVEL_ALIASES[normalized]
            text_levels.extend(mapping["levels"])
            log_file_names.extend(mapping["log_file_names"])
        else:
            # 兼容老用法：允许直接传 INFO、WARN、ERROR 等日志文本级别。
            text_levels.append(item.upper())
    return text_levels, log_file_names


def loki_label_expr(key: str, values: list[str]) -> str | None:
    """按泰山前端规则生成 Loki label 条件。"""
    if not values:
        return None
    if len(values) == 1:
        return f'{key}="{values[0]}"'
    return f'{key}=~"({"|".join(values)})"'


def build_biz_log_loki_query(
    app_name: str,
    profile: str,
    keywords: list[str] | None = None,
    levels: list[str] | None = None,
    log_file_names: list[str] | None = None,
    pod_ids: list[str] | None = None,
) -> str:
    """生成与业务日志前端一致的 Loki 查询字符串。"""
    labels: list[str] = ['infra_type="app"']
    label_values = {
        "log_file_name": log_file_names or [],
        "pod_id": pod_ids or [],
        "profile": [profile] if profile else [],
        "app_name": [app_name] if app_name else [],
    }
    for key in LOKI_LABEL_KEYS:
        expr = loki_label_expr(key, label_values[key])
        if expr:
            labels.append(expr)

    filters: list[str] = []
    for keyword in keywords or []:
        filters.append(f'|=`{keyword}`')
    for level in levels or []:
        filters.append(f'|=`{level}`')

    query = "{" + ",".join(labels) + "}"
    if filters:
        query += " " + "".join(filters)
    return query


def build_biz_log_request(args: argparse.Namespace) -> dict[str, Any]:
    """构造业务日志查询请求体，时间戳单位与前端保持一致：纳秒。"""
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.minutes * 60 * 1000
    text_levels, log_file_names = normalize_biz_log_filters(args)
    return {
        "query": build_biz_log_loki_query(
            app_name=args.eng_name,
            profile=args.env,
            keywords=split_multi_values(args.keyword),
            levels=text_levels,
            log_file_names=log_file_names,
            pod_ids=split_multi_values(args.pod_id),
        ),
        "start": start_ms * 1_000_000,
        "end": end_ms * 1_000_000,
        "limit": args.limit,
        "taishanId": int(args.id),
    }


def build_biz_log_query_range_params(args: argparse.Namespace) -> dict[str, Any]:
    """构造业务日志真实查询接口的 GET 参数。"""
    request_body = build_biz_log_request(args)
    return {
        "_r": int(time.time() * 1_000_000),
        "end": request_body["end"],
        "limit": request_body["limit"],
        "query": request_body["query"],
        "start": request_body["start"],
        "taishanId": request_body["taishanId"],
        "_": random.random(),
    }


def build_biz_log_query_range_url(params: dict[str, Any]) -> str:
    """把业务日志 GET 参数编码成真实请求 URL。"""
    query = urllib.parse.urlencode(params)
    return f"{LOGCENTER_BIZ_LOG_QUERY_RANGE_URL}?{query}"


def format_local_time(seconds: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(seconds))


def build_access_log_query(args: argparse.Namespace) -> str:
    """构造访问日志 q 参数，语法与前端 getQueryStr 保持一致。"""
    if args.query:
        return args.query
    clauses: list[str] = []
    if args.host:
        hosts = split_multi_values([args.host])
        # 前端对 request_host 使用 has([...],request_host)，注意逗号后不能加空格。
        host_array = json.dumps(hosts, ensure_ascii=False, separators=(",", ":"))
        clauses.append(f"has({host_array},request_host)")
    if args.path:
        clauses.append(f"request_path = {args.path}")
    if args.method:
        clauses.append(f"method = {args.method.upper()}")
    if args.status:
        clauses.append(f"status = {args.status}")
    return " and ".join(clauses)


def build_access_log_request(args: argparse.Namespace) -> dict[str, Any]:
    """构造访问日志查询表单参数，时间格式与前端保持一致。"""
    if args.start_time and args.end_time:
        start_time = args.start_time
        end_time = args.end_time
    else:
        end_seconds = time.time() - args.lag_seconds
        start_seconds = end_seconds - args.minutes * 60
        start_time = format_local_time(start_seconds)
        end_time = format_local_time(end_seconds)
    body: dict[str, Any] = {
        "appName": args.eng_name,
        "startTime": start_time,
        "endTime": end_time,
        "q": build_access_log_query(args),
        "page": args.page,
        # 访问日志前端固定 LOG_LIMIT=25；后端对过小 limit 会返回“查询出错”。
        "limit": max(args.limit, 25),
    }
    if args.profile_id:
        body["appName"] = ""
        body["profileId"] = args.profile_id
        hosts = split_multi_values([args.host] if args.host else None)
        body["hosts"] = json.dumps(hosts, ensure_ascii=False)
    return body


def build_access_log_query_url() -> str:
    """访问日志查询 URL 会带前端同款缓存击穿参数。"""
    params = {
        "_r": int(time.time() * 1_000_000),
        "_": random.random(),
    }
    return f"{LOGCENTER_ACCESS_LOG_QUERY_URL}?{urllib.parse.urlencode(params)}"


def format_ns_timestamp(value: Any) -> str:
    """把 Loki 纳秒时间戳转成本地可读时间。"""
    try:
        seconds = int(str(value)) / 1_000_000_000
    except (TypeError, ValueError):
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(seconds))


def get_biz_log_loki_payload(api_payload: dict[str, Any]) -> dict[str, Any]:
    """从泰山包装响应中取出 Loki 原始 payload。"""
    data = api_payload.get("data") if isinstance(api_payload, dict) else None
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return {}


def summarize_biz_log_response(response: dict[str, Any]) -> dict[str, Any]:
    """提取业务日志查询的简洁摘要和日志列表。"""
    api_payload = response.get("data", {})
    api_data = api_payload.get("data", {}) if isinstance(api_payload, dict) else {}
    loki_payload = get_biz_log_loki_payload(api_payload)
    result = loki_payload.get("result", []) if isinstance(loki_payload, dict) else []
    stats_summary = (
        loki_payload.get("stats", {}).get("summary", {})
        if isinstance(loki_payload, dict)
        else {}
    )
    logs: list[dict[str, Any]] = []
    for item in result if isinstance(result, list) else []:
        if not isinstance(item, dict):
            continue
        stream = item.get("stream") if isinstance(item.get("stream"), dict) else {}
        values = item.get("values") if isinstance(item.get("values"), list) else []
        timestamp = values[0] if len(values) > 0 else ""
        message = values[1] if len(values) > 1 else ""
        logs.append(
            {
                "time": format_ns_timestamp(timestamp),
                "timestampNs": timestamp,
                "level": stream.get("detected_level") or "",
                "logFile": stream.get("log_file_name") or "",
                "podId": stream.get("pod_id") or "",
                "message": redact_log_message(message),
            }
        )

    return {
        "httpStatus": response.get("status"),
        "success": api_payload.get("success") if isinstance(api_payload, dict) else None,
        "errorCode": api_payload.get("errorCode") if isinstance(api_payload, dict) else None,
        "status": api_data.get("status") if isinstance(api_data, dict) else None,
        "resultType": loki_payload.get("resultType") if isinstance(loki_payload, dict) else None,
        "returned": len(logs),
        "totalEntriesReturned": stats_summary.get("totalEntriesReturned"),
        "logs": logs,
    }


def summarize_access_log_response(response: dict[str, Any]) -> dict[str, Any]:
    """提取访问日志查询的简洁摘要和日志列表。"""
    api_payload = response.get("data", {})
    if isinstance(api_payload, dict) and isinstance(api_payload.get("data"), list):
        rows = api_payload.get("data", [])
        paging = api_payload.get("paging", {})
    else:
        result_payload = api_payload.get("data", {}) if isinstance(api_payload, dict) else {}
        rows = result_payload.get("data", []) if isinstance(result_payload, dict) else []
        paging = result_payload.get("paging", {}) if isinstance(result_payload, dict) else {}
    logs: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        log_data: dict[str, Any] = {}
        raw_log_data = row.get("logData")
        if isinstance(raw_log_data, str) and raw_log_data.strip():
            try:
                parsed = json.loads(raw_log_data)
                if isinstance(parsed, dict):
                    log_data = parsed
            except json.JSONDecodeError:
                log_data = {}
        logs.append(
            {
                "logTime": row.get("logTime"),
                "requestHost": row.get("request_host") or log_data.get("request_host"),
                "requestPath": row.get("request_path") or log_data.get("request_path"),
                "method": row.get("method") or log_data.get("request_method") or log_data.get("method"),
                "status": row.get("status") or log_data.get("request_http_status") or log_data.get("status"),
                "cost": row.get("cost") or log_data.get("request_time") or log_data.get("cost"),
                "logData": redact(log_data) if log_data else redact(row),
            }
        )
    return {
        "httpStatus": response.get("status"),
        "success": api_payload.get("success") if isinstance(api_payload, dict) else None,
        "errorCode": api_payload.get("errorCode") if isinstance(api_payload, dict) else None,
        "message": api_payload.get("message") if isinstance(api_payload, dict) else None,
        "returned": len(logs),
        "paging": paging,
        "logs": logs,
    }


def should_send_biz_error_alert(summary: dict[str, Any]) -> bool:
    """只有真实返回 error 日志时才发送飞书，避免定时任务空跑打扰。"""
    try:
        return int(summary.get("returned") or 0) > 0
    except (TypeError, ValueError):
        return False


def normalize_log_signature(message: str) -> str:
    """生成告警聚合用签名，不用于展示原文。"""
    normalized = str(redact_log_message(message))
    normalized = re.sub(r"\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:. -]+\]", "[TIME]", normalized)
    normalized = re.sub(r"\[(?:http-nio|scheduler|pool|task|ForkJoinPool|Dubbo|grpc|lettuce|mysql|redis)[^\]]*\]", "[THREAD]", normalized, flags=re.I)
    normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>", normalized, flags=re.I)
    normalized = re.sub(r"\b\d{6,}\b", "<NUM>", normalized)
    normalized = re.sub(r"userId\s*[:=]\s*[^,\s]+", "userId=<ID>", normalized, flags=re.I)
    normalized = re.sub(r"taskId\s*[:=]\s*[^,\s]+", "taskId=<ID>", normalized, flags=re.I)
    normalized = re.sub(r"traceId\s*[:=]\s*[^,\s]+", "traceId=<ID>", normalized, flags=re.I)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:1000]


def classify_log_message(message: str, log_file: str) -> str:
    """把日志正文归类为面向人的短标签，不泄露异常原文。"""
    lower = message.lower()
    if log_file == "druidWallFilter" or "sql injection violation" in lower:
        return "Druid SQL 安全规则拦截"
    if message.strip() == "[REDACTED]":
        return "敏感日志已脱敏"
    if re.fullmatch(r"[-=_*.\s]{20,}", message.strip()):
        return "分隔线日志"
    if "exception" in lower:
        return "应用异常"
    if "error" in lower:
        return "错误日志"
    return "同类 error"


def summarize_log_groups(logs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for log in logs:
        if not isinstance(log, dict):
            continue
        log_file = str(log.get("logFile") or "-")
        message = str(log.get("message") or "")
        signature = hashlib.sha256(f"{log_file}|{normalize_log_signature(message)}".encode("utf-8")).hexdigest()[:12]
        group = groups.setdefault(
            signature,
            {
                "signature": signature,
                "logFile": log_file,
                "category": classify_log_message(message, log_file),
                "count": 0,
                "firstTime": log.get("time"),
                "lastTime": log.get("time"),
                "pods": set(),
            },
        )
        group["count"] += 1
        group["lastTime"] = log.get("time") or group["lastTime"]
        if log.get("time") and (not group["firstTime"] or str(log.get("time")) < str(group["firstTime"])):
            group["firstTime"] = log.get("time")
        if log.get("podId"):
            group["pods"].add(str(log.get("podId")))
    result = sorted(groups.values(), key=lambda item: int(item["count"]), reverse=True)
    for item in result:
        item["podCount"] = len(item.pop("pods"))
    return result[:limit]


def format_biz_error_alert(summary: dict[str, Any], args: argparse.Namespace) -> str:
    """把业务 error 日志摘要整理成适合飞书私聊的纯文本。"""
    logs = summary.get("logs") if isinstance(summary.get("logs"), list) else []
    display_limit = int(getattr(args, "limit", 20) or 20)
    groups = summarize_log_groups(logs, display_limit)
    lines = [
        f"泰山业务日志告警：{args.eng_name} / {args.env}",
        f"最近 {args.minutes} 分钟发现 {summary.get('returned', 0)} 条 error 日志。",
        f"同类异常 {len(groups)} 组；以下为聚合摘要，未包含异常原文。",
    ]
    for index, group in enumerate(groups, start=1):
        lines.append(
            f"{index}. {group['category']} / {group['logFile']}：{group['count']} 次，"
            f"实例数 {group['podCount']}，时间 {group.get('firstTime') or '-'} ~ {group.get('lastTime') or '-'}，"
            f"指纹 {group['signature']}"
        )
    return "\n".join(lines)


def format_biz_error_ok_message(summary: dict[str, Any], args: argparse.Namespace) -> str:
    """生成无 error 时的健康心跳消息，让用户确认巡检仍在运行。"""
    check_time = format_local_time(time.time())
    return "\n".join(
        [
            f"泰山业务日志巡检正常：{args.eng_name} / {args.env}",
            f"最近 {args.minutes} 分钟未发现 error 日志。",
            f"巡检时间：{check_time}",
        ]
    )


def ok_heartbeat_state_key(args: argparse.Namespace) -> str:
    """同一服务和环境共用一条正常心跳节流记录。"""
    return f"{args.eng_name}:{args.env}"


def read_ok_heartbeat_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path).expanduser()
    if state_path == DEFAULT_OK_HEARTBEAT_STATE_FILE:
        state_path = migrate_legacy_file(state_path, LEGACY_OK_HEARTBEAT_STATE_FILE)
    if not state_path.exists():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def should_send_ok_heartbeat(args: argparse.Namespace, now: float | None = None) -> bool:
    """根据本地状态判断是否到了发送正常心跳的时间。"""
    interval_minutes = int(getattr(args, "ok_interval_minutes", 0) or 0)
    if interval_minutes <= 0:
        return True
    current = time.time() if now is None else now
    state = read_ok_heartbeat_state(args.ok_state_file)
    last_sent = state.get(ok_heartbeat_state_key(args))
    try:
        last_sent_seconds = float(last_sent)
    except (TypeError, ValueError):
        return True
    return current - last_sent_seconds >= interval_minutes * 60


def mark_ok_heartbeat_sent(args: argparse.Namespace, now: float | None = None) -> None:
    """记录正常心跳发送时间；只保存时间戳，不保存日志内容。"""
    state_path = Path(args.ok_state_file).expanduser()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = read_ok_heartbeat_state(state_path)
    state[ok_heartbeat_state_key(args)] = time.time() if now is None else now
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def build_incident_event(output: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """把日志巡检结果转换成通用 Incident Router 事件。"""
    return {
        "project": args.project,
        "source": "logcenter.biz-log",
        "service": args.eng_name,
        "env": args.env,
        "severity": "error",
        "windowMinutes": args.minutes,
        "summary": output.get("summary", {}),
    }


def write_incident_event(output: dict[str, Any], args: argparse.Namespace) -> None:
    """按需写出统一事件 JSON；事件只包含脱敏后的巡检摘要。"""
    if not args.event_output:
        return
    event_path = Path(args.event_output).expanduser()
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path.write_text(
        json.dumps(build_incident_event(output, args), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    event_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def build_lark_send_command(
    lark_cli: str,
    text: str,
    user_id: str | None,
    chat_id: str | None,
    as_identity: str,
) -> list[str]:
    """生成 lark-cli 发消息命令，确保接收人唯一且不把消息通过 shell 拼接。"""
    if bool(user_id) == bool(chat_id):
        raise RuntimeError("必须指定飞书接收人：--feishu-user-id 或 --feishu-chat-id 二选一")
    command = shlex.split(lark_cli)
    if not command:
        raise RuntimeError("lark-cli 命令不能为空")
    command.extend(["im", "+messages-send", "--as", as_identity])
    if user_id:
        command.extend(["--user-id", user_id])
    if chat_id:
        command.extend(["--chat-id", chat_id])
    command.extend(["--text", text])
    return command


def resolve_lark_cli(lark_cli: str) -> str:
    """在未全局安装 lark-cli 时自动降级到 npx 调用。"""
    if lark_cli.strip() != "lark-cli":
        return lark_cli
    if shutil.which("lark-cli"):
        return lark_cli
    if shutil.which("npx"):
        logging.info("未找到全局 lark-cli，自动使用 npx @larksuite/cli@latest。")
        return "npx @larksuite/cli@latest"
    return lark_cli


def extract_lark_open_id(payload: Any, user_name: str) -> str | None:
    """从 lark-cli contact +search-user 的 JSON 输出中选择最匹配的 open_id。"""
    if not isinstance(payload, dict):
        return None
    users = payload.get("users")
    if not isinstance(users, list):
        data = payload.get("data")
        users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(users, list):
        return None

    candidates = [item for item in users if isinstance(item, dict)]
    for user in candidates:
        names = [
            user.get("name"),
            user.get("localized_name"),
            user.get("en_name"),
            user.get("nickname"),
        ]
        if user_name in {str(name) for name in names if name}:
            return str(user.get("open_id") or user.get("user_id") or "")
    if len(candidates) == 1:
        return str(candidates[0].get("open_id") or candidates[0].get("user_id") or "")
    return None


def resolve_feishu_user_id(args: argparse.Namespace) -> str | None:
    """解析飞书用户 open_id，优先用显式配置，其次用姓名搜索。"""
    explicit_user_id = args.feishu_user_id or os.environ.get("TAISHAN_FEISHU_USER_ID")
    if explicit_user_id:
        return explicit_user_id
    if args.feishu_chat_id or os.environ.get("TAISHAN_FEISHU_CHAT_ID"):
        return None

    user_name = args.feishu_user_name or os.environ.get("TAISHAN_FEISHU_USER_NAME") or DEFAULT_FEISHU_USER_NAME
    search_command = shlex.split(resolve_lark_cli(args.lark_cli))
    if not search_command:
        raise RuntimeError("lark-cli 命令不能为空")
    search_command.extend([
        "contact",
        "+search-user",
        "--as",
        "user",
        "--query",
        user_name,
        "--page-size",
        "5",
        "--format",
        "json",
    ])
    logging.info("开始通过飞书通讯录查找接收人，name=%s。", user_name)
    result = subprocess.run(search_command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "飞书接收人查找失败，请先配置 lark-cli 登录态，或设置 TAISHAN_FEISHU_USER_ID。"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("飞书接收人查找返回不是 JSON，请检查 lark-cli 版本或认证状态。") from exc
    open_id = extract_lark_open_id(payload, user_name)
    if not open_id:
        raise RuntimeError(f"未能唯一匹配飞书接收人：{user_name}，请改用 --feishu-user-id。")
    return open_id


def send_feishu_text(args: argparse.Namespace, text: str) -> dict[str, Any]:
    """调用 lark-cli 发送飞书消息，输出只保留执行状态，不泄露凭据。"""
    user_id = resolve_feishu_user_id(args)
    chat_id = args.feishu_chat_id or os.environ.get("TAISHAN_FEISHU_CHAT_ID")
    command = build_lark_send_command(resolve_lark_cli(args.lark_cli), text, user_id, chat_id, args.feishu_as)
    if args.dry_run:
        return {"sent": False, "dryRun": True, "command": redact(command)}

    logging.info("开始发送飞书日志告警，recipientType=%s。", "chat" if chat_id else "user")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"飞书消息发送失败，exitCode={result.returncode}，error={stderr[:300]}")
    return {"sent": True, "dryRun": False, "recipientType": "chat" if chat_id else "user"}


def resolve_app_from_response(payload: Any) -> dict[str, Any]:
    """兼容常见响应包装：data、result、record 或直接返回对象。"""
    current = payload
    for key in ("data", "result", "record"):
        if isinstance(current, dict) and isinstance(current.get(key), dict):
            current = current[key]
    if not isinstance(current, dict):
        raise RuntimeError("接口响应中没有找到应用对象。")
    return parse_nested_json_fields(current)


def command_auth(args: argparse.Namespace) -> None:
    if args.auth_command == "set-cookie":
        cookie = args.value
        if not cookie:
            cookie = getpass.getpass("请粘贴完整 Cookie Header 值，输入时不会回显：")
        path = save_cookie(cookie)
        print(json.dumps({"ok": True, "cookieFile": str(path)}, ensure_ascii=False, indent=2))
    elif args.auth_command == "status":
        path = cookie_file()
        print(
            json.dumps(
                {
                    "envCookiePresent": bool(os.environ.get("TAISHAN_COOKIE")),
                    "cookieFile": str(path),
                    "cookieFilePresent": path.exists(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.auth_command == "refresh-cookie":
        path = refresh_cookie_from_chrome(args)
        print(
            json.dumps(
                {
                    "ok": True,
                    "cookieFile": str(path),
                    "source": args.browser,
                    "cookieNames": split_multi_values(args.cookie_name),
                    "validated": args.validate,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        raise SystemExit("未知 auth 命令")


def command_summarize_url(args: argparse.Namespace) -> None:
    parsed = parse_taishan_url(args.url)
    app = parsed.get("app")
    output = {
        "route": parsed["route"],
        "summary": app_summary(app) if isinstance(app, dict) else None,
        "app": app if args.full else None,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_fetch_app(args: argparse.Namespace) -> None:
    template = args.url_template or os.environ.get("TAISHAN_APP_DETAIL_URL_TEMPLATE", "")
    if not template:
        raise SystemExit(
            "缺少应用详情接口模板。请设置 TAISHAN_APP_DETAIL_URL_TEMPLATE，例如包含 {id} 的 URL。"
        )
    url = template.format(id=urllib.parse.quote(str(args.id)))
    cookie = load_cookie()
    logging.info("开始请求泰山应用详情接口，appId=%s。", args.id)
    payload = fetch_json(url, cookie)
    app = redact(resolve_app_from_response(payload))
    output = {"summary": app_summary(app), "app": app if args.full else None}
    print(json.dumps(output, ensure_ascii=False, indent=2))


def app_context_from_args(args: argparse.Namespace) -> dict[str, Any]:
    app: dict[str, Any] | None = None
    if getattr(args, "app_url", None):
        parsed = parse_taishan_url(args.app_url)
        parsed_app = parsed.get("app")
        if isinstance(parsed_app, dict):
            app = parsed_app
    return build_app_context(app, getattr(args, "id", None), getattr(args, "eng_name", None))


def command_capabilities(args: argparse.Namespace) -> None:
    print(json.dumps({"capabilities": list_capabilities()}, ensure_ascii=False, indent=2))


def command_capability_url(args: argparse.Namespace) -> None:
    capability = resolve_capability(args.capability)
    app = app_context_from_args(args)
    params = parse_key_value(args.param)
    url = build_capability_url(capability, app, params, args.template or "")
    # URL 可能包含查询条件，但不应该包含 Cookie；仍统一脱敏后输出。
    print(
        json.dumps(
            {
                "capability": capability.title,
                "key": capability.key,
                "url": redact(url),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def command_capability_fetch(args: argparse.Namespace) -> None:
    capability = resolve_capability(args.capability)
    app = app_context_from_args(args)
    params = parse_key_value(args.param)
    url = build_capability_url(capability, app, params, args.template or "")
    cookie = load_cookie()
    logging.info("开始请求泰山能力接口：%s。", capability.title)
    payload = redact(fetch_json(url, cookie))
    print(
        json.dumps(
            {
                "capability": capability.title,
                "key": capability.key,
                "data": payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def command_sql_dbs(args: argparse.Namespace) -> None:
    """查询应用可选数据库。"""
    cookie = load_cookie()
    params = {"appId": require_positive_int(args.id, "--app-id")}
    url = build_url_with_params(SQL_DBS_URL, params)
    output = {
        "request": {
            "method": "GET",
            "url": url,
            "headers": {"Cookie": "[REDACTED]"},
            "queryParams": params,
        }
    }
    response = request_json(url, cookie, method="GET")
    ensure_taishan_success(response)
    output["summary"] = {"databases": redact(unwrap_taishan_data(response))}
    if args.full:
        output["response"] = redact(response)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_sql_query_apply(args: argparse.Namespace) -> None:
    """发起 SQL 查询权限申请。"""
    body = build_sql_query_apply_body(args)
    output = {
        "request": {
            "method": "POST",
            "url": SQL_QUERY_APPROVE_CREATE_URL,
            "headers": {"Cookie": "[REDACTED]", "Content-Type": "application/json;charset=UTF-8"},
            "body": redact(body),
        }
    }
    if args.dry_run:
        output["dryRun"] = True
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    cookie = load_cookie()
    response = request_json(SQL_QUERY_APPROVE_CREATE_URL, cookie, method="POST", body=body)
    ensure_taishan_success(response)
    output["summary"] = {"created": True, "data": redact(unwrap_taishan_data(response))}
    if args.full:
        output["response"] = redact(response)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_sql_query_apply_list(args: argparse.Namespace) -> None:
    """查询 SQL 查询权限申请列表，用于确认审批是否通过。"""
    params = build_sql_query_apply_list_params(args)
    url = build_url_with_params(SQL_QUERY_APPROVE_LIST_URL, params)
    output = {
        "request": {
            "method": "GET",
            "url": url,
            "headers": {"Cookie": "[REDACTED]"},
            "queryParams": params,
        }
    }
    cookie = load_cookie()
    response = request_json(url, cookie, method="GET")
    ensure_taishan_success(response)
    output["summary"] = summarize_item_list_response(response)
    if args.full:
        output["response"] = redact(response)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_sql_permission_ensure(args: argparse.Namespace) -> None:
    """先检查是否已有有效 SQL 查询权限；没有时提交申请。"""
    list_args = argparse.Namespace(
        id=args.id,
        approve_system_id="",
        address=args.address,
        db_name=args.db_name,
        status="",
        create_user_name="",
        approve_user_name="",
        page=1,
        limit=args.limit,
    )
    list_params = build_sql_query_apply_list_params(list_args)
    list_url = build_url_with_params(SQL_QUERY_APPROVE_LIST_URL, list_params)
    output: dict[str, Any] = {
        "permissionCheck": {
            "method": "GET",
            "url": list_url,
            "headers": {"Cookie": "[REDACTED]"},
            "queryParams": list_params,
        }
    }
    cookie = load_cookie()
    list_response = request_json(list_url, cookie, method="GET")
    ensure_taishan_success(list_response)
    active = find_active_sql_permission(
        list_response,
        db_name=args.db_name,
        address=args.address,
    )
    if active:
        output["summary"] = {
            "hasPermission": True,
            "action": "skip_apply",
            "permission": redact(active),
        }
        if args.full:
            output["permissionCheckResponse"] = redact(list_response)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    output["summary"] = {
        "hasPermission": False,
        "action": "apply_required" if args.no_apply else "apply",
        "existing": summarize_item_list_response(list_response),
    }
    if args.no_apply:
        if args.full:
            output["permissionCheckResponse"] = redact(list_response)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    apply_args = argparse.Namespace(
        id=args.id,
        db_index=args.db_index,
        apply_hours=args.apply_hours,
        remark=args.remark,
    )
    apply_body = build_sql_query_apply_body(apply_args)
    output["permissionApply"] = {
        "method": "POST",
        "url": SQL_QUERY_APPROVE_CREATE_URL,
        "headers": {"Cookie": "[REDACTED]", "Content-Type": "application/json;charset=UTF-8"},
        "body": redact(apply_body),
    }
    if args.dry_run:
        output["dryRun"] = True
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    apply_response = request_json(SQL_QUERY_APPROVE_CREATE_URL, cookie, method="POST", body=apply_body)
    ensure_taishan_success(apply_response)
    output["summary"]["applied"] = True
    output["summary"]["applyData"] = redact(unwrap_taishan_data(apply_response))
    if args.full:
        output["permissionCheckResponse"] = redact(list_response)
        output["permissionApplyResponse"] = redact(apply_response)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_sql_init(args: argparse.Namespace) -> None:
    """初始化受控 SQL 查询会话。"""
    body = {
        "appId": require_positive_int(args.id, "--app-id"),
        "index": require_positive_int(args.db_index, "--db-index"),
    }
    output = {
        "request": {
            "method": "POST",
            "url": SQL_QUERY_INIT_URL,
            "headers": {"Cookie": "[REDACTED]", "Content-Type": "application/json;charset=UTF-8"},
            "body": body,
        }
    }
    if args.dry_run:
        output["dryRun"] = True
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    cookie = load_cookie()
    response = request_json(SQL_QUERY_INIT_URL, cookie, method="POST", body=body)
    ensure_taishan_success(response)
    data = unwrap_taishan_data(response)
    output["summary"] = {"session": redact(data)}
    if isinstance(data, dict) and data.get("uuid"):
        output["summary"]["uuid"] = data.get("uuid")
    if args.full:
        output["response"] = redact(response)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_sql_query(args: argparse.Namespace) -> None:
    """执行 Taishan 受控只读 SQL 查询。"""
    raw_sql = args.sql
    if args.sql_file:
        raw_sql = Path(args.sql_file).expanduser().read_text(encoding="utf-8")
    prepared_sql = prepare_readonly_sql(raw_sql, args.max_rows, auto_limit=not args.no_auto_limit)
    body = {"uuid": args.uuid, "sql": prepared_sql}
    output = {
        "request": {
            "method": "POST",
            "url": SQL_QUERY_URL,
            "headers": {"Cookie": "[REDACTED]", "Content-Type": "application/json;charset=UTF-8"},
            "body": {"uuid": args.uuid, "sql": redact_sql_literals(prepared_sql)},
        }
    }
    if args.dry_run:
        output["dryRun"] = True
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    cookie = load_cookie()
    response = request_json(SQL_QUERY_URL, cookie, method="POST", body=body)
    ensure_taishan_success(response)
    output["summary"] = summarize_sql_query_response(response, args.max_rows)
    if args.full:
        output["response"] = redact(response)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_sql_query_result(args: argparse.Namespace) -> None:
    """获取受控 SQL 异步查询结果。"""
    body = {"uuid": args.uuid, **parse_key_value(args.param)}
    output = {
        "request": {
            "method": "POST",
            "url": SQL_QUERY_RESULT_URL,
            "headers": {"Cookie": "[REDACTED]", "Content-Type": "application/json;charset=UTF-8"},
            "body": redact(body),
        }
    }
    cookie = load_cookie()
    response = request_json(SQL_QUERY_RESULT_URL, cookie, method="POST", body=body)
    ensure_taishan_success(response)
    output["summary"] = summarize_sql_query_response(response, args.max_rows)
    if args.full:
        output["response"] = redact(response)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_sql_close(args: argparse.Namespace) -> None:
    """关闭受控 SQL 查询会话。"""
    params = {"uuid": args.uuid}
    url = build_url_with_params(SQL_QUERY_CLOSE_URL, params)
    output = {
        "request": {
            "method": "GET",
            "url": url,
            "headers": {"Cookie": "[REDACTED]"},
            "queryParams": params,
        }
    }
    if args.dry_run:
        output["dryRun"] = True
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    cookie = load_cookie()
    response = request_json(url, cookie, method="GET")
    ensure_taishan_success(response)
    output["summary"] = {"closed": True, "data": redact(unwrap_taishan_data(response))}
    if args.full:
        output["response"] = redact(response)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_biz_log_query(args: argparse.Namespace) -> None:
    """通过纯 HTTP 查询业务日志，并输出脱敏后的请求和响应。"""
    output = execute_biz_log_query(args)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def execute_biz_log_query(args: argparse.Namespace) -> dict[str, Any]:
    """执行业务日志查询并返回脱敏后的调用结果，供 CLI 和巡检任务复用。"""
    if args.minutes <= 0:
        raise RuntimeError("--minutes 必须大于 0")
    if args.limit <= 0:
        raise RuntimeError("--limit 必须大于 0")

    cookie = load_cookie()
    query_params = build_biz_log_query_range_params(args)
    url = build_biz_log_query_range_url(query_params)
    logging.info(
        "开始请求泰山业务日志接口，appId=%s，engName=%s，env=%s。",
        args.id,
        args.eng_name,
        args.env,
    )
    output = {
        "request": {
            "method": "GET",
            "url": url,
            "headers": {
                "Accept": "application/json, text/plain, */*",
                "Cookie": "[REDACTED]",
                "Origin": "https://taishan.wanmeixiangsu.cn",
                "Referer": "https://taishan.wanmeixiangsu.cn/",
            },
            "queryParams": query_params,
        },
    }
    try:
        response = request_json(url, cookie, method="GET")
        output["summary"] = summarize_biz_log_response(response)
        if args.full:
            output["response"] = redact(response)
    except Exception as exc:
        # 登录态失效时也保留本次 HTTP 观测结果，便于后续确认 Cookie 或 SSO 换票流程。
        output["response"] = {
            "ok": False,
            "error": str(exc),
        }
        raise
    return output


def command_biz_error_monitor(args: argparse.Namespace) -> None:
    """查询最近窗口内的业务 error 日志，并按配置发送告警或健康心跳。"""
    output = execute_biz_log_query(args)
    summary = output.get("summary", {})
    monitor_result: dict[str, Any] = {
        "request": output.get("request"),
        "summary": summary,
        "notification": {"sent": False, "reason": "no_error_logs"},
    }
    if isinstance(summary, dict) and should_send_biz_error_alert(summary):
        message = format_biz_error_alert(summary, args)
        monitor_result["notification"] = send_feishu_text(args, message)
    elif args.send_ok:
        if should_send_ok_heartbeat(args):
            message = format_biz_error_ok_message(summary if isinstance(summary, dict) else {}, args)
            monitor_result["notification"] = send_feishu_text(args, message)
            if monitor_result["notification"].get("sent"):
                mark_ok_heartbeat_sent(args)
        else:
            monitor_result["notification"] = {"sent": False, "reason": "ok_heartbeat_throttled"}
    logging.info(
        "业务 error 日志巡检完成，engName=%s，env=%s，returned=%s。",
        args.eng_name,
        args.env,
        summary.get("returned") if isinstance(summary, dict) else None,
    )
    write_incident_event(monitor_result, args)
    print(json.dumps(monitor_result, ensure_ascii=False, indent=2))


def command_access_log_query(args: argparse.Namespace) -> None:
    """通过纯 HTTP 查询访问日志，并输出脱敏后的简洁结果。"""
    if args.minutes <= 0:
        raise RuntimeError("--minutes 必须大于 0")
    if args.limit <= 0:
        raise RuntimeError("--limit 必须大于 0")
    if bool(args.start_time) != bool(args.end_time):
        raise RuntimeError("--start-time 和 --end-time 必须同时传入")
    if not args.host and not args.query and not args.profile_id:
        raise RuntimeError("访问日志至少需要 --host、--query 或 --profile-id 之一")

    cookie = load_cookie()
    request_body = build_access_log_request(args)
    url = build_access_log_query_url()
    logging.info(
        "开始请求泰山访问日志接口，appName=%s，env=%s。",
        args.eng_name,
        args.env,
    )
    output = {
        "request": {
            "method": "POST",
            "url": url,
            "headers": {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Cookie": "[REDACTED]",
                "Origin": "https://taishan.wanmeixiangsu.cn",
                "Referer": "https://taishan.wanmeixiangsu.cn/",
            },
            "body": request_body,
        },
    }
    try:
        response = request_form_json(url, cookie, request_body)
        output["summary"] = summarize_access_log_response(response)
        logs = output["summary"].get("logs")
        if isinstance(logs, list) and len(logs) > args.limit:
            output["summary"]["logs"] = logs[: args.limit]
            output["summary"]["returned"] = args.limit
        if args.full:
            output["response"] = redact(response)
    except Exception as exc:
        output["response"] = {
            "ok": False,
            "error": str(exc),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        raise
    print(json.dumps(output, ensure_ascii=False, indent=2))


def command_capability_page(args: argparse.Namespace) -> None:
    capability = resolve_capability(args.capability)
    route = args.route or os.environ.get(
        f"TAISHAN_{capability.key.upper().replace('-', '_')}_ROUTE",
        capability.default_route or "",
    )
    if not route:
        raise RuntimeError(f"{capability.title} 暂未确认页面路由，请通过 --route 指定。")
    query = {"id": args.id}
    if args.eng_name:
        query["engName"] = args.eng_name
    query.update(parse_key_value(args.param))
    url = "https://taishan.wanmeixiangsu.cn/#" + route + "?" + urllib.parse.urlencode(query)
    print(
        json.dumps(
            {
                "capability": capability.title,
                "key": capability.key,
                "url": url,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安全查询和解析泰山应用信息")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志，不包含敏感值")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth", help="管理泰山 Cookie")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)
    set_cookie = auth_subparsers.add_parser("set-cookie", help="保存完整 Cookie Header")
    set_cookie.add_argument("--value", help="完整 Cookie Header。省略时用安全输入提示。")
    auth_subparsers.add_parser("status", help="查看 Cookie 配置状态")
    refresh_cookie = auth_subparsers.add_parser(
        "refresh-cookie",
        help="打开 Chrome 等待扫码登录，并自动保存泰山 Cookie",
    )
    refresh_cookie.add_argument(
        "--browser",
        choices=("chrome",),
        default="chrome",
        help="用于扫码登录和读取 Cookie 的浏览器，默认 chrome",
    )
    refresh_cookie.add_argument(
        "--profile-dir",
        default=str(DEFAULT_CHROME_PROFILE_DIR),
        help="Chrome profile 目录，默认读取当前用户 Default profile",
    )
    refresh_cookie.add_argument(
        "--url",
        default=DEFAULT_TAISHAN_LOGIN_URL,
        help="需要打开的泰山登录页 URL",
    )
    refresh_cookie.add_argument(
        "--cookie-name",
        action="append",
        default=["__CLIENT_USER_TOKEN__"],
        help="允许保存的 Cookie 名称，支持逗号分隔或重复传入",
    )
    refresh_cookie.add_argument(
        "--cookie-domain",
        action="append",
        default=["wanmeixiangsu.cn"],
        help="允许读取的 Cookie 域名片段，支持逗号分隔或重复传入",
    )
    refresh_cookie.add_argument("--timeout", type=int, default=180, help="等待扫码登录的最长秒数")
    refresh_cookie.add_argument("--interval", type=float, default=3, help="轮询 Chrome Cookie 的间隔秒数")
    refresh_cookie.add_argument("--no-open", action="store_true", help="不自动打开 Chrome，仅从现有 Cookie 中读取")
    refresh_cookie.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        help="只保存 Cookie，不请求 logcenter 校验",
    )
    refresh_cookie.set_defaults(validate=True)
    auth_parser.set_defaults(func=command_auth)

    summarize = subparsers.add_parser("summarize-url", help="从登录后泰山 URL 解析应用信息")
    summarize.add_argument("--url", required=True, help="登录后泰山 URL")
    summarize.add_argument("--full", action="store_true", help="输出脱敏后的完整 app 对象")
    summarize.set_defaults(func=command_summarize_url)

    fetch_app = subparsers.add_parser("fetch-app", help="通过已知接口模板获取应用信息")
    fetch_app.add_argument("--id", required=True, help="泰山应用 ID")
    fetch_app.add_argument("--url-template", help="应用详情接口模板，使用 {id} 作为占位符")
    fetch_app.add_argument("--full", action="store_true", help="输出脱敏后的完整 app 对象")
    fetch_app.set_defaults(func=command_fetch_app)

    capabilities = subparsers.add_parser("capabilities", help="列出已实现的泰山能力")
    capabilities.set_defaults(func=command_capabilities)

    capability_url = subparsers.add_parser("capability-url", help="生成指定能力的接口 URL")
    capability_url.add_argument("--capability", required=True, help="能力 key、中文名或别名")
    capability_url.add_argument("--id", help="泰山应用 ID")
    capability_url.add_argument("--eng-name", help="应用英文名")
    capability_url.add_argument("--app-url", help="登录后的泰山应用 URL，可从中解析 app 对象")
    capability_url.add_argument("--template", help="接口 URL 模板，优先级高于环境变量")
    capability_url.add_argument(
        "--param",
        action="append",
        help="额外模板参数，格式 key=value，可重复传入",
    )
    capability_url.set_defaults(func=command_capability_url)

    capability_fetch = subparsers.add_parser("capability-fetch", help="调用指定能力接口")
    capability_fetch.add_argument("--capability", required=True, help="能力 key、中文名或别名")
    capability_fetch.add_argument("--id", help="泰山应用 ID")
    capability_fetch.add_argument("--eng-name", help="应用英文名")
    capability_fetch.add_argument("--app-url", help="登录后的泰山应用 URL，可从中解析 app 对象")
    capability_fetch.add_argument("--template", help="接口 URL 模板，优先级高于环境变量")
    capability_fetch.add_argument(
        "--param",
        action="append",
        help="额外模板参数，格式 key=value，可重复传入",
    )
    capability_fetch.set_defaults(func=command_capability_fetch)

    sql_dbs = subparsers.add_parser("sql-dbs", help="查询应用可选数据库")
    sql_dbs.add_argument(
        "--id",
        "--app-id",
        dest="id",
        default=DEFAULT_APP_ID,
        help=f"泰山应用 ID，默认 {DEFAULT_APP_ID}",
    )
    sql_dbs.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    sql_dbs.set_defaults(func=command_sql_dbs)

    sql_query_apply = subparsers.add_parser("sql-query-apply", help="发起 SQL 查询权限申请")
    sql_query_apply.add_argument(
        "--id",
        "--app-id",
        dest="id",
        default=DEFAULT_APP_ID,
        help=f"泰山应用 ID，默认 {DEFAULT_APP_ID}",
    )
    sql_query_apply.add_argument(
        "--db-index",
        "--index",
        dest="db_index",
        required=True,
        help="泰山数据库索引 index，来自 sql-dbs 或项目映射 taishanSql.dbIndex",
    )
    sql_query_apply.add_argument("--apply-hours", type=int, default=2, help="申请时长，默认 2 小时，最长 12 小时")
    sql_query_apply.add_argument(
        "--remark",
        default="应用问题排查：受控只读 SQL 查询",
        help="申请原因，会写入泰山申请记录",
    )
    sql_query_apply.add_argument("--dry-run", action="store_true", help="只输出请求，不真正提交申请")
    sql_query_apply.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    sql_query_apply.set_defaults(func=command_sql_query_apply)

    sql_query_apply_list = subparsers.add_parser(
        "sql-query-apply-list",
        help="查询 SQL 查询权限申请列表，用于查看申请是否通过",
    )
    sql_query_apply_list.add_argument(
        "--id",
        "--app-id",
        dest="id",
        default=DEFAULT_APP_ID,
        help=f"泰山应用 ID，默认 {DEFAULT_APP_ID}",
    )
    sql_query_apply_list.add_argument("--approve-system-id", help="审批系统 ID")
    sql_query_apply_list.add_argument("--address", help="数据库地址")
    sql_query_apply_list.add_argument("--db-name", help="数据库名")
    sql_query_apply_list.add_argument("--status", help="审批状态")
    sql_query_apply_list.add_argument("--create-user-name", help="申请人")
    sql_query_apply_list.add_argument("--approve-user-name", help="审批人")
    sql_query_apply_list.add_argument("--page", type=int, default=1, help="页码")
    sql_query_apply_list.add_argument("--limit", type=int, default=20, help="每页条数")
    sql_query_apply_list.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    sql_query_apply_list.set_defaults(func=command_sql_query_apply_list)

    sql_permission_ensure = subparsers.add_parser(
        "sql-permission-ensure",
        help="检查 SQL 查询权限；已有有效权限则跳过申请，否则提交申请",
    )
    sql_permission_ensure.add_argument(
        "--id",
        "--app-id",
        dest="id",
        default=DEFAULT_APP_ID,
        help=f"泰山应用 ID，默认 {DEFAULT_APP_ID}",
    )
    sql_permission_ensure.add_argument(
        "--db-index",
        "--index",
        dest="db_index",
        required=True,
        help="泰山数据库索引 index，来自 sql-dbs 或项目映射 taishanSql.dbIndex",
    )
    sql_permission_ensure.add_argument("--db-name", help="数据库名，用于匹配已有权限")
    sql_permission_ensure.add_argument("--address", help="数据库地址，用于匹配已有权限")
    sql_permission_ensure.add_argument("--apply-hours", type=int, default=2, help="申请时长，默认 2 小时，最长 12 小时")
    sql_permission_ensure.add_argument(
        "--remark",
        default="应用问题排查：受控只读 SQL 查询",
        help="申请原因，会写入泰山申请记录",
    )
    sql_permission_ensure.add_argument("--limit", type=int, default=20, help="检查最近多少条申请记录")
    sql_permission_ensure.add_argument("--no-apply", action="store_true", help="只检查权限，不自动提交申请")
    sql_permission_ensure.add_argument("--dry-run", action="store_true", help="已有权限时输出结果；无权限时只展示申请请求")
    sql_permission_ensure.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    sql_permission_ensure.set_defaults(func=command_sql_permission_ensure)

    sql_init = subparsers.add_parser("sql-init", help="初始化受控 SQL 查询会话")
    sql_init.add_argument(
        "--id",
        "--app-id",
        dest="id",
        default=DEFAULT_APP_ID,
        help=f"泰山应用 ID，默认 {DEFAULT_APP_ID}",
    )
    sql_init.add_argument(
        "--db-index",
        "--index",
        dest="db_index",
        required=True,
        help="泰山数据库索引 index，来自 sql-dbs 或项目映射 taishanSql.dbIndex",
    )
    sql_init.add_argument("--dry-run", action="store_true", help="只输出请求，不真正初始化")
    sql_init.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    sql_init.set_defaults(func=command_sql_init)

    sql_query = subparsers.add_parser("sql-query", help="执行 Taishan 受控只读 SQL 查询")
    sql_query.add_argument("--uuid", required=True, help="sql-init 返回的查询会话 uuid")
    sql_input = sql_query.add_mutually_exclusive_group(required=True)
    sql_input.add_argument("--sql", help="只读 SQL；SELECT 会自动补 LIMIT")
    sql_input.add_argument("--sql-file", help="从文件读取只读 SQL")
    sql_query.add_argument("--max-rows", type=int, default=100, help="最大返回行数，默认 100")
    sql_query.add_argument(
        "--no-auto-limit",
        action="store_true",
        help="不自动给 SELECT 追加 LIMIT；缺失 LIMIT 时会报错",
    )
    sql_query.add_argument("--dry-run", action="store_true", help="只做安全检查并输出请求，不真正查询")
    sql_query.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    sql_query.set_defaults(func=command_sql_query)

    sql_query_result = subparsers.add_parser("sql-query-result", help="获取受控 SQL 异步查询结果")
    sql_query_result.add_argument("--uuid", required=True, help="查询会话 uuid")
    sql_query_result.add_argument("--max-rows", type=int, default=100, help="最大展示行数，默认 100")
    sql_query_result.add_argument(
        "--param",
        action="append",
        help="额外结果查询参数，格式 key=value，可重复传入",
    )
    sql_query_result.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    sql_query_result.set_defaults(func=command_sql_query_result)

    sql_close = subparsers.add_parser("sql-close", help="关闭受控 SQL 查询会话")
    sql_close.add_argument("--uuid", required=True, help="查询会话 uuid")
    sql_close.add_argument("--dry-run", action="store_true", help="只输出请求，不真正关闭")
    sql_close.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    sql_close.set_defaults(func=command_sql_close)

    biz_log_query = subparsers.add_parser("biz-log-query", help="通过纯 HTTP 查询业务日志")
    biz_log_query.add_argument(
        "--id",
        "--app-id",
        dest="id",
        default=DEFAULT_APP_ID,
        help=f"泰山应用 ID，默认 {DEFAULT_APP_ID}",
    )
    biz_log_query.add_argument(
        "--eng-name",
        "--service",
        dest="eng_name",
        default=DEFAULT_APP_ENG_NAME,
        help=f"服务英文名，默认 {DEFAULT_APP_ENG_NAME}",
    )
    biz_log_query.add_argument(
        "--env",
        default=DEFAULT_APP_ENV,
        help=f"环境，例如 production 或 test，默认 {DEFAULT_APP_ENV}",
    )
    biz_log_query.add_argument("--minutes", type=int, default=60, help="向前查询的分钟数")
    biz_log_query.add_argument("--limit", type=int, default=5, help="返回日志条数")
    biz_log_query.add_argument(
        "--keyword",
        action="append",
        help="日志内容关键字，支持逗号分隔或重复传入",
    )
    biz_log_query.add_argument(
        "--level",
        action="append",
        help="日志级别：server、warning、error；也兼容 INFO、WARN、ERROR。支持逗号分隔或重复传入",
    )
    biz_log_query.add_argument(
        "--log-file-name",
        action="append",
        help="日志文件名，支持逗号分隔或重复传入",
    )
    biz_log_query.add_argument(
        "--pod-id",
        action="append",
        help="实例 ID，支持逗号分隔或重复传入",
    )
    biz_log_query.add_argument("--full", action="store_true", help="输出完整 HTTP 响应和 stats")
    biz_log_query.set_defaults(func=command_biz_log_query)

    biz_error_monitor = subparsers.add_parser(
        "biz-error-monitor",
        help="查询最近 5 分钟业务 error 日志，有结果时发送飞书告警",
    )
    biz_error_monitor.add_argument(
        "--id",
        "--app-id",
        dest="id",
        default=DEFAULT_APP_ID,
        help=f"泰山应用 ID，默认 {DEFAULT_APP_ID}",
    )
    biz_error_monitor.add_argument(
        "--eng-name",
        "--service",
        dest="eng_name",
        default=DEFAULT_APP_ENG_NAME,
        help=f"服务英文名，默认 {DEFAULT_APP_ENG_NAME}",
    )
    biz_error_monitor.add_argument(
        "--env",
        default=DEFAULT_APP_ENV,
        help=f"环境，例如 production 或 test，默认 {DEFAULT_APP_ENV}",
    )
    biz_error_monitor.add_argument(
        "--project",
        default=DEFAULT_APP_ENG_NAME,
        help="项目注册表中的项目名，供 Incident Router Agent 使用",
    )
    biz_error_monitor.add_argument("--minutes", type=int, default=5, help="向前查询的分钟数，默认 5")
    biz_error_monitor.add_argument("--limit", type=int, default=20, help="最多展示并发送的日志条数")
    biz_error_monitor.add_argument(
        "--keyword",
        action="append",
        help="日志内容关键字，支持逗号分隔或重复传入",
    )
    biz_error_monitor.add_argument(
        "--level",
        action="append",
        default=["error"],
        help="巡检日志级别，默认 error；一般无需修改",
    )
    biz_error_monitor.add_argument(
        "--log-file-name",
        action="append",
        help="日志文件名，支持逗号分隔或重复传入",
    )
    biz_error_monitor.add_argument(
        "--pod-id",
        action="append",
        help="实例 ID，支持逗号分隔或重复传入",
    )
    biz_error_monitor.add_argument(
        "--lark-cli",
        default=os.environ.get("TAISHAN_LARK_CLI", "lark-cli"),
        help="lark-cli 命令路径，默认读取 TAISHAN_LARK_CLI 或 lark-cli",
    )
    biz_error_monitor.add_argument(
        "--feishu-user-id",
        help="飞书接收人 open_id；也可用 TAISHAN_FEISHU_USER_ID 配置",
    )
    biz_error_monitor.add_argument(
        "--feishu-chat-id",
        help="飞书群聊 chat_id；也可用 TAISHAN_FEISHU_CHAT_ID 配置",
    )
    biz_error_monitor.add_argument(
        "--feishu-user-name",
        default=os.environ.get("TAISHAN_FEISHU_USER_NAME", DEFAULT_FEISHU_USER_NAME),
        help=f"未配置 user_id 时按姓名查找，默认 {DEFAULT_FEISHU_USER_NAME}",
    )
    biz_error_monitor.add_argument(
        "--feishu-as",
        default=os.environ.get("TAISHAN_FEISHU_AS", "bot"),
        choices=("bot", "user"),
        help="飞书发送身份，默认 bot",
    )
    biz_error_monitor.add_argument(
        "--send-ok",
        action="store_true",
        help="没有 error 日志时也发送一条巡检正常消息",
    )
    biz_error_monitor.add_argument(
        "--ok-interval-minutes",
        type=int,
        default=0,
        help="正常心跳最小发送间隔；0 表示每次无 error 都发送",
    )
    biz_error_monitor.add_argument(
        "--ok-state-file",
        default=str(DEFAULT_OK_HEARTBEAT_STATE_FILE),
        help="正常心跳节流状态文件，只保存发送时间戳",
    )
    biz_error_monitor.add_argument(
        "--event-output",
        help="把巡检结果写成通用 Incident Router 事件 JSON",
    )
    biz_error_monitor.add_argument("--dry-run", action="store_true", help="只查询和生成发送命令，不实际发飞书")
    biz_error_monitor.add_argument("--full", action="store_true", help="输出完整 HTTP 响应和 stats")
    biz_error_monitor.set_defaults(func=command_biz_error_monitor)

    access_log_query = subparsers.add_parser("access-log-query", help="通过纯 HTTP 查询访问日志")
    access_log_query.add_argument(
        "--eng-name",
        "--service",
        dest="eng_name",
        default=DEFAULT_APP_ENG_NAME,
        help=f"服务英文名，默认 {DEFAULT_APP_ENG_NAME}",
    )
    access_log_query.add_argument(
        "--env",
        default=DEFAULT_APP_ENV,
        help=f"环境标签，默认 {DEFAULT_APP_ENV}；访问日志接口主要使用 appName/profileId",
    )
    access_log_query.add_argument("--host", help="请求 Host，例如 pixel-studio.ppixels.com")
    access_log_query.add_argument("--path", help="请求路径，例如 /api/open/user")
    access_log_query.add_argument("--method", help="HTTP 方法，例如 GET 或 POST")
    access_log_query.add_argument("--status", type=int, help="HTTP 状态码，例如 500")
    access_log_query.add_argument("--query", help="原始访问日志 q 查询串，优先级最高")
    access_log_query.add_argument("--profile-id", help="logcenter 数据源/环境 ID，已知时传入")
    access_log_query.add_argument("--minutes", type=int, default=60, help="向前查询的分钟数")
    access_log_query.add_argument("--lag-seconds", type=int, default=180, help="默认查询时 endTime 距离当前时间的延迟秒数")
    access_log_query.add_argument("--start-time", help="精确开始时间，格式 YYYY-MM-DD HH:mm:ss")
    access_log_query.add_argument("--end-time", help="精确结束时间，格式 YYYY-MM-DD HH:mm:ss")
    access_log_query.add_argument("--page", type=int, default=1, help="页码")
    access_log_query.add_argument("--limit", type=int, default=25, help="展示日志条数；后端请求至少按 25 条发起")
    access_log_query.add_argument("--full", action="store_true", help="输出完整 HTTP 响应")
    access_log_query.set_defaults(func=command_access_log_query)

    capability_page = subparsers.add_parser("capability-page", help="生成指定能力的泰山页面 URL")
    capability_page.add_argument("--capability", required=True, help="能力 key、中文名或别名")
    capability_page.add_argument("--id", required=True, help="泰山应用 ID")
    capability_page.add_argument("--eng-name", help="应用英文名")
    capability_page.add_argument("--route", help="页面路由，例如 taishan.H0009")
    capability_page.add_argument(
        "--param",
        action="append",
        help="额外页面参数，格式 key=value，可重复传入",
    )
    capability_page.set_defaults(func=command_capability_page)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    try:
        args.func(args)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI 需要统一转换为可读错误。
        logging.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
