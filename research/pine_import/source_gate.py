"""Fail-closed evidence gate for externally supplied TradingView Pine sources.

This module does not scrape TradingView, infer license terms, or translate code.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

VERSION = re.compile(r"(?m)^\s*//\s*@version\s*=\s*([3456])\s*$")
DECLARATION = re.compile(r"\b(strategy|indicator)\s*\(")
LICENSE = re.compile(
    r"(?im)(?:Mozilla Public License\s*2\.0|MPL[- ]2\.0|MIT License|"
    r"SPDX-License-Identifier:\s*(?:MPL-2\.0|MIT))"
)
UNSUPPORTED = {
    "orders": r"\bstrategy\.(?:order|exit|close|cancel|cancel_all|close_all)\s*\(",
    "multi_timeframe": r"\brequest\.security\s*\(|\bsecurity\s*\(",
    "repainting": r"\b(?:lookahead_on|pivothigh|pivotlow)\b",
    "realtime": r"\b(?:calc_on_every_tick|barstate\.)",
    "session": r"\b(?:session\.|time\s*\(|timestamp\s*\()",
    "pyramiding": r"\bpyramiding\s*=",
}


@dataclass(frozen=True)
class SourceAudit:
    sha256: str
    pine_version: str | None
    declaration: str | None
    license_header_detected: bool
    unsupported_features: tuple[str, ...]
    conversion_permitted: bool
    issues: tuple[str, ...]


def audit_pine_source(source: str, *, permission_confirmed: bool = False) -> SourceAudit:
    """Audit independently obtained exact source; never assume publish permission.

    permission_confirmed means the user's documented reuse assessment has passed,
    not merely that a page has an 'open-source' badge.
    """
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    version = VERSION.search(source)
    declaration = DECLARATION.search(source)
    has_license = bool(LICENSE.search("\n".join(source.splitlines()[:35])))
    features = tuple(name for name, pattern in UNSUPPORTED.items() if re.search(pattern, source))
    issues: list[str] = []
    if version is None:
        issues.append("PINE_VERSION_NOT_VERIFIED")
    if declaration is None or declaration.group(1) != "strategy":
        issues.append("NOT_A_PINE_STRATEGY")
    if not has_license:
        issues.append("LICENSE_HEADER_NOT_VERIFIED")
    if not permission_confirmed:
        issues.append("LICENSE_PERMISSION_UNCONFIRMED")
    if features:
        issues.append("UNSUPPORTED_EXECUTION_SEMANTICS")
    # Source capture alone is never sufficient to enable compilation/backtesting.
    issues.append("MANUAL_SEMANTIC_PARITY_REVIEW_REQUIRED")
    return SourceAudit(
        digest,
        version.group(1) if version else None,
        declaration.group(1) if declaration else None,
        has_license,
        features,
        False,
        tuple(issues),
    )
