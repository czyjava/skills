#!/usr/bin/env python3
"""审计 Java 工程的 Modulith 边界与 Javadoc 基线。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


POJO_SUFFIXES = (
    "Api",
    "Command",
    "Query",
    "Result",
    "Request",
    "Response",
    "Req",
    "Resp",
    "DTO",
    "Dto",
    "Event",
    "Payload",
    "Config",
    "Rule",
    "Policy",
    "Context",
    "Entity",
    "DO",
)

TYPE_RE = re.compile(
    r"(?m)^[ \t]*(?P<mods>(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed|strictfp)\s+)*)"
    r"(?P<kind>@interface|class|interface|record|enum)\s+(?P<name>[A-Za-z_$][\w$]*)"
)
METHOD_RE = re.compile(
    r"(?m)^[ \t]*(?P<mods>(?:(?:public|protected|private|static|final|abstract|synchronized|default|native|strictfp)\s+)*)"
    r"(?P<return>[A-Za-z_$][\w$<>,.? @\[\]]*?)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*\((?P<params>[^;{}()]*)\)\s*"
    r"(?:throws\s+(?P<throws>[A-Za-z_$][\w$.,<> ?]*))?\s*(?:\{|;)"
)
CONSTRUCTOR_RE = re.compile(
    r"(?m)^[ \t]*(?P<mods>(?:(?:public|protected|private)\s+)+)"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*\((?P<params>[^;{}()]*)\)\s*"
    r"(?:throws\s+(?P<throws>[A-Za-z_$][\w$.,<> ?]*))?\s*\{"
)
PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([\w.]+)\s*;")
IMPORT_RE = re.compile(r"(?m)^\s*import\s+(?P<static>static\s+)?(?P<name>[\w.*]+)\s*;")
JAVADOC_RE = re.compile(r"/\*\*.*?\*/", re.DOTALL)


@dataclass(frozen=True)
class Finding:
    """一条可稳定序列化的审计结果。"""

    severity: str
    code: str
    path: str
    line: int
    message: str


@dataclass(frozen=True)
class TypeInfo:
    """源码类型及其主体范围。"""

    name: str
    kind: str
    modifiers: tuple[str, ...]
    start: int
    body_start: int
    body_end: int
    body_depth: int


def _mask_non_code(source: str) -> str:
    """保留字符位置并屏蔽注释与字符串，避免括号统计受文本内容干扰。"""

    chars = list(source)
    pattern = re.compile(r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", re.DOTALL)
    for match in pattern.finditer(source):
        for index in range(match.start(), match.end()):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def _brace_depths(masked: str) -> list[int]:
    """计算每个字符位置之前的大括号深度。"""

    depths = [0] * (len(masked) + 1)
    depth = 0
    for index, char in enumerate(masked):
        depths[index] = depth
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
    depths[len(masked)] = depth
    return depths


def _matching_brace(masked: str, opening: int) -> int:
    """返回与 opening 对应的右大括号位置。"""

    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return len(masked)


def _types(source: str, masked: str, depths: Sequence[int]) -> list[TypeInfo]:
    """提取能够可靠定位主体范围的类型。"""

    result: list[TypeInfo] = []
    for match in TYPE_RE.finditer(masked):
        opening = masked.find("{", match.end())
        if opening < 0:
            continue
        # 遇到分号说明该声明不是当前正则期望的普通类型主体。
        semicolon = masked.find(";", match.end(), opening)
        if semicolon >= 0:
            continue
        result.append(
            TypeInfo(
                name=match.group("name"),
                kind=match.group("kind"),
                modifiers=tuple(match.group("mods").split()),
                start=match.start(),
                body_start=opening,
                body_end=_matching_brace(masked, opening),
                body_depth=depths[opening] + 1,
            )
        )
    return result


def _line_number(source: str, position: int) -> int:
    """把字符偏移转换为从 1 开始的行号。"""

    return source.count("\n", 0, position) + 1


def _annotation_only_gap(gap: str) -> bool:
    """判断 Javadoc 与声明之间是否只有空白和注解。"""

    in_annotation = False
    parenthesis_depth = 0
    for raw_line in gap.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not in_annotation:
            if not line.startswith("@"):
                return False
            in_annotation = True
            parenthesis_depth = line.count("(") - line.count(")")
            if parenthesis_depth <= 0:
                in_annotation = False
        else:
            parenthesis_depth += line.count("(") - line.count(")")
            if parenthesis_depth <= 0:
                in_annotation = False
    return not in_annotation


def _javadoc_before(source: str, position: int) -> str | None:
    """查找紧邻声明且允许中间存在注解的 Javadoc。"""

    documents = list(JAVADOC_RE.finditer(source, 0, position))
    if not documents:
        return None
    document = documents[-1]
    if _annotation_only_gap(source[document.end() : position]):
        return document.group()
    return None


def _package_name(source: str) -> str | None:
    """读取 Java 源码包名。"""

    match = PACKAGE_RE.search(source)
    return match.group(1) if match else None


def _split_top_level(value: str) -> list[str]:
    """按顶层逗号切分泛型参数或异常列表。"""

    result: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char in "<([{":
            depth += 1
        elif char in ">)]}":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        result.append("".join(current).strip())
    return [item for item in result if item]


def _parameter_names(parameters: str) -> list[str]:
    """从常见 Java 方法签名中提取参数名。"""

    names: list[str] = []
    for parameter in _split_top_level(parameters):
        cleaned = re.sub(r"@[\w.]+(?:\([^)]*\))?", " ", parameter)
        cleaned = re.sub(r"\bfinal\b", " ", cleaned).strip()
        match = re.search(r"([A-Za-z_$][\w$]*)\s*(?:\[\])?\s*$", cleaned)
        if match:
            names.append(match.group(1))
    return names


def _tag_names(document: str, tag: str) -> set[str]:
    """读取 Javadoc 指定标签的首个参数。"""

    return set(re.findall(rf"@{re.escape(tag)}\s+([\w$<>.]+)", document))


def _relative(path: Path, root: Path) -> str:
    """返回稳定的仓库相对路径。"""

    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _discover_roots(repo_root: Path, configured: Sequence[str]) -> list[Path]:
    """发现主流 Maven/Gradle Java 源码根，或解析显式配置。"""

    if configured:
        return [(repo_root / value).resolve() for value in configured]
    roots = [
        path
        for path in repo_root.rglob("java")
        if path.is_dir() and path.parent.name in {"main", "test", "integrationTest"} and path.parent.parent.name == "src"
    ]
    return sorted(set(roots))


def _java_files(roots: Iterable[Path], base_package: str | None) -> list[Path]:
    """收集审计范围内的 Java 文件。"""

    files: set[Path] = set()
    package_fragment = Path(*base_package.split(".")) if base_package else None
    for root in roots:
        search_root = root / package_fragment if package_fragment else root
        if search_root.exists():
            files.update(search_root.rglob("*.java"))
    return sorted(files)


def _enclosing_type(types: Sequence[TypeInfo], position: int) -> TypeInfo | None:
    """返回位置所在的最内层类型。"""

    candidates = [item for item in types if item.body_start < position < item.body_end]
    return min(candidates, key=lambda item: item.body_end - item.body_start) if candidates else None


def _record_components(masked: str, type_info: TypeInfo) -> list[str]:
    """提取 record component 名称，用类型 Javadoc 的 @param 校验。"""

    if type_info.kind != "record":
        return []
    declaration = masked[type_info.start : type_info.body_start]
    opening = declaration.find("(")
    closing = declaration.rfind(")")
    if opening < 0 or closing < opening:
        return []
    return _parameter_names(declaration[opening + 1 : closing])


def _audit_javadocs(path: Path, root: Path, source: str, package: str | None) -> list[Finding]:
    """审计公开类型、POJO 字段和公开/核心方法的 Javadoc。"""

    findings: list[Finding] = []
    relative = _relative(path, root)
    masked = _mask_non_code(source)
    depths = _brace_depths(masked)
    types = _types(source, masked, depths)

    for type_info in types:
        is_public = "public" in type_info.modifiers
        is_business_object = type_info.name.endswith(POJO_SUFFIXES)
        document = _javadoc_before(source, type_info.start)
        if (is_public or is_business_object) and not document:
            findings.append(
                Finding("warning", "DOC001", relative, _line_number(source, type_info.start), f"类型 {type_info.name} 缺少 Javadoc")
            )
        if document and type_info.kind == "record":
            tags = _tag_names(document, "param")
            for component in _record_components(masked, type_info):
                if component not in tags:
                    findings.append(
                        Finding(
                            "warning",
                            "DOC004",
                            relative,
                            _line_number(source, type_info.start),
                            f"record component {component} 缺少 @param",
                        )
                    )

        if not is_business_object:
            continue
        body = masked[type_info.body_start + 1 : type_info.body_end]
        offset = type_info.body_start + 1
        for line_match in re.finditer(r"(?m)^[ \t]*[^\n;]+;", body):
            position = offset + line_match.start()
            if depths[position] != type_info.body_depth:
                continue
            declaration = line_match.group().strip()
            left = declaration[:-1].split("=", 1)[0].strip()
            if "(" in left or re.search(r"\bstatic\b", left) or "," in left:
                continue
            name_match = re.search(r"([A-Za-z_$][\w$]*)\s*$", left)
            if not name_match:
                continue
            field_name = name_match.group(1)
            if field_name == "serialVersionUID":
                continue
            if not _javadoc_before(source, position):
                findings.append(
                    Finding(
                        "warning",
                        "DOC002",
                        relative,
                        _line_number(source, position),
                        f"业务对象字段 {type_info.name}.{field_name} 缺少 Javadoc",
                    )
                )

    for match in METHOD_RE.finditer(masked):
        owner = _enclosing_type(types, match.start())
        if not owner or depths[match.start()] != owner.body_depth:
            continue
        modifiers = set(match.group("mods").split())
        if match.group("name") == owner.name:
            continue
        is_interface_method = owner.kind in {"interface", "@interface"}
        is_public_surface = bool({"public", "protected"} & modifiers) or is_interface_method
        is_core_method = bool(package and (".application" in package or ".domain" in package)) and "private" not in modifiers
        if not (is_public_surface or is_core_method):
            continue

        line = _line_number(source, match.start())
        document = _javadoc_before(source, match.start())
        method_name = match.group("name")
        if not document:
            findings.append(Finding("warning", "DOC003", relative, line, f"方法 {owner.name}.{method_name} 缺少 Javadoc"))
            continue

        parameter_tags = _tag_names(document, "param")
        for parameter in _parameter_names(match.group("params")):
            if parameter not in parameter_tags:
                findings.append(
                    Finding("warning", "DOC004", relative, line, f"方法 {owner.name}.{method_name} 的参数 {parameter} 缺少 @param")
                )
        return_type = re.sub(r"\s+", " ", match.group("return")).strip().split()[-1]
        if return_type != "void" and "@return" not in document:
            findings.append(Finding("warning", "DOC005", relative, line, f"方法 {owner.name}.{method_name} 缺少 @return"))
        throws_tags = _tag_names(document, "throws") | _tag_names(document, "exception")
        for exception in _split_top_level(match.group("throws") or ""):
            simple_name = re.sub(r"<.*>", "", exception).strip().split(".")[-1]
            if simple_name and simple_name not in throws_tags and exception.strip() not in throws_tags:
                findings.append(
                    Finding("warning", "DOC006", relative, line, f"方法 {owner.name}.{method_name} 的异常 {simple_name} 缺少 @throws")
                )

    for match in CONSTRUCTOR_RE.finditer(masked):
        owner = _enclosing_type(types, match.start())
        if not owner or match.group("name") != owner.name or depths[match.start()] != owner.body_depth:
            continue
        modifiers = set(match.group("mods").split())
        if not ({"public", "protected"} & modifiers):
            continue
        line = _line_number(source, match.start())
        document = _javadoc_before(source, match.start())
        if not document:
            findings.append(Finding("warning", "DOC003", relative, line, f"构造方法 {owner.name} 缺少 Javadoc"))
            continue
        parameter_tags = _tag_names(document, "param")
        for parameter in _parameter_names(match.group("params")):
            if parameter not in parameter_tags:
                findings.append(Finding("warning", "DOC004", relative, line, f"构造方法 {owner.name} 的参数 {parameter} 缺少 @param"))
        throws_tags = _tag_names(document, "throws") | _tag_names(document, "exception")
        for exception in _split_top_level(match.group("throws") or ""):
            simple_name = re.sub(r"<.*>", "", exception).strip().split(".")[-1]
            if simple_name and simple_name not in throws_tags and exception.strip() not in throws_tags:
                findings.append(Finding("warning", "DOC006", relative, line, f"构造方法 {owner.name} 的异常 {simple_name} 缺少 @throws"))
    return findings


def audit(repo_root: Path, source_roots: Sequence[str], base_package: str | None) -> tuple[list[Finding], int, int]:
    """执行完整审计并返回结果、文件数和业务模块数。"""

    roots = _discover_roots(repo_root, source_roots)
    files = _java_files(roots, base_package)
    findings: list[Finding] = []
    sources = {path: path.read_text(encoding="utf-8") for path in files}
    main_sources = {path: value for path, value in sources.items() if "/src/test/" not in path.as_posix()}

    if not any("@Modulithic" in source for source in main_sources.values()):
        findings.append(Finding("error", "ARCH001", ".", 1, "未发现 @Modulithic 结构入口"))
    verify_pattern = re.compile(r"ApplicationModules\s*\.\s*of\s*\(.*?\)\s*\.\s*verify\s*\(", re.DOTALL)
    if not any(verify_pattern.search(source) for source in sources.values()):
        findings.append(Finding("error", "ARCH002", ".", 1, "未发现 ApplicationModules.of(...).verify() 结构测试"))

    module_packages: list[str] = []
    named_packages: list[str] = []
    for path, source in main_sources.items():
        package = _package_name(source)
        if not package or path.name != "package-info.java":
            continue
        package_match = PACKAGE_RE.search(source)
        if ("@ApplicationModule" in source or "@NamedInterface" in source) and package_match and not _javadoc_before(source, package_match.start()):
            findings.append(
                Finding("warning", "DOC007", _relative(path, repo_root), _line_number(source, package_match.start()), f"模块或命名接口包 {package} 缺少包级 Javadoc")
            )
        if "@ApplicationModule" in source:
            if not re.search(r"type\s*=\s*ApplicationModule\.Type\.OPEN", source):
                module_packages.append(package)
        if "@NamedInterface" in source:
            named_packages.append(package)

    module_packages = sorted(set(module_packages), key=len, reverse=True)
    named_packages = sorted(set(named_packages), key=len, reverse=True)
    for path, source in main_sources.items():
        package = _package_name(source)
        if not package:
            continue
        owner = next((item for item in module_packages if package == item or package.startswith(f"{item}.")), None)
        if not owner:
            continue
        for import_match in IMPORT_RE.finditer(source):
            imported = import_match.group("name")
            target = next((item for item in module_packages if imported.startswith(f"{item}.")), None)
            if not target or target == owner:
                continue
            if any(imported.startswith(f"{named}.") for named in named_packages):
                continue
            remainder = imported[len(target) + 1 :]
            # 根包公开类型只有一个类型名片段；出现更多片段即表示访问了未开放子包。
            allowed_dots = 1 if import_match.group("static") else 0
            if remainder.count(".") > allowed_dots:
                import_position = import_match.start("name")
                findings.append(
                    Finding(
                        "error",
                        "ARCH003",
                        _relative(path, repo_root),
                        _line_number(source, import_position),
                        f"领域 {owner} 跨域访问了 {target} 的未开放子包：{imported}",
                    )
                )

    for path, source in sources.items():
        if path.name == "package-info.java":
            continue
        findings.extend(_audit_javadocs(path, repo_root, source, _package_name(source)))

    findings.sort(key=lambda item: (item.path, item.line, item.code, item.message))
    return findings, len(files), len(module_packages)


def _print_text(findings: Sequence[Finding], file_count: int, module_count: int) -> None:
    """输出便于本地阅读的中文报告。"""

    print(f"[INFO] 已扫描 {file_count} 个 Java 文件，识别 {module_count} 个关闭业务模块")
    for finding in findings:
        print(f"[{finding.severity.upper()}] {finding.code} {finding.path}:{finding.line} {finding.message}")
    error_count = sum(item.severity == "error" for item in findings)
    warning_count = sum(item.severity == "warning" for item in findings)
    print(f"[INFO] 审计完成：{error_count} 个错误，{warning_count} 个警告")


def _should_fail(findings: Sequence[Finding], fail_on: str) -> bool:
    """根据命令行门槛判断退出码。"""

    if fail_on == "never":
        return False
    if fail_on == "warning":
        return bool(findings)
    return any(item.severity == "error" for item in findings)


def main(argv: Sequence[str] | None = None) -> int:
    """解析参数、执行审计并返回适合 CI 的退出码。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="目标 Java 工程根目录")
    parser.add_argument("--source-root", action="append", default=[], help="相对工程根目录的源码根，可重复指定")
    parser.add_argument("--base-package", help="限制审计的 Java 基础包，例如 cn.mucang.example")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="报告格式")
    parser.add_argument("--fail-on", choices=("error", "warning", "never"), default="error", help="触发非零退出码的最低级别")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    if not repo_root.is_dir():
        parser.error(f"工程根目录不存在：{repo_root}")
    findings, file_count, module_count = audit(repo_root, args.source_root, args.base_package)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "repoRoot": repo_root.as_posix(),
                    "fileCount": file_count,
                    "moduleCount": module_count,
                    "findings": [asdict(item) for item in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_text(findings, file_count, module_count)
    return 1 if _should_fail(findings, args.fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())
