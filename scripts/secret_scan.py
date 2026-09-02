"""Scan Git-tracked text files for credential-like material.

The scanner intentionally reports only a repository-relative path and rule name.
``redact_sensitive_text`` is suitable for audit text before it is persisted or
printed; it is best-effort and does not replace a secret manager.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class UnsafeRedactionError(ValueError):
    """Raised when an ambiguous PEM fallback cannot be safely bounded."""


_PLACEHOLDER_WORDS = {
    "change-me",
    "changeme",
    "dummy",
    "example",
    "placeholder",
    "replace-me",
    "<replace-me>",
    "your-kis-app-key",
    "your-kis-app-secret",
    "your-api-key",
    "your-api-secret",
    "secret",
    "test",
    "[redacted]",
    "[redacted_private_key]",
}
_NON_LITERAL_IDENTIFIERS = {
    "current_key",
    "key",
    "record",
    "response",
    "str",
    "token",
    "value",
}
_PEM_HEADER = r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
_PEM_FOOTER = r"-----END [A-Z0-9 ]*PRIVATE KEY-----"
_PEM_SEPARATOR = r"(?:\r?\n|\\n)"
_PEM_COMPLETE_BODY = r"[A-Za-z0-9+/=]{1,76}"
_PEM_UNTERMINATED_BODY = r"[A-Za-z0-9+/=]{1,76}"
_PEM_SHORT_BODY = r"[A-Za-z0-9+/=]{1,3}"
_PEM_BODY_FOLLOW = r"(?=[ \t]*(?:\r?\n|\\n|\Z|[\"']\s*[,}\]]))"
_PEM_JSON_BODY_FOLLOW = r"(?=[ \t]*(?:[\"']\s*[,}\]]))"
_PEM_COMPLETE = re.compile(
    _PEM_HEADER
    + r"[ \t]*"
    + _PEM_SEPARATOR
    + _PEM_COMPLETE_BODY
    + r"(?:[ \t]*"
    + _PEM_SEPARATOR
    + _PEM_COMPLETE_BODY
    + r")*[ \t]*"
    + _PEM_SEPARATOR
    + _PEM_FOOTER,
    re.IGNORECASE,
)
_PEM_UNTERMINATED_JSON = re.compile(
    _PEM_HEADER
    + r"[ \t]*"
    + _PEM_SEPARATOR
    + _PEM_UNTERMINATED_BODY
    + r"(?:[ \t]*"
    + _PEM_SEPARATOR
    + _PEM_UNTERMINATED_BODY
    + r")*"
    + _PEM_JSON_BODY_FOLLOW,
    re.IGNORECASE,
)
_PEM_UNTERMINATED_BLANK = re.compile(
    _PEM_HEADER
    + r"[ \t]*"
    + _PEM_SEPARATOR
    + _PEM_UNTERMINATED_BODY
    + r"(?:[ \t]*"
    + _PEM_SEPARATOR
    + _PEM_UNTERMINATED_BODY
    + r")*"
    + r"(?=[ \t]*\r?\n[ \t]*\r?\n)",
    re.IGNORECASE,
)
_PEM_UNTERMINATED = re.compile(
    _PEM_HEADER
    + r"[ \t]*(?:"
    + _PEM_SEPARATOR
    + _PEM_UNTERMINATED_BODY
    + _PEM_BODY_FOLLOW
    + r")?",
    re.IGNORECASE,
)
_PEM_AMBIGUOUS = re.compile(
    _PEM_HEADER
    + r"[ \t]*"
    + _PEM_SEPARATOR
    # A short first line is deliberately explicit: it is still a possible
    # PEM body line, so a following base64-looking line must fail closed.
    + rf"(?:{_PEM_SHORT_BODY}|[A-Za-z0-9+/=]{{4,76}})[ \t]*"
    + _PEM_SEPARATOR
    + _PEM_UNTERMINATED_BODY
    + _PEM_BODY_FOLLOW,
    re.IGNORECASE,
)
_PEM_HEADER_RE = re.compile(_PEM_HEADER, re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+([A-Za-z0-9._~+/=-]{8,})", re.IGNORECASE)
_ASSIGNMENT = re.compile(
    r"(?P<prefix>(?:export[ \t]+)?(?:const|let|var)[ \t]+|export[ \t]+)?"
    r"(?P<key_quote>(?:\\['\"]|['\"])?)(?P<name>\b(?:[A-Za-z][A-Za-z0-9_-]*(?:key|secret|token|password|passwd)|key|secret|token|password|passwd)\b)"
    r"(?P=key_quote)"
    r"[ \t]*(?P<separator>[:=])[ \t]*"
    r"(?:(?P<quote>(?:\\['\"]|['\"]))(?P<quoted_value>(?:\\.|[^'\"\\\r\n])*?)(?P=quote)"
    r"(?=[ \t]*(?:[,}\]]|$|#|;|&&|\|\||\r?\n|\\n))|"
    r"(?P<unquoted_value>[^\s'\";&|]+)"
    r"(?=[ \t]*(?:$|#|;|&&|\|\||\r?\n)))",
    re.IGNORECASE,
)
_KIS_NAME = re.compile(r"\bkis[_-]?(?:app[_-]?)?(?:key|secret)\b", re.IGNORECASE)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.exit(
            EXIT_ERROR,
            "secret scan error: invalid command-line arguments\n"
            "SECRET_SCAN_SUMMARY {\"files_scanned\": 0, \"findings\": 0}\n",
        )


@dataclass(frozen=True)
class Finding:
    """A safe finding that never contains the matched value or source line."""

    rule: str
    detail: str


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    return (
        normalized == ""
        or normalized in _PLACEHOLDER_WORDS
    )


def _assignment_value(match: re.Match[str]) -> str:
    return match.group("quoted_value") or match.group("unquoted_value") or ""


def _assignment_value_span(match: re.Match[str]) -> tuple[int, int]:
    if match.group("quoted_value") is not None:
        return match.span("quoted_value")
    return match.span("unquoted_value")


def _looks_like_nonliteral_reference(match: re.Match[str]) -> bool:
    """Return whether an unquoted assignment is source code, not a secret."""

    if match.group("quoted_value") is not None:
        return False
    value = _assignment_value(match).strip()
    return value in _NON_LITERAL_IDENTIFIERS or "." in value


def _is_standalone_unquoted_assignment(text: str, match: re.Match[str]) -> bool:
    if match.group("key_quote") or match.group("prefix"):
        return True
    line_start = text.rfind("\n", 0, match.start()) + 1
    prefix = text[line_start : match.start()]
    stripped = prefix.strip()
    if not stripped or stripped == "env":
        return True
    return bool(re.search(r"(?:^|;|&&|\|\|)[ \t]*$", prefix))


def _is_scannable_assignment(text: str, match: re.Match[str]) -> bool:
    if match.group("key_quote") and match.group("unquoted_value") is not None:
        return False
    if match.group("separator") == ":" and not _is_standalone_unquoted_assignment(text, match):
        return False
    return _is_standalone_unquoted_assignment(text, match)


def _has_ambiguous_unterminated_pem(text: str) -> bool:
    for header in _PEM_HEADER_RE.finditer(text):
        start = header.start()
        if (
            _PEM_COMPLETE.match(text, start)
            or _PEM_UNTERMINATED_JSON.match(text, start)
            or _PEM_UNTERMINATED_BLANK.match(text, start)
        ):
            continue
        if _PEM_AMBIGUOUS.match(text, start):
            return True
    return False


def scan_text(text: str) -> list[Finding]:
    """Return redacted findings for one text payload."""
    findings: list[Finding] = []
    if _PEM_HEADER_RE.search(text):
        findings.append(Finding("pem-private-key", "private-key material"))
    if _BEARER.search(text):
        findings.append(Finding("bearer-token", "bearer token"))

    for match in _ASSIGNMENT.finditer(text):
        if not _is_scannable_assignment(text, match):
            continue
        if _looks_like_nonliteral_reference(match):
            continue
        value = _assignment_value(match)
        if _looks_like_placeholder(value):
            continue
        rule = (
            "kis-credential"
            if _KIS_NAME.fullmatch(match.group("name"))
            else "credential-assignment"
        )
        if not any(finding.rule == rule for finding in findings):
            findings.append(Finding(rule, "credential-like assignment"))
    return findings


def redact_sensitive_text(text: str) -> str:
    """Replace detected credential values with ``[REDACTED]``.

    Non-secret text is returned unchanged. Explicit benign placeholders are
    preserved, while short non-placeholder credential values are redacted.
    If an unterminated PEM has an ambiguous multi-line fallback, this helper
    raises ``UnsafeRedactionError`` before returning any output. Callers must
    quarantine that event and must not persist or output the original text.
    """

    if _has_ambiguous_unterminated_pem(text):
        raise UnsafeRedactionError("ambiguous unterminated PEM requires quarantine")
    redacted = _PEM_COMPLETE.sub("[REDACTED_PRIVATE_KEY]", text)
    redacted = _PEM_UNTERMINATED_JSON.sub("[REDACTED_PRIVATE_KEY]", redacted)
    redacted = _PEM_UNTERMINATED_BLANK.sub("[REDACTED_PRIVATE_KEY]", redacted)
    redacted = _PEM_UNTERMINATED.sub("[REDACTED_PRIVATE_KEY]", redacted)
    redacted = _BEARER.sub("Bearer [REDACTED]", redacted)

    def replace_assignment(match: re.Match[str]) -> str:
        if not _is_scannable_assignment(match.string, match):
            return match.group(0)
        if _looks_like_nonliteral_reference(match):
            return match.group(0)
        if _looks_like_placeholder(_assignment_value(match)):
            return match.group(0)
        start, end = _assignment_value_span(match)
        return match.string[match.start() : start] + "[REDACTED]" + match.string[end : match.end()]

    return _ASSIGNMENT.sub(replace_assignment, redacted)


def tracked_files(root: Path) -> list[Path]:
    """Return only Git-tracked files below ``root``."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    names = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return [root / name for name in names if name]


def scan_repository(root: Path) -> tuple[int, list[tuple[str, Finding]]]:
    """Scan tracked worktree and index text, deduplicating path/rule findings."""
    findings: list[tuple[str, Finding]] = []
    files = tracked_files(root)
    for path in files:
        relative = path.relative_to(root).as_posix()
        sources: list[bytes] = []
        try:
            sources.append(path.read_bytes())
        except FileNotFoundError:
            pass
        index_data = subprocess.run(
            ["git", "cat-file", "blob", f":{relative}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        sources.append(index_data)
        for data in sources:
            if b"\0" in data:
                continue
            text = data.decode("utf-8", errors="replace")
            for finding in scan_text(text):
                item = (relative, finding)
                if item not in findings:
                    findings.append(item)
    return len(files), findings


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in raw_argv or "--help" in raw_argv:
        parser.print_help()
        print("SECRET_SCAN_SUMMARY {\"files_scanned\": 0, \"findings\": 0}")
        return EXIT_OK
    args = parser.parse_args(raw_argv)
    try:
        files_scanned, findings = scan_repository(args.root.resolve())
    except (OSError, UnicodeError, subprocess.CalledProcessError):
        print("secret scan error: unable to enumerate or read tracked files")
        print("SECRET_SCAN_SUMMARY " + json.dumps({"files_scanned": 0, "findings": 0}))
        return EXIT_ERROR
    for path, finding in findings:
        print(f"{path}: {finding.rule}")
    print(
        "SECRET_SCAN_SUMMARY "
        + json.dumps({"files_scanned": files_scanned, "findings": len(findings)}, sort_keys=True)
    )
    return EXIT_FINDINGS if findings else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
