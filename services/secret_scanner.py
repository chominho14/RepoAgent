# 민감 정보(토큰·키·패스워드)가 포함된 파일을 탐지하는 스캐너
import re
from dataclasses import dataclass
from pathlib import Path

_NAME_PATTERNS: list[tuple[str, str]] = [
    (r"^\.env$|\.env\.", "env 파일"),
    (r"\.key$|\.pem$|\.p12$|\.pfx$|\.keystore$", "키 파일"),
    (r"id_rsa|id_ed25519|id_dsa|id_ecdsa", "SSH 개인키"),
    (r"secret|credential|password", "파일명에 민감 키워드"),
]

_CONTENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS 액세스 키"),
    (re.compile(r"sk-[a-zA-Z0-9]{48}"), "OpenAI API 키"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "GitHub PAT"),
    (re.compile(r"glpat-[a-zA-Z0-9\-]{20}"), "GitLab PAT"),
    (re.compile(r"-----BEGIN .{0,20}PRIVATE KEY-----"), "개인키"),
    (re.compile(r'(?i)(?:password|passwd|secret|api_key|token)\s*[=:]\s*["\'][^"\']{8,}'),
     "하드코딩된 패스워드/토큰"),
]

_MAX_SCAN_BYTES = 500_000  # 500KB 초과 파일은 내용 스캔 생략


@dataclass
class SecretFile:
    path: str    # root 기준 상대경로
    folder: str  # 최상위 폴더명
    reason: str  # 탐지 이유


def scan_sensitive_files(root: Path) -> list[SecretFile]:
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        folder = rel.split("/")[0] if "/" in rel else "."
        reason = _check_name(path.name) or _check_content(path)
        if reason:
            found.append(SecretFile(path=rel, folder=folder, reason=reason))
    return found


def _check_name(name: str) -> str:
    name_lower = name.lower()
    for pattern, label in _NAME_PATTERNS:
        if re.search(pattern, name_lower):
            return label
    return ""


def _check_content(path: Path) -> str:
    try:
        if path.stat().st_size > _MAX_SCAN_BYTES:
            return ""
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    for pattern, label in _CONTENT_PATTERNS:
        if pattern.search(text):
            return label
    return ""
