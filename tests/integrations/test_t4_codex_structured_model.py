"""T4 Codex decisions remain opt-in, schema-checked, and untrusted as proof."""

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from application.t4_codex_structured_model import (
    CodexDecisionBlocked,
    CodexStructuredDecisionHost,
)

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["mode", "rationale"],
    "properties": {
        "mode": {"enum": ["structure", "parameter"]},
        "rationale": {"type": "string", "minLength": 1},
    },
}

def usage(total=110):
    return SimpleNamespace(
        total=SimpleNamespace(
            input_tokens=70, output_tokens=40,
            cached_input_tokens=0, total_tokens=total,
        )
    )

@dataclass
class Turn:
    id: str = "turn_mock_01"
    status: str = "completed"
    final_response: str = '{"mode":"structure","rationale":"Testable thesis"}'
    usage: object = None

class FakeThread:
    id = "thread_mock_01"
    def __init__(self, result: Turn):
        self.result = result
        self.calls = 0
        self.last = None
    def run(self, prompt, **kwargs):
        self.calls += 1
        self.last = (prompt, kwargs)
        return self.result

class FakeCodex:
    def __init__(self, account=True, response=None):
        self.account_present = account
        self.model_started = 0
        self.logins = 0
        self.thread = FakeThread(response or Turn(usage=usage()))
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        pass
    def account(self):
        return SimpleNamespace(root=SimpleNamespace(
            account=object() if self.account_present else None))
    def thread_start(self, **kwargs):
        self.model_started += 1
        self.thread_start_kwargs = kwargs
        return self.thread
    def login_chatgpt(self):
        self.logins += 1
        raise AssertionError("No login from adapter")

def host(tmp_path: Path, codex):
    return CodexStructuredDecisionHost(
        project_root=tmp_path,
        codex_factory=lambda: codex,
    )

def test_no_authorization_no_model_call(tmp_path):
    client = FakeCodex()
    with pytest.raises(CodexDecisionBlocked, match="opt-in"):
        host(tmp_path, client).propose(
            stage="plan", model_context={"generation": 1},
            output_schema=SCHEMA,
        )
    assert client.model_started == 0 and client.thread.calls == 0

def test_missing_auth_blocks_before_thread_start(tmp_path):
    client = FakeCodex(account=False)
    with pytest.raises(CodexDecisionBlocked, match="not connected"):
        host(tmp_path, client).propose(
            stage="plan", model_context={"generation": 1},
            output_schema=SCHEMA, enable_model_call=True,
        )
    assert client.model_started == 0 and client.logins == 0

def test_valid_stub_response_has_unverified_provenance_and_usage(tmp_path):
    client = FakeCodex()
    d = host(tmp_path, client).propose(
        stage="plan", model_context={"generation": 1},
        output_schema=SCHEMA, enable_model_call=True,
    )
    assert d["decision"] == {"mode": "structure", "rationale": "Testable thesis"}
    assert d["metadata"]["turn_id"] == "turn_mock_01"
    assert d["metadata"]["thread_id"] == "thread_mock_01"
    assert d["metadata"]["token_usage"]["total_tokens"] == 110
    assert d["metadata"]["provider_signed_receipt_verified"] is False
    assert d["metadata"]["independent_model_invocation_verified"] is False
    assert d["metadata"]["auth_provenance"] == "UNVERIFIED_LOCAL_SDK_METADATA"
    assert d["metadata"]["output_hash"].startswith("sha256:")
    assert d["metadata"]["context_hash"].startswith("sha256:")
    assert client.thread.calls == 1 and client.model_started == 1
    assert client.thread.last[1]["output_schema"] == SCHEMA
    assert str(client.thread_start_kwargs["sandbox"]).endswith("read_only")
    assert client.thread_start_kwargs["ephemeral"] is True
    assert "secret" not in str(d).lower()

@pytest.mark.parametrize("result", [
    Turn(status="failed",usage=usage()),
    Turn(status="interrupted",usage=usage()),
    Turn(final_response="not json",usage=usage()),
    Turn(final_response='{"unknown":"field"}',usage=usage()),
    Turn(final_response='{"mode":"structure","rationale":"ok"}',usage=None),
    Turn(final_response='{"mode":"structure","rationale":"ok"}',usage=usage(0)),
])
def test_fail_closed_without_resubmission(tmp_path, result):
    client = FakeCodex(response=result)
    with pytest.raises(CodexDecisionBlocked):
        host(tmp_path, client).propose(
            stage="diagnosis", model_context={"generation": 1},
            output_schema=SCHEMA, enable_model_call=True,
        )
    assert client.thread.calls == 1
    assert client.logins == 0

def test_reject_unknown_stage_and_empty_schema(tmp_path):
    client = FakeCodex()
    with pytest.raises(CodexDecisionBlocked):
        host(tmp_path, client).propose(
            stage="execute_code", model_context={}, output_schema=SCHEMA,
            enable_model_call=True,
        )
    with pytest.raises(CodexDecisionBlocked):
        host(tmp_path, client).propose(
            stage="plan", model_context={}, output_schema={},
            enable_model_call=True,
        )
    assert client.model_started == 0

def test_project_root_is_distinct_and_read_only(tmp_path):
    client = FakeCodex()
    with pytest.raises(ValueError,match="existing"):
        CodexStructuredDecisionHost(project_root=tmp_path/"missing",codex_factory=lambda:client)


def test_existing_p5_state_cannot_be_model_workspace(tmp_path):
    (tmp_path / "p5_session_id.txt").write_text("do not use original P5")
    with pytest.raises(ValueError, match="research state"):
        CodexStructuredDecisionHost(project_root=tmp_path)
