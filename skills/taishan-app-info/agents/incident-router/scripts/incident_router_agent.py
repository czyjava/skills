#!/usr/bin/env python3
"""通用 Incident Router Agent。

输入统一事件 JSON，输出去重后的 incident JSON 和分析 Agent prompt。
该脚本不读取生产凭据、不执行写库 SQL，也不自动修改代码。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME_DIR = Path(
    os.environ.get("WMXS_AGENT_RUNTIME_DIR", Path.cwd() / ".agent-state")
).expanduser()
DEFAULT_CONFIG_FILE = DEFAULT_RUNTIME_DIR / "wmxs-agent" / "projects.json"
DEFAULT_INCIDENT_DIR = DEFAULT_RUNTIME_DIR / "wmxs-agent" / "incidents"
DEFAULT_STATE_FILE = DEFAULT_RUNTIME_DIR / "wmxs-agent" / "incident-router-state.json"
DEFAULT_LEDGER_FILE = DEFAULT_RUNTIME_DIR / "wmxs-agent" / "incident-ledger.json"
DEFAULT_REPORT_FILE = DEFAULT_RUNTIME_DIR / "wmxs-agent" / "reports" / "incidents.md"
DEFAULT_FIX_DIR = DEFAULT_RUNTIME_DIR / "wmxs-agent" / "fix-queue"
DEFAULT_ISSUE_DIR = DEFAULT_RUNTIME_DIR / "wmxs-agent" / "issue-queue"
DEFAULT_REPO_CONFIG = SKILL_ROOT / "configs" / "projects.example.json"
LEGACY_CONFIG_FILE = Path.home() / ".config" / "wmxs-agent" / "projects.json"
LEGACY_STATE_FILE = Path.home() / ".config" / "wmxs-agent" / "incident-router-state.json"
LEGACY_LEDGER_FILE = Path.home() / ".config" / "wmxs-agent" / "incident-ledger.json"
ACTIVE_ISSUE_STATUSES = {"queued_for_issue", "creating_issue"}
ACTIVE_FIX_STATUSES = {"queued_for_fix", "investigating", "fixing"}


SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(password|passwd|pwd|token|secret|cookie|authorization|accessKey|access_id)\s*[:=]\s*[^,\s]+"),
    re.compile(r"(?i)(phone|mobile|email|idcard|identity)\s*[:=]\s*[^,\s]+"),
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_private(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def migrate_legacy_file(target: Path, legacy: Path) -> Path:
    if target.exists() or not legacy.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return target


def load_project_registry(config_file: Path | str | None = None) -> dict[str, Any]:
    """加载项目注册表；优先用户配置，缺省用仓库示例配置。"""
    candidates = []
    if config_file:
        candidates.append(Path(config_file).expanduser())
    else:
        migrate_legacy_file(DEFAULT_CONFIG_FILE, LEGACY_CONFIG_FILE)
    candidates.extend([DEFAULT_CONFIG_FILE, DEFAULT_REPO_CONFIG])
    for path in candidates:
        if path.exists():
            data = read_json(path)
            projects = data.get("projects") if isinstance(data, dict) else None
            if isinstance(projects, dict):
                return projects
    raise RuntimeError(f"未找到项目注册表，请创建 {DEFAULT_CONFIG_FILE}")


def redact_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(lambda match: match.group(1) + "=[REDACTED]", redacted)
    return redacted


def normalize_message(message: str) -> str:
    """归一化日志正文，去掉高基数字段，保留错误语义。"""
    normalized = redact_text(message)
    normalized = re.sub(r"\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:. -]+\]", "[TIME]", normalized)
    normalized = re.sub(r"(?<=\[TIME\]\s)\[[^\]]+\]", "[THREAD]", normalized)
    normalized = re.sub(r"\[(?:http-nio|scheduler|pool|task|ForkJoinPool|Dubbo|grpc|lettuce|mysql|redis)[^\]]*\]", "[THREAD]", normalized, flags=re.I)
    normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>", normalized, flags=re.I)
    normalized = re.sub(r"\b\d{8,}\b", "<NUM>", normalized)
    normalized = re.sub(r"taskId\s*[:=]\s*[^,\s]+", "taskId=<ID>", normalized, flags=re.I)
    normalized = re.sub(r"traceId\s*[:=]\s*[^,\s]+", "traceId=<ID>", normalized, flags=re.I)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:1000]


def strip_log_prefix(message: str) -> str:
    stripped = normalize_message(message)
    stripped = re.sub(r"^\[TIME\]\s*", "", stripped)
    stripped = re.sub(r"^\[THREAD\]\s*", "", stripped)
    stripped = re.sub(r"^-\s*(?:ERROR|WARN|WARNING|INFO)\s*-\s*", "", stripped, flags=re.I)
    stripped = re.sub(r"^(?:<UUID>|[0-9a-f.]{12,})\s*:\s*", "", stripped, flags=re.I)
    stripped = re.sub(r"^-\s*-\s*", "", stripped)
    return stripped.strip()


def semantic_problem_signature(project: str, env: str, log: dict[str, Any]) -> str:
    """生成比单条日志更粗的语义签名，用于避免同一异常链路重复建 Issue。"""
    raw_message = str(log.get("message") or "")
    message = strip_log_prefix(raw_message)
    lower = message.lower()

    if (
        ("id.photo" in lower or "idphoto" in lower or "证件照" in message)
        and any(
            token in message
            for token in (
                "并行步骤无法选出主输出",
                "所有抠图通道均失败",
                "阿里云抠图异常",
                "获取图片信息失败",
                "无法读取图片内容",
                "抠图分割失败",
            )
        )
    ):
        return "|".join([project, env, "idphoto-segmentation-chain-failure"])

    if "sql injection violation" in lower and "part alway true condition" in lower:
        return "|".join([project, env, "druid-wall-filter-always-true-condition"])

    if "com.sun.xml.bind.v2.runtime.reflect.opt.injector" in lower and "null" in lower:
        return "|".join([project, env, "jaxb-injector-null"])

    if "query feishu task detail error" in lower:
        return "|".join([project, env, "feishu-task-detail-error"])

    exception_class = extract_exception_class(raw_message)
    top_stack_frame = extract_top_stack_frame(raw_message)
    if exception_class or top_stack_frame:
        return "|".join([project, env, exception_class, top_stack_frame, message])
    return "|".join([project, env, message])


def canonical_key_from_signature(signature: str) -> str:
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]


def is_noise_log(log: dict[str, Any]) -> bool:
    """过滤只用于排版的 error 日志，避免把分隔线当成 incident。"""
    message = str(log.get("message") or "").strip()
    normalized = normalize_message(message)
    if not normalized:
        return True
    without_prefix = re.sub(r"^\[TIME\]\s*(?:\[THREAD\]\s*)?(?:-\s*)?(?:ERROR|WARN|INFO)?\s*:?\s*", "", normalized, flags=re.I)
    return bool(re.fullmatch(r"[-=_*.\s]{20,}", without_prefix))


def extract_exception_class(message: str) -> str:
    match = re.search(r"([a-zA-Z_][\w$]*(?:\.[a-zA-Z_][\w$]*)*(?:Exception|Error))", message)
    return match.group(1) if match else ""


def extract_top_stack_frame(message: str) -> str:
    match = re.search(r"\bat\s+([a-zA-Z_][\w.$]+)\(([^)]*)\)", message)
    return f"{match.group(1)}({match.group(2)})" if match else ""


def fingerprint_log(project: str, env: str, log: dict[str, Any]) -> str:
    """按项目、环境、日志文件、异常类、首个栈帧和归一化消息生成稳定指纹。"""
    message = str(log.get("message") or "")
    basis = "|".join(
        [
            project,
            env,
            str(log.get("logFile") or ""),
            extract_exception_class(message),
            extract_top_stack_frame(message),
            normalize_message(message),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def extract_logs(event: dict[str, Any]) -> list[dict[str, Any]]:
    summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
    logs = summary.get("logs") if isinstance(summary.get("logs"), list) else event.get("logs")
    return [log for log in logs if isinstance(log, dict)] if isinstance(logs, list) else []


def extract_incidents(event: dict[str, Any], threshold: int = 1) -> list[dict[str, Any]]:
    project = str(event.get("project") or event.get("service") or "")
    env = str(event.get("env") or "unknown")
    source = str(event.get("source") or "unknown")
    severity = str(event.get("severity") or "").lower()
    expected_levels = {
        "error": {"error"},
        "warning": {"warning", "warn"},
        "warn": {"warning", "warn"},
    }.get(severity)
    groups: dict[str, list[dict[str, Any]]] = {}
    for log in extract_logs(event):
        log_level = str(log.get("level") or "").lower()
        if expected_levels and log_level and log_level not in expected_levels:
            continue
        if is_noise_log(log):
            continue
        fingerprint = fingerprint_log(project, env, log)
        groups.setdefault(fingerprint, []).append(log)

    incidents: list[dict[str, Any]] = []
    for fingerprint, logs in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True):
        if len(logs) < threshold:
            continue
        sample_logs = []
        for log in logs[:5]:
            sample = dict(log)
            if "message" in sample:
                sample["message"] = redact_text(sample["message"])
            sample_logs.append(sample)
        incidents.append(
            {
                "project": project,
                "env": env,
                "source": source,
                "familyKey": build_family_key(project, env, logs[0]),
                "fingerprint": fingerprint,
                "count": len(logs),
                "firstSeen": logs[-1].get("time"),
                "lastSeen": logs[0].get("time"),
                "sampleLogs": sample_logs,
            }
        )
    return incidents


def build_family_key(project: str, env: str, log: dict[str, Any]) -> str:
    """生成问题族 key，用于长期台账；比单次日志指纹更关注问题本身。"""
    return canonical_key_from_signature(semantic_problem_signature(project, env, log))


def family_semantic_signature(family: dict[str, Any]) -> str:
    logs = family.get("lastSampleLogs") if isinstance(family.get("lastSampleLogs"), list) else []
    sample = logs[0] if logs and isinstance(logs[0], dict) else {}
    message = str(sample.get("message") or "").strip()
    if not message or message == "[REDACTED]":
        return ""
    project = str(family.get("project") or "")
    env = str(family.get("env") or "unknown")
    return semantic_problem_signature(project, env, sample)


def issue_number(issue_url: str) -> int:
    match = re.search(r"/issues/(\d+)(?:$|[/?#])", issue_url or "")
    return int(match.group(1)) if match else 10**9


def dedupe_existing_families(families: dict[str, Any], project_name: str | None = None) -> int:
    """把历史台账里语义相同的问题族合并，避免继续创建重复 Issue/修复线程。"""
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for family_key, family in families.items():
        if project_name and family.get("project") != project_name:
            continue
        if family.get("status") == "duplicate":
            continue
        signature = family_semantic_signature(family)
        if not signature:
            continue
        family["canonicalKey"] = canonical_key_from_signature(signature)
        groups.setdefault(signature, []).append((str(family_key), family))

    changed = 0
    for items in groups.values():
        if len(items) < 2:
            continue
        canonical_key, canonical = sorted(
            items,
            key=lambda item: (
                0 if item[1].get("issueUrl") else 1,
                issue_number(str(item[1].get("issueUrl") or "")),
                str(item[1].get("firstSeen") or ""),
                item[0],
            ),
        )[0]
        canonical.setdefault("duplicateFamilies", [])
        canonical_duplicates = canonical["duplicateFamilies"]
        for family_key, family in items:
            if family_key == canonical_key:
                continue
            if family.get("duplicateOf") == canonical_key and family.get("status") == "duplicate":
                continue
            if family_key not in canonical_duplicates:
                canonical_duplicates.append(family_key)
            family["statusBeforeDuplicate"] = family.get("status", "new")
            family["status"] = "duplicate"
            family["duplicateOf"] = canonical_key
            family["issueUrlBeforeDuplicate"] = family.get("issueUrl", "")
            family["issueUrl"] = canonical.get("issueUrl", family.get("issueUrl", ""))
            changed += 1
    return changed


def read_deduped_ledger(ledger_path: Path, project_name: str | None = None) -> dict[str, Any]:
    ledger = read_ledger(ledger_path)
    if dedupe_existing_families(ledger["families"], project_name):
        write_json_private(ledger_path, ledger)
    return ledger


def family_coverage_terms(family: dict[str, Any]) -> list[str]:
    signature = family_semantic_signature(family)
    if not signature:
        return []
    if "idphoto-segmentation-chain-failure" in signature:
        return ["证件照", "抠图"]
    if "druid-wall-filter-always-true-condition" in signature:
        return ["druid", "恒真"]
    if "jaxb-injector-null" in signature:
        return ["jaxb", "injector"]
    if "feishu-task-detail-error" in signature:
        return ["飞书", "任务详情"]
    sample_logs = family.get("lastSampleLogs") if isinstance(family.get("lastSampleLogs"), list) else []
    message = str(sample_logs[0].get("message") or "") if sample_logs and isinstance(sample_logs[0], dict) else ""
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_][A-Za-z0-9_]{3,}", strip_log_prefix(message))
    return [token.lower() for token in tokens[:4]]


def issue_text(issue: dict[str, Any]) -> str:
    return f"{issue.get('title') or ''}\n{issue.get('description') or ''}".lower()


def issue_covers_family(issue: dict[str, Any], family: dict[str, Any]) -> bool:
    text = issue_text(issue)
    family_key = str(family.get("familyKey") or "")
    canonical_key = str(family.get("canonicalKey") or "")
    if family_key and family_key.lower() in text:
        return True
    if canonical_key and canonical_key.lower() in text:
        return True
    terms = family_coverage_terms(family)
    return bool(terms) and all(term.lower() in text for term in terms)


def list_existing_gitlab_issues(project: dict[str, Any]) -> list[dict[str, Any]]:
    repo = project.get("repo")
    if not repo:
        return []
    repo_path = Path(str(repo)).expanduser()
    if not repo_path.exists():
        return []
    try:
        completed = subprocess.run(
            ["glab", "issue", "list", "--all", "--per-page", "100", "--output", "json"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    try:
        issues = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    return [issue for issue in issues if isinstance(issue, dict)] if isinstance(issues, list) else []


def apply_existing_issue_coverage(
    families: dict[str, Any],
    projects: dict[str, Any],
    project_name: str | None = None,
) -> int:
    """认领 Issue 前检查 GitLab 是否已有覆盖；有则不再创建新 Issue。"""
    changed = 0
    project_names = [project_name] if project_name else sorted({str(f.get("project") or "") for f in families.values()})
    for project_key in project_names:
        if not project_key:
            continue
        issues = list_existing_gitlab_issues(projects.get(project_key, {}))
        if not issues:
            continue
        sorted_issues = sorted(issues, key=lambda item: int(item.get("iid") or 10**9))
        for family_key, family in families.items():
            if family.get("project") != project_key:
                continue
            if family.get("status") == "duplicate" or family.get("issueUrl"):
                continue
            matched = next((issue for issue in sorted_issues if issue_covers_family(issue, family)), None)
            if not matched:
                continue
            family["statusBeforeDuplicate"] = family.get("status", "new")
            family["status"] = "duplicate"
            family["duplicateOf"] = f"gitlab-issue-{matched.get('iid')}"
            family["issueUrl"] = matched.get("web_url") or ""
            family["issueCoverageCheckedAt"] = int(time.time())
            changed += 1
    return changed


def read_ledger(ledger_file: Path | str) -> dict[str, Any]:
    path = Path(ledger_file).expanduser()
    if path == DEFAULT_LEDGER_FILE:
        path = migrate_legacy_file(path, LEGACY_LEDGER_FILE)
    if not path.exists():
        return {"version": 1, "families": {}}
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "families": {}}
    if not isinstance(data, dict):
        return {"version": 1, "families": {}}
    families = data.get("families")
    if not isinstance(families, dict):
        data["families"] = {}
    data.setdefault("version", 1)
    return data


def update_ledger(
    incidents: list[dict[str, Any]],
    ledger_file: Path | str,
    now: float | None = None,
) -> dict[str, bool]:
    current = int(time.time() if now is None else now)
    ledger_path = Path(ledger_file).expanduser()
    ledger = read_ledger(ledger_path)
    families: dict[str, Any] = ledger["families"]
    new_flags: dict[str, bool] = {}
    for incident in incidents:
        family_key = str(incident.get("familyKey") or incident.get("fingerprint"))
        is_new = family_key not in families
        new_flags[family_key] = is_new
        family = families.setdefault(
            family_key,
            {
                "familyKey": family_key,
                "project": incident.get("project"),
                "env": incident.get("env"),
                "source": incident.get("source"),
                "status": "new",
                "firstSeen": incident.get("firstSeen"),
                "lastSeen": incident.get("lastSeen"),
                "occurrences": 0,
                "totalLogCount": 0,
                "fingerprints": [],
                "issueUrl": "",
                "fixBranch": "",
                "mrUrl": "",
                "lastSampleLogs": [],
                "history": [],
            },
        )
        if incident.get("sampleLogs"):
            family["canonicalKey"] = build_family_key(str(incident.get("project") or ""), str(incident.get("env") or ""), incident["sampleLogs"][0])
        family["lastSeen"] = incident.get("lastSeen")
        family["occurrences"] = int(family.get("occurrences") or 0) + 1
        family["totalLogCount"] = int(family.get("totalLogCount") or 0) + int(incident.get("count") or 0)
        fingerprint = incident.get("fingerprint")
        fingerprints = family.setdefault("fingerprints", [])
        if fingerprint and fingerprint not in fingerprints:
            fingerprints.append(fingerprint)
        family["lastSampleLogs"] = incident.get("sampleLogs", [])[:3]
        history = family.setdefault("history", [])
        history.append(
            {
                "at": current,
                "fingerprint": fingerprint,
                "count": incident.get("count"),
                "firstSeen": incident.get("firstSeen"),
                "lastSeen": incident.get("lastSeen"),
            }
        )
        del history[:-50]
    dedupe_existing_families(families)
    write_json_private(ledger_path, ledger)
    return new_flags


def append_report(
    report_file: Path | str,
    event: dict[str, Any],
    incidents: list[dict[str, Any]],
    new_flags: dict[str, bool],
    now: float | None = None,
) -> None:
    path = Path(report_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() if now is None else now))
    lines = [
        f"## {current} {event.get('project') or event.get('service')} {event.get('env')}",
        "",
        f"- 来源：{event.get('source', 'unknown')}",
        f"- 窗口：最近 {event.get('windowMinutes', 'unknown')} 分钟",
        f"- 问题族：{len(incidents)}",
        f"- 新增问题族：{sum(1 for incident in incidents if new_flags.get(str(incident.get('familyKey'))))}",
        "",
    ]
    for incident in incidents:
        family_key = str(incident.get("familyKey") or "")
        status = "新增" if new_flags.get(family_key) else "已知"
        sample = (incident.get("sampleLogs") or [{}])[0]
        lines.append(
            f"- {status} `{family_key}` `{sample.get('logFile', '')}` "
            f"count={incident.get('count')} first={incident.get('firstSeen')} last={incident.get('lastSeen')}"
        )
    lines.append("")
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines))
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def read_state(state_file: Path | str) -> dict[str, Any]:
    path = Path(state_file).expanduser()
    if path == DEFAULT_STATE_FILE:
        path = migrate_legacy_file(path, LEGACY_STATE_FILE)
    if not path.exists():
        return {}
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def state_key(incident: dict[str, Any]) -> str:
    return f"{incident.get('project')}:{incident.get('env')}:{incident.get('familyKey') or incident.get('fingerprint')}"


def should_trigger(
    incident: dict[str, Any],
    state_file: Path | str,
    dedupe_window_minutes: int,
    now: float | None = None,
) -> bool:
    current = time.time() if now is None else now
    state = read_state(state_file)
    last = state.get(state_key(incident))
    try:
        last_seconds = float(last)
    except (TypeError, ValueError):
        return True
    return current - last_seconds >= dedupe_window_minutes * 60


def mark_triggered(incident: dict[str, Any], state_file: Path | str, now: float | None = None) -> None:
    state_path = Path(state_file).expanduser()
    state = read_state(state_path)
    state[state_key(incident)] = time.time() if now is None else now
    write_json_private(state_path, state)


def build_analysis_prompt(project: dict[str, Any], incident: dict[str, Any]) -> str:
    """生成给 Troubleshooting Agent 的任务提示。"""
    database = project.get("testDatabase") if isinstance(project.get("testDatabase"), dict) else {}
    db_lines = [
        f"- 类型：{database.get('type', 'unknown')}",
        f"- Host：{database.get('host', '未配置')}",
        f"- Database：{database.get('database', '未配置')}",
        "- 访问策略：只读；只允许 SELECT / SHOW / EXPLAIN；禁止 INSERT / UPDATE / DELETE / DDL",
    ]
    return f"""你是通用 Troubleshooting Agent。请基于下面的 incident 做根因分析，第一阶段不得自动修改代码。

项目：
- 名称：{incident.get('project')}
- Repo：{project.get('repo', '未配置')}
- 知识库：{project.get('knowledge', '未配置')}

测试数据库：
{chr(10).join(db_lines)}

Incident：
```json
{json.dumps(incident, ensure_ascii=False, indent=2)}
```

要求：
1. 先读取项目 AGENTS.md 和必要知识库索引。
2. 根据日志中的类名、方法、异常栈定位源码。
3. 如需查询数据库，只能查询测试环境，并保持只读。
4. 输出根因判断、影响面、复现/验证建议、可选修复方案。
5. 根因基本明确后，提一个 issue；issue 需要包含现象、影响面、根因判断、验证方式、关联 incident/fingerprint/familyKey 和修复建议。若当前环境没有可用的 Git 服务认证或 issue 创建工具，输出可直接提交的 issue 标题与正文，并明确说明阻塞点。
6. 不得自动修改代码、不得提交、不得推送；除非用户在后续明确要求进入修复阶段。
7. 进入修复阶段时，必须先 `git fetch origin master`，再从 `origin/master` 创建新的修复分支；不得在现有工作分支、`master` 或 `test` 上直接修。
8. 修复完成并验证通过后，推送修复分支，并向 `origin/test` 发起 MR；不要直接推送到 `test`。
9. MR 创建后，把 MR 链接和验证结果发给用户，并更新问题族台账中的 issueUrl、fixBranch、mrUrl。
"""


def build_fix_prompt(project: dict[str, Any], family: dict[str, Any], ledger_file: Path | str) -> str:
    """生成串行修复 Agent 的任务提示。"""
    database = project.get("testDatabase") if isinstance(project.get("testDatabase"), dict) else {}
    return f"""你是 Pixel Studio 线上异常修复 Agent。请只处理下面这一个问题族；一次只能修复一个问题。

项目：
- Repo：{project.get('repo', '未配置')}
- 知识库：{project.get('knowledge', '未配置')}
- Ledger：{Path(ledger_file).expanduser()}

测试数据库：
- 类型：{database.get('type', 'unknown')}
- Host：{database.get('host', '未配置')}
- Database：{database.get('database', '未配置')}
- 访问策略：只读；只允许 SELECT / SHOW / EXPLAIN；禁止 INSERT / UPDATE / DELETE / DDL

问题族：
```json
{json.dumps(family, ensure_ascii=False, indent=2)}
```

GitLab Issue：
- {family.get('issueUrl') or '未创建，禁止开始修复'}

必须遵守：
1. 先读取项目 AGENTS.md、知识库 README 和必要的 shared 调试/安全/Git 规范。
2. 确认上方 GitLab Issue 已存在；如果没有 issueUrl，立即停止，不要开始修复。
3. 修复阶段必须先执行 `git fetch origin master`，再从 `origin/master` 创建新的修复分支；不得在当前分支、`master` 或 `test` 上直接修。
4. 一次只能修复一个问题，不要顺手修其他问题族或无关代码。
5. 修复完成后运行相关验证，写 session，提交并推送修复分支。
6. 向远程 `origin/test` 发起 MR，不要直接推送到 `test`。
7. 把 issue 链接、修复分支、MR 链接和验证结果发给用户，并回写 ledger 中该 family 的 `issueUrl`、`fixBranch`、`mrUrl`、`status`。
"""


def build_issue_prompt(project: dict[str, Any], family: dict[str, Any], ledger_file: Path | str) -> str:
    """生成 GitLab Issue 创建 Agent 的任务提示。"""
    return f"""你是 Pixel Studio 线上异常 Issue 创建 Agent。请只处理下面这一个问题族；先创建 GitLab Issue，不要开始修复。

项目：
- Repo：{project.get('repo', '未配置')}
- 知识库：{project.get('knowledge', '未配置')}
- Ledger：{Path(ledger_file).expanduser()}

问题族：
```json
{json.dumps(family, ensure_ascii=False, indent=2)}
```

必须遵守：
1. 先读取项目 AGENTS.md、知识库 README 和必要的 shared 调试/安全/Git 规范。
2. 自检硬门禁：创建 Issue 前必须先用 `glab issue list --all --per-page 100 --output json` 检查现有 Issue 是否已经覆盖同类问题；检查范围包括 open 和 closed issue，匹配依据包括 familyKey、canonicalKey、fingerprint、异常类、核心错误语义和模块/链路关键词。
3. 如果现有 Issue 已覆盖该问题，不得创建新 Issue；只回写 ledger：`status=duplicate`、`issueUrl=<已有 Issue URL>`、`duplicateOf=<已有 Issue 标识>`，并在最终回复说明复用了哪个 Issue。
4. 只有确认没有现有 Issue 覆盖后，才完成根因分析摘要并创建 GitLab Issue；不要创建修复分支，不要修改代码，不要提交，不要推送。
5. 新 Issue 内容必须包含：现象、影响面、根因判断、验证方式、关联 familyKey/fingerprint/canonicalKey、建议修复方向。
6. 如果本机缺少 `glab`、GitLab token 或认证，不能完成现有 Issue 检查或创建 Issue 时，输出可直接提交的 Issue 标题和正文，并说明缺少的认证/工具；仍然不要开始修复。
7. Issue 创建成功后，回写 ledger 中该 family 的 `issueUrl` 和 `status=issue_created`。
8. 不要输出 Cookie、token、App Secret、数据库密码或飞书凭据。
"""


def active_family_by_status(
    families: dict[str, Any],
    statuses: set[str],
    project_name: str | None = None,
) -> tuple[str, dict[str, Any]] | None:
    for family_key, family in families.items():
        if project_name and family.get("project") != project_name:
            continue
        if family.get("status") in statuses:
            return str(family_key), family
    return None


def active_fix_family(families: dict[str, Any], project_name: str | None = None) -> tuple[str, dict[str, Any]] | None:
    return active_family_by_status(families, ACTIVE_FIX_STATUSES, project_name)


def active_issue_family(families: dict[str, Any], project_name: str | None = None) -> tuple[str, dict[str, Any]] | None:
    return active_family_by_status(families, ACTIVE_ISSUE_STATUSES, project_name)


def select_next_issue_family(families: dict[str, Any], project_name: str | None = None) -> tuple[str, dict[str, Any]] | None:
    candidates: list[tuple[str, dict[str, Any]]] = []
    for family_key, family in families.items():
        if project_name and family.get("project") != project_name:
            continue
        if family.get("status", "new") == "new" and not family.get("issueUrl"):
            candidates.append((str(family_key), family))
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            int(item[1].get("totalLogCount") or 0),
            int(item[1].get("occurrences") or 0),
            str(item[1].get("lastSeen") or ""),
        ),
        reverse=True,
    )[0]


def select_next_fix_family(families: dict[str, Any], project_name: str | None = None) -> tuple[str, dict[str, Any]] | None:
    candidates: list[tuple[str, dict[str, Any]]] = []
    for family_key, family in families.items():
        if project_name and family.get("project") != project_name:
            continue
        if family.get("status") == "issue_created" and family.get("issueUrl"):
            candidates.append((str(family_key), family))
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            int(item[1].get("totalLogCount") or 0),
            int(item[1].get("occurrences") or 0),
            str(item[1].get("lastSeen") or ""),
        ),
        reverse=True,
    )[0]


def reserve_next_issue(
    project_name: str | None = None,
    config_file: Path | str | None = None,
    ledger_file: Path | str = DEFAULT_LEDGER_FILE,
    issue_dir: Path | str = DEFAULT_ISSUE_DIR,
    now: float | None = None,
) -> dict[str, Any]:
    projects = load_project_registry(config_file)
    ledger_path = Path(ledger_file).expanduser()
    ledger = read_deduped_ledger(ledger_path, project_name)
    families: dict[str, Any] = ledger["families"]
    if apply_existing_issue_coverage(families, projects, project_name):
        write_json_private(ledger_path, ledger)
    selected = select_next_issue_family(families, project_name)
    if not selected:
        return {"reserved": False, "reason": "no_new_family", "ledgerFile": str(ledger_path)}

    family_key, family = selected
    project_key = str(family.get("project") or project_name or "")
    project = projects.get(project_key, {})
    current = int(time.time() if now is None else now)
    family["status"] = "queued_for_issue"
    family["issueQueuedAt"] = current
    family.setdefault("issueUrl", "")
    family.setdefault("fixBranch", "")
    family.setdefault("mrUrl", "")

    directory = Path(issue_dir).expanduser()
    name = safe_filename(f"{current}-{project_key}-{family_key}")
    prompt_file = directory / f"{name}.issue.prompt.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(build_issue_prompt(project, family, ledger_path), encoding="utf-8")
    prompt_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    write_json_private(ledger_path, ledger)
    return {
        "reserved": True,
        "familyKey": family_key,
        "project": project_key,
        "status": family["status"],
        "promptFile": str(prompt_file),
        "ledgerFile": str(ledger_path),
    }


def reserve_next_fix(
    project_name: str | None = None,
    config_file: Path | str | None = None,
    ledger_file: Path | str = DEFAULT_LEDGER_FILE,
    fix_dir: Path | str = DEFAULT_FIX_DIR,
    now: float | None = None,
) -> dict[str, Any]:
    projects = load_project_registry(config_file)
    ledger_path = Path(ledger_file).expanduser()
    ledger = read_deduped_ledger(ledger_path, project_name)
    families: dict[str, Any] = ledger["families"]
    selected = select_next_fix_family(families, project_name)
    if not selected:
        has_issue_required = any(
            (not project_name or family.get("project") == project_name)
            and family.get("status", "new") in {"new", "queued_for_issue", "creating_issue"}
            and not family.get("issueUrl")
            for family in families.values()
        )
        return {
            "reserved": False,
            "reason": "issue_required" if has_issue_required else "no_issue_created_family",
            "ledgerFile": str(ledger_path),
        }

    family_key, family = selected
    project_key = str(family.get("project") or project_name or "")
    project = projects.get(project_key, {})
    current = int(time.time() if now is None else now)
    family["status"] = "queued_for_fix"
    family["queuedAt"] = current
    family.setdefault("issueUrl", "")
    family.setdefault("fixBranch", "")
    family.setdefault("mrUrl", "")

    directory = Path(fix_dir).expanduser()
    name = safe_filename(f"{current}-{project_key}-{family_key}")
    prompt_file = directory / f"{name}.fix.prompt.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(build_fix_prompt(project, family, ledger_path), encoding="utf-8")
    prompt_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    write_json_private(ledger_path, ledger)
    return {
        "reserved": True,
        "familyKey": family_key,
        "project": project_key,
        "status": family["status"],
        "promptFile": str(prompt_file),
        "ledgerFile": str(ledger_path),
    }


def reserve_many(
    reserve_fn: Any,
    limit: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """连续认领多个问题族；每个返回项仍只对应一个问题族。"""
    items: list[dict[str, Any]] = []
    last: dict[str, Any] | None = None
    for _ in range(max(1, limit)):
        result = reserve_fn(**kwargs)
        if not result.get("reserved"):
            last = result
            break
        items.append(result)
        last = result
    if limit <= 1:
        return items[0] if items else (last or {"reserved": False, "reason": "not_reserved"})
    return {
        "reserved": bool(items),
        "count": len(items),
        "items": items,
        "reason": None if items else (last or {}).get("reason"),
        "nextReason": (last or {}).get("reason") if last and not last.get("reserved") else None,
        "ledgerFile": (last or items[-1] if items else {}).get("ledgerFile"),
    }


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def write_incident_artifacts(
    incident: dict[str, Any],
    project: dict[str, Any],
    incident_dir: Path | str,
    now: float | None = None,
) -> dict[str, str]:
    current = int(time.time() if now is None else now)
    directory = Path(incident_dir).expanduser()
    name = safe_filename(f"{current}-{incident.get('project')}-{incident.get('fingerprint')}")
    incident_file = directory / f"{name}.json"
    prompt_file = directory / f"{name}.prompt.md"
    write_json_private(incident_file, incident)
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(build_analysis_prompt(project, incident), encoding="utf-8")
    prompt_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {"incidentFile": str(incident_file), "promptFile": str(prompt_file)}


def route_event(
    event: dict[str, Any],
    config_file: Path | str | None = None,
    incident_dir: Path | str = DEFAULT_INCIDENT_DIR,
    state_file: Path | str = DEFAULT_STATE_FILE,
    ledger_file: Path | str = DEFAULT_LEDGER_FILE,
    report_file: Path | str = DEFAULT_REPORT_FILE,
    threshold: int = 1,
    dedupe_window_minutes: int = 30,
    now: float | None = None,
) -> dict[str, Any]:
    projects = load_project_registry(config_file)
    project_name = str(event.get("project") or event.get("service") or "")
    if project_name not in projects:
        raise RuntimeError(f"项目未注册：{project_name}")
    project = projects[project_name]
    incidents = extract_incidents(event, threshold=threshold)
    new_flags = update_ledger(incidents, ledger_file, now=now)
    append_report(report_file, event, incidents, new_flags, now=now)
    result_items: list[dict[str, Any]] = []
    for incident in incidents:
        family_key = str(incident.get("familyKey") or "")
        if not new_flags.get(family_key):
            result_items.append({"trigger": False, "reason": "known_family", **incident})
        elif should_trigger(incident, state_file, dedupe_window_minutes, now=now):
            paths = write_incident_artifacts(incident, project, incident_dir, now=now)
            mark_triggered(incident, state_file, now=now)
            result_items.append({"trigger": True, **incident, **paths})
        else:
            result_items.append({"trigger": False, "reason": "deduped", **incident})
    return {
        "project": project_name,
        "triggered": sum(1 for item in result_items if item["trigger"]),
        "newFamilies": sum(1 for incident in incidents if new_flags.get(str(incident.get("familyKey")))),
        "knownFamilies": sum(1 for incident in incidents if not new_flags.get(str(incident.get("familyKey")))),
        "ledgerFile": str(Path(ledger_file).expanduser()),
        "reportFile": str(Path(report_file).expanduser()),
        "incidents": result_items,
    }


def load_event_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.input == "-":
        return json.loads(sys.stdin.read())
    return read_json(Path(args.input).expanduser())


def command_route(args: argparse.Namespace) -> None:
    event = load_event_from_args(args)
    result = route_event(
        event,
        config_file=args.config,
        incident_dir=args.incident_dir,
        state_file=args.state_file,
        ledger_file=args.ledger_file,
        report_file=args.report_file,
        threshold=args.threshold,
        dedupe_window_minutes=args.dedupe_window_minutes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_prompt(args: argparse.Namespace) -> None:
    print(Path(args.prompt_file).expanduser().read_text(encoding="utf-8"))


def command_next_fix(args: argparse.Namespace) -> None:
    result = reserve_many(
        reserve_next_fix,
        limit=args.limit,
        project_name=args.project,
        config_file=args.config,
        ledger_file=args.ledger_file,
        fix_dir=args.fix_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_next_issue(args: argparse.Namespace) -> None:
    result = reserve_many(
        reserve_next_issue,
        limit=args.limit,
        project_name=args.project,
        config_file=args.config,
        ledger_file=args.ledger_file,
        issue_dir=args.issue_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="通用 Incident Router Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    route = subparsers.add_parser("route", help="从统一事件 JSON 生成 incident 和分析 Agent prompt")
    route.add_argument("--input", required=True, help="事件 JSON 文件路径；传 - 表示 stdin")
    route.add_argument("--config", help="项目注册表 JSON，默认项目 .agent-state/wmxs-agent/projects.json 或仓库示例")
    route.add_argument("--incident-dir", default=str(DEFAULT_INCIDENT_DIR), help="incident 输出目录")
    route.add_argument("--state-file", default=str(DEFAULT_STATE_FILE), help="去重状态文件")
    route.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="问题族台账文件")
    route.add_argument("--report-file", default=str(DEFAULT_REPORT_FILE), help="巡检汇总 Markdown")
    route.add_argument("--threshold", type=int, default=1, help="同指纹触发最小日志数")
    route.add_argument("--dedupe-window-minutes", type=int, default=30, help="同指纹去重窗口分钟数")
    route.set_defaults(func=command_route)

    prompt = subparsers.add_parser("prompt", help="打印已生成的分析 Agent prompt")
    prompt.add_argument("--prompt-file", required=True, help="prompt 文件路径")
    prompt.set_defaults(func=command_prompt)

    next_issue = subparsers.add_parser("next-issue", help="从问题族台账中认领待创建 Issue 的问题")
    next_issue.add_argument("--project", help="只认领指定项目的问题族")
    next_issue.add_argument("--config", help="项目注册表 JSON，默认项目 .agent-state/wmxs-agent/projects.json 或仓库示例")
    next_issue.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="问题族台账文件")
    next_issue.add_argument("--issue-dir", default=str(DEFAULT_ISSUE_DIR), help="Issue prompt 输出目录")
    next_issue.add_argument("--limit", type=int, default=1, help="本次最多认领多少个问题族")
    next_issue.set_defaults(func=command_next_issue)

    next_fix = subparsers.add_parser("next-fix", help="从问题族台账中认领待修复问题")
    next_fix.add_argument("--project", help="只认领指定项目的问题族")
    next_fix.add_argument("--config", help="项目注册表 JSON，默认项目 .agent-state/wmxs-agent/projects.json 或仓库示例")
    next_fix.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="问题族台账文件")
    next_fix.add_argument("--fix-dir", default=str(DEFAULT_FIX_DIR), help="修复 prompt 输出目录")
    next_fix.add_argument("--limit", type=int, default=1, help="本次最多认领多少个问题族")
    next_fix.set_defaults(func=command_next_fix)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI 输出可读错误。
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
