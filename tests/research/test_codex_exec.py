from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from research.llm import codex_exec
from research.llm.codex_exec import CodexExecProvider, CodexExecResult
from research.llm.codex_schema import research_intent_schema


def _valid_intent() -> dict[str, object]:
    return {
        "mode": "structure",
        "parent_ids": ["champion-1"],
        "operations": [],
        "rationale": "test a momentum interaction",
    }


class FakeRunner:
    def __init__(
        self,
        payload: object,
        returncode: int = 0,
        stderr: str = "codex diagnostic must not leak",
    ) -> None:
        self.payload = payload
        self.returncode = returncode
        self.stderr = stderr
        self.calls = 0
        self.timeouts: list[float] = []
        self.command: list[str] = []
        self.input_text = ""
        self.cwd = Path()
        self.env: dict[str, str] = {}

    def __call__(
        self,
        command: list[str],
        input_text: str,
        cwd: Path,
        env: dict[str, str],
        timeout: float,
    ) -> CodexExecResult:
        self.timeouts.append(timeout)
        self.calls += 1
        self.command = command
        self.input_text = input_text
        self.cwd = cwd
        self.env = env
        output_path = Path(command[command.index("-o") + 1])
        output_path.write_text(json.dumps(self.payload), encoding="utf-8")
        return CodexExecResult(self.returncode, "", self.stderr)


def test_codex_exec_provider_uses_schema_and_redacts_child_environment(tmp_path: Path) -> None:
    runner = FakeRunner(_valid_intent())
    provider = CodexExecProvider(workdir=tmp_path, model="gpt-5.4-mini", runner=runner)
    context = {
        "generation": 3,
        "observations": [{"score": 0.8}],
        "raw_market_rows": [{"close": 100}],
        "sealed_oos": [{"return": 0.4}],
        "KIS_PAPER_APP_SECRET": "placeholder",
    }

    payload = provider.propose(context)

    assert payload == _valid_intent()
    assert runner.command[:3] == ["codex", "exec", "-m"]
    assert runner.command[2:4] == ["-m", "gpt-5.4-mini"]
    assert "--output-schema" in runner.command
    assert "--ephemeral" in runner.command
    assert "--sandbox" in runner.command
    assert runner.command[runner.command.index("-c") + 1] == 'service_tier="fast"'
    assert runner.env.get("KIS_PAPER_APP_SECRET") is None
    assert runner.env.get("OPENAI_API_KEY") is None
    assert runner.env.get("CODEX_API_KEY") is None
    sent = json.loads(runner.input_text)
    assert "raw_market_rows" not in sent["context"]
    assert "sealed_oos" not in sent["context"]
    assert "KIS_PAPER_APP_SECRET" not in sent["context"]
    assert sent["context"]["observations"] == [{"score": 0.8}]
    assert "canonical typed operation" in sent["instruction"]
    assert "never use json patch" in sent["instruction"].lower()
    assert "greater_than" in sent["instruction"]
    assert "indicators.<alias>" in sent["instruction"]
    assert "entry.conditions.<index>" in sent["instruction"]


def test_codex_exec_provider_compacts_repeated_feature_metadata(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(_valid_intent())
    provider = CodexExecProvider(workdir=tmp_path, runner=runner)
    context = {
        "generation": 5,
        "source_strategy": {"id": "golden_cross", "indicators": {"fast": {"period": 8}}},
        "feature_catalog": [
            {
                "name": "vix_percentile",
                "canonical_id": "vix_percentile",
                "aliases": ["vix_pct"],
                "family": "macro",
                "inputs": ["VIX.close"],
                "calculator": "percentile",
                "lookback": 20,
                "timeframe": "1d",
                "supported_timeframes": ["1d", "1w"],
                "lag_bars": 1,
                "parameters": {"window": 20},
                "implementation_hash": "hash-that-is-not-needed-for-a-proposal",
                "source_repositories": ["https://example.invalid/source"],
                "source_licenses": ["MIT"],
                "data_contract": "large repeated contract description",
                "status": "VERIFIED",
                "duplicate_group": "macro-vix",
            }
        ],
    }

    provider.propose(context)

    sent = json.loads(runner.input_text)
    feature = sent["context"]["feature_catalog"][0]
    assert feature == {
        "name": "vix_percentile",
        "canonical_id": "vix_percentile",
        "aliases": ["vix_pct"],
        "family": "macro",
        "inputs": ["VIX.close"],
        "calculator": "percentile",
        "lookback": 20,
        "timeframe": "1d",
        "supported_timeframes": ["1d", "1w"],
        "lag_bars": 1,
        "parameters": {"window": 20},
        "status": "VERIFIED",
    }
    assert len(json.dumps(sent["context"], ensure_ascii=False)) < len(
        json.dumps(context, ensure_ascii=False)
    )


def test_codex_exec_provider_caches_identical_requests(tmp_path: Path) -> None:
    runner = FakeRunner(_valid_intent())
    provider = CodexExecProvider(workdir=tmp_path, runner=runner)
    context = {"generation": 5, "source_strategy": {"id": "golden_cross"}}

    first = provider.propose(context)
    second = provider.propose(context)

    assert first == second == _valid_intent()
    assert runner.calls == 1


def test_codex_exec_provider_separates_proposal_and_repair_timeouts(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(_valid_intent())
    provider = CodexExecProvider(
        workdir=tmp_path,
        timeout_seconds=300,
        proposal_timeout_seconds=180,
        repair_timeout_seconds=45,
        runner=runner,
    )

    provider.propose({"generation": 1})
    provider.repair({}, {}, "invalid intent")

    assert runner.timeouts == [180, 45]


def test_codex_exec_provider_rejects_failed_or_invalid_output(tmp_path: Path) -> None:
    failed = FakeRunner(_valid_intent(), returncode=17, stderr="unsupported option: --sandbox")
    with pytest.raises(ValueError, match=r"Codex execution failed \(exit 17\): unsupported option"):
        CodexExecProvider(workdir=tmp_path, runner=failed).propose({})

    invalid = FakeRunner({"python_patch": "danger"})
    with pytest.raises(ValueError):
        CodexExecProvider(workdir=tmp_path, runner=invalid).propose({})


def test_codex_exec_provider_repairs_with_an_independent_request(tmp_path: Path) -> None:
    runner = FakeRunner(_valid_intent())
    provider = CodexExecProvider(workdir=tmp_path, runner=runner)

    payload = provider.repair(
        {"feature_catalog": [{"name": "rsi"}], "KIS_PAPER_APP_SECRET": "redacted"},
        {"mode": "mixed", "feature_proposal": {"name": "unsafe_feature"}},
        "feature proposal requires verification",
    )

    assert payload == _valid_intent()
    assert runner.command[:2] == ["codex", "exec"]
    assert "--ephemeral" in runner.command
    assert "--sandbox" in runner.command
    request = json.loads(runner.input_text)
    assert "independent intent repair" in request["instruction"].lower()
    assert request["repair_error"] == "feature proposal requires verification"
    assert "KIS_PAPER_APP_SECRET" not in json.dumps(request)
    assert "condition object" in request["instruction"]
    assert "never emit json patch" in request["instruction"].lower()
    assert "greater_than" in request["instruction"]
    assert "indicators.<alias>" in request["instruction"]


def test_codex_exec_provider_compacts_invalid_intent_for_repair(tmp_path: Path) -> None:
    runner = FakeRunner(_valid_intent())
    provider = CodexExecProvider(workdir=tmp_path, runner=runner)
    invalid_intent = {
        "mode": "structure",
        "parent_ids": ["golden_cross"],
        "operations": [],
        "rationale": "repair this proposal",
        "feature_selections": [],
        "feature_proposal": {"name": "vix_regime", "family": "macro"},
        "python_patch": "must not be sent to the repair agent",
        "evaluator_change": "must not be sent to the repair agent",
    }

    provider.repair({}, invalid_intent, "invalid target")

    request = json.loads(runner.input_text)
    sent_intent = request["invalid_intent"]
    assert sent_intent == {
        "mode": "structure",
        "parent_ids": ["golden_cross"],
        "operations": [],
        "rationale": "repair this proposal",
        "feature_selections": [],
        "feature_proposal": {"name": "vix_regime", "family": "macro"},
    }
    assert "python_patch" not in request["invalid_intent"]
    assert "evaluator_change" not in request["invalid_intent"]


def test_codex_exec_provider_marks_repair_as_active_and_completed(tmp_path: Path) -> None:
    runner = FakeRunner(_valid_intent())
    status_path = tmp_path / "state" / "llm" / "status.json"
    provider = CodexExecProvider(workdir=tmp_path, runner=runner, status_path=status_path)

    provider.repair({}, {}, "invalid intent")

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "ONLINE"
    assert status["last_result"] == "REPAIRED"
    assert status["operation"] == "repair"


def test_checked_in_schema_matches_model_schema() -> None:
    schema_path = Path(__file__).parents[2] / "schemas" / "research_intent.schema.json"
    assert json.loads(schema_path.read_text(encoding="utf-8")) == research_intent_schema()


def test_codex_exec_provider_records_non_secret_status(tmp_path: Path) -> None:
    runner = FakeRunner(_valid_intent())
    status_path = tmp_path / "state" / "llm" / "status.json"
    provider = CodexExecProvider(workdir=tmp_path, runner=runner, status_path=status_path)

    provider.propose({"generation": 1})

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["provider"] == "codex_exec"
    assert status["status"] == "ONLINE"
    assert status["last_result"] == "VALIDATED"
    assert "stderr" not in status


def test_codex_subprocess_decodes_utf8_output_on_windows(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> object:
        del args
        captured.update(kwargs)
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(codex_exec.sys, "platform", "linux")
    monkeypatch.setattr(codex_exec.subprocess, "run", fake_run)

    result = codex_exec._run_codex(["codex"], "{}", tmp_path, {}, 1.0)

    assert result.returncode == 0
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"


def test_codex_subprocess_reports_timeout(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise subprocess.TimeoutExpired(cmd=["codex"], timeout=120)

    monkeypatch.setattr(codex_exec.sys, "platform", "linux")
    monkeypatch.setattr(codex_exec.subprocess, "run", fake_run)

    result = codex_exec._run_codex(["codex"], "{}", tmp_path, {}, 120.0)

    assert result.returncode == 124
    assert "timed out after 120" in result.stderr


def test_codex_subprocess_timeout_kills_the_spawned_process_tree(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    class FakeProcess:
        pid = 4321
        returncode = 0

        def communicate(
            self, input: str | None = None, timeout: float | None = None
        ) -> tuple[str, str]:
            del input
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd=["codex"], timeout=1)
            return "", ""

    def fake_popen(*args: object, **kwargs: object) -> FakeProcess:
        del args, kwargs
        return FakeProcess()

    def fake_run(command: list[str], **kwargs: object) -> object:
        del kwargs
        calls.append(tuple(command))
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(codex_exec.sys, "platform", "win32")
    monkeypatch.setattr(codex_exec.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(codex_exec.subprocess, "run", fake_run)

    result = codex_exec._run_codex(["codex"], "{}", tmp_path, {}, 1.0)

    assert result.returncode == 124
    assert "timed out after 1" in result.stderr
    assert calls == [("taskkill", "/PID", "4321", "/T", "/F")]


def test_codex_subprocess_resolves_windows_executable(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_which(name: str, path: str | None = None) -> str | None:
        del path
        return r"C:\tools\codex.CMD" if name == "codex" else None

    class FakeProcess:
        returncode = 0

        def communicate(
            self, input: str | None = None, timeout: float | None = None
        ) -> tuple[str, str]:
            del input, timeout
            return "", ""

    def fake_popen(*args: object, **kwargs: object) -> FakeProcess:
        captured["args"] = args
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(codex_exec.sys, "platform", "win32")
    monkeypatch.setattr(codex_exec.shutil, "which", fake_which)
    monkeypatch.setattr(codex_exec.subprocess, "Popen", fake_popen)

    result = codex_exec._run_codex(["codex", "--version"], "", tmp_path, {"PATH": "x"}, 1.0)

    assert result.returncode == 0
    assert captured["args"] == ([r"C:\tools\codex.CMD", "--version"],)


def test_codex_exec_provider_uses_long_enough_default_timeout(tmp_path: Path) -> None:
    provider = CodexExecProvider(workdir=tmp_path)

    assert provider.timeout_seconds == 300.0
    assert provider.service_tier == "fast"
