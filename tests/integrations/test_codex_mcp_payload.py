from __future__ import annotations

import json
from pathlib import Path

from integrations.codex_mcp_protocol import text_content

ROOT = Path(__file__).resolve().parents[2]


def test_phase6_2_neutral_payload_codec_preserves_wire_text_semantics() -> None:
    from integrations.codex_mcp_payload import encode_tool_payload, text_content_payload

    payload = {"z": "한글", "a": {"enabled": False}}

    encoded = encode_tool_payload(payload)
    assert encoded == json.dumps(payload, ensure_ascii=True, sort_keys=True)
    assert text_content_payload(payload) == [{"type": "text", "text": encoded}]
    assert text_content(payload) == [{"type": "text", "text": encoded}]


def test_phase6_2_sdk_does_not_import_legacy_protocol_module() -> None:
    sdk_source = (ROOT / "integrations" / "codex_mcp_sdk_server.py").read_text(
        encoding="utf-8"
    )
    protocol_source = (ROOT / "integrations" / "codex_mcp_protocol.py").read_text(
        encoding="utf-8"
    )

    assert "codex_mcp_protocol" not in sdk_source
    assert "from integrations.codex_mcp_payload import" in sdk_source
    assert "from integrations.codex_mcp_payload import" in protocol_source


def test_phase6_2_manual_protocol_reuses_neutral_payload_codec() -> None:
    protocol_source = (ROOT / "integrations" / "codex_mcp_protocol.py").read_text(
        encoding="utf-8"
    )

    assert "def text_content(" in protocol_source
    assert "text_content_payload(payload)" in protocol_source
    assert "json.dumps(payload, ensure_ascii=True, sort_keys=True)" not in protocol_source
