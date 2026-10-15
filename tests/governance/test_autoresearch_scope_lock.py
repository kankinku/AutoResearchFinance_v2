"""Guard the original user interview and the approved development-scope mapping.

This test prevents accidental deletion/replacement of source requirements.
It does not infer consent for a future intentional change: that remains human
approval and a separate ADR.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERVIEW = ROOT / "docs/decisions/2026-10-14-autoresearch-interview-20q.md"
CHARTER = ROOT / "docs/decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md"
LEDGER = ROOT / "docs/operations/autoresearch-master-progress.md"
AGENT_CONTRACT = ROOT / "AGENTS.md"
ORIGINAL_INTERVIEW_SHA256 = (
    "ab41bbb68bf410ae9914c628d38915678472d5a906ee75e2cf2dae9ad8bfb801"
)


def test_original_20_user_answers_stay_byte_for_byte_unchanged() -> None:
    raw = INTERVIEW.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL_INTERVIEW_SHA256
    text = raw.decode("utf-8")
    rows = re.findall(r"^\|\s*(\d{1,2})\s*\|", text, re.MULTILINE)
    assert [int(number) for number in rows] == list(range(1, 21))


def test_scope_charter_tracks_all_original_answers_and_three_phases() -> None:
    text = CHARTER.read_text(encoding="utf-8")
    matches = re.findall(r"^\|\s*(Q\d{2})\s*\|", text, re.MULTILINE)
    assert matches == [f"Q{i:02d}" for i in range(1, 21)]
    assert "USER_CONFIRMED_SCOPE_LOCK" in text
    assert ORIGINAL_INTERVIEW_SHA256 in text
    assert "예상 순수익" in text
    assert "3단계 독립 성공 기준" in text
    assert "사용자 명시 승인" in text
    assert "실주문" in text


def test_confirmed_remaining_work_has_no_unapproved_reordering() -> None:
    text = CHARTER.read_text(encoding="utf-8")
    frozen = text.split("## 3. 사용자 확정 잔여 작업 순서", 1)[1].split(
        "## 4. 변경 통제", 1
    )[0]
    tasks = re.findall(r"^\|\s*([1-5])\s*\|", frozen, re.MULTILINE)
    assert tasks == list("12345")
    offsets = [frozen.index(stage) for stage in ("V05", "T4", "V01~V04", "V06", "V07")]
    assert offsets == sorted(offsets)
    assert "Q19" in text and "S0~S10" in text
    assert "SCOPE_DRIFT" in text
    assert "BLOCKED" in text


def test_repo_agents_and_ledger_point_to_locked_scope() -> None:
    agent = AGENT_CONTRACT.read_text(encoding="utf-8")
    ledger = LEDGER.read_text(encoding="utf-8")
    for document in (agent, ledger):
        assert INTERVIEW.name in document
        assert CHARTER.name in document
    assert "explicit user approval" in agent
    assert "V05" in ledger and "T4" in ledger
    assert all(f"| {part} |" in ledger for part in (
        "1-1", "1-2", "1-3", "2-1", "2-2", "2-3",
        "3-1", "3-2", "3-3", "4-1", "4-2", "4-3",
        "5-1", "5-2", "5-3",
    ))
    assert all(f"| T{i} |" in ledger for i in range(7))
