from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from strategy_import.models import GitHubSource, SourceFile


class SourceSecurityError(ValueError):
    """Raised when an external source violates the import boundary."""


_ALLOWED_SUFFIXES = frozenset({".py", ".yaml", ".yml", ".json", ".pine", ".pinescript"})
_BLOCKED_NAMES = frozenset({".env", ".env.local", ".env.production", "credentials", "secrets"})
_BLOCKED_PARTS = frozenset({"raw_sources", "source_dumps", ".git"})
_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/@+-]{1,200}$")


def parse_github_source(url: str, *, ref: str) -> GitHubSource:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise SourceSecurityError("GitHub source must use an https github.com URL")
    if parsed.username or parsed.password or not parsed.path.strip("/"):
        raise SourceSecurityError("GitHub source URL contains invalid credentials or path")
    if not _REF_PATTERN.fullmatch(ref):
        raise SourceSecurityError("GitHub ref contains unsupported characters")
    return GitHubSource(repository_url=url.strip(), ref=ref)


def iter_safe_source_files(root: Path) -> list[SourceFile]:
    root = root.resolve()
    files: list[SourceFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _ALLOWED_SUFFIXES:
            continue
        relative = path.relative_to(root)
        parts = {part.lower() for part in relative.parts}
        if path.name.lower() in _BLOCKED_NAMES or parts.intersection(_BLOCKED_PARTS):
            continue
        content = path.read_text(encoding="utf-8")
        files.append(
            SourceFile(
                path=path,
                relative_path=relative,
                content=content,
                source_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )
    return files


class CloneManager:
    """Clone a repository into a private temporary directory without executing its code."""

    def clone(self, source: GitHubSource) -> tuple[Path, str]:
        target = Path(tempfile.mkdtemp(prefix="quant-strategy-source-"))
        try:
            completed = subprocess.run(
                [
                    "git",
                    "clone",
                    "--no-checkout",
                    "--filter=blob:none",
                    source.repository_url,
                    str(target),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            del completed
            subprocess.run(
                ["git", "-C", str(target), "checkout", "--detach", source.ref],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            commit = subprocess.run(
                ["git", "-C", str(target), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            ).stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise SourceSecurityError("clone did not resolve to a commit")
            return target, commit
        except (OSError, subprocess.SubprocessError) as exc:
            raise SourceSecurityError("GitHub clone failed") from exc
