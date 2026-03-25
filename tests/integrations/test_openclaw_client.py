from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def make_success_response(
    *,
    task_kind: str,
    idempotency_key: str,
    artifact: dict[str, object],
) -> dict[str, object]:
    return {
        "ok": True,
        "task_kind": task_kind,
        "idempotency_key": idempotency_key,
        "artifact": artifact,
        "error_type": None,
        "message": "ok",
        "retryable": False,
    }


def make_schema_failure_response(
    *,
    task_kind: str,
    idempotency_key: str,
) -> dict[str, object]:
    return {
        "ok": False,
        "task_kind": task_kind,
        "idempotency_key": idempotency_key,
        "artifact": None,
        "error_type": "schema",
        "message": "schema failure",
        "retryable": False,
    }


def make_mutation_artifact() -> dict[str, object]:
    return {
        "kind": "strategy_replacement",
        "target_path": "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
        "hypothesis": "Add a volatility filter.",
        "change_summary": "Added ATR filter to long entries.",
        "full_file_contents": "from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition\n\n\ndef build_strategy(context: StrategyContext) -> StrategyDefinition:\n    raise NotImplementedError\n",
        "expected_effects": ["Fewer trades in choppy markets."],
    }


def make_analysis_artifact() -> dict[str, object]:
    return {
        "strengths": ["Bull regime improved."],
        "weaknesses": ["Bear drawdown still high."],
        "coverage_gaps": ["Needs chop filter."],
        "regime_observations": ["Bull exposure increased."],
        "next_hypothesis_hints": ["Tighten bear exits."],
        "summary": "Bull improved but bear remains weak.",
    }


def test_candidate_workspace_round_trip_writes_request_and_reads_response(
    tmp_path: Path,
) -> None:
    from finance_autoresearch.mutation.candidate_workspace import CandidateWorkspace
    from finance_autoresearch.mutation.prompt_builder import build_mutation_request

    workspace = CandidateWorkspace.create(
        base_dir=tmp_path,
        task_kind="mutation",
        run_id="run-001",
        iteration=7,
        stage="mutate_strategy",
    )
    request = build_mutation_request(
        run_id="run-001",
        iteration=7,
        stage="mutate_strategy",
        agent_id="research",
        context={"baseline_score": 1.2},
    )

    workspace.write_request(request)
    workspace.response_path.write_text(
        json.dumps(
            make_success_response(
                task_kind="mutation",
                idempotency_key=request.idempotency_key,
                artifact=make_mutation_artifact(),
            )
        ),
        encoding="utf-8",
    )

    assert workspace.request_path.exists()
    assert workspace.read_response()["artifact"]["kind"] == "strategy_replacement"


def test_prompt_builder_builds_expected_envelopes() -> None:
    from finance_autoresearch.mutation.prompt_builder import (
        build_analysis_request,
        build_mutation_request,
    )

    mutation_request = build_mutation_request(
        run_id="run-001",
        iteration=7,
        stage="mutate_strategy",
        agent_id="research",
        context={"baseline_score": 1.2},
    )
    analysis_request = build_analysis_request(
        run_id="run-001",
        iteration=7,
        stage="analyze_candidate",
        agent_id="critic",
        context={"candidate_score": 1.4},
    )

    assert mutation_request.task_kind == "mutation"
    assert mutation_request.expected_schema == "strategy_replacement"
    assert mutation_request.idempotency_key == "run-001:7:mutate_strategy"
    assert mutation_request.target_path == (
        "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"
    )
    assert analysis_request.task_kind == "analysis"
    assert analysis_request.expected_schema == "analysis_artifact"
    assert analysis_request.idempotency_key == "run-001:7:analyze_candidate"
    assert analysis_request.target_path is None


def test_openclaw_client_retries_transport_failure_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finance_autoresearch.mutation.openclaw_client import OpenClawClient
    from finance_autoresearch.mutation.prompt_builder import build_mutation_request

    calls: list[list[str]] = []
    sleeps: list[float] = []
    request = build_mutation_request(
        run_id="run-001",
        iteration=7,
        stage="mutate_strategy",
        agent_id="research",
        context={"baseline_score": 1.2},
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        timeout: int,
        cwd: Path | None,
        capture_output: bool,
        env: dict[str, str] | None,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        response_path = Path(command[-1])
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 1, "", "transport failure")
        response_path.write_text(
            json.dumps(
                make_success_response(
                    task_kind="mutation",
                    idempotency_key=request.idempotency_key,
                    artifact=make_mutation_artifact(),
                )
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "finance_autoresearch.mutation.openclaw_client.subprocess.run",
        fake_run,
    )

    client = OpenClawClient(
        mutate_script=tmp_path / "openclaw-mutate.ps1",
        analyze_script=tmp_path / "openclaw-analyze.ps1",
        sleep_fn=sleeps.append,
        workspace_root=tmp_path,
    )

    response = client.invoke(request)

    assert response.ok is True
    assert response.artifact is not None
    assert len(calls) == 2
    assert sleeps == [2.0]


def test_openclaw_client_retries_timeout_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finance_autoresearch.mutation.openclaw_client import OpenClawClient
    from finance_autoresearch.mutation.prompt_builder import build_analysis_request

    calls: list[list[str]] = []
    sleeps: list[float] = []
    request = build_analysis_request(
        run_id="run-001",
        iteration=7,
        stage="analyze_candidate",
        agent_id="critic",
        context={"candidate_score": 1.4},
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        timeout: int,
        cwd: Path | None,
        capture_output: bool,
        env: dict[str, str] | None,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, timeout)
        response_path = Path(command[-1])
        response_path.write_text(
            json.dumps(
                make_success_response(
                    task_kind="analysis",
                    idempotency_key=request.idempotency_key,
                    artifact=make_analysis_artifact(),
                )
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "finance_autoresearch.mutation.openclaw_client.subprocess.run",
        fake_run,
    )

    client = OpenClawClient(
        mutate_script=tmp_path / "openclaw-mutate.ps1",
        analyze_script=tmp_path / "openclaw-analyze.ps1",
        sleep_fn=sleeps.append,
        workspace_root=tmp_path,
    )

    response = client.invoke(request)

    assert response.ok is True
    assert response.artifact is not None
    assert len(calls) == 2
    assert sleeps == [2.0]


def test_openclaw_client_does_not_retry_schema_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finance_autoresearch.mutation.openclaw_client import OpenClawClient
    from finance_autoresearch.mutation.prompt_builder import build_analysis_request

    calls: list[list[str]] = []
    sleeps: list[float] = []
    request = build_analysis_request(
        run_id="run-001",
        iteration=7,
        stage="analyze_candidate",
        agent_id="critic",
        context={"candidate_score": 1.4},
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        timeout: int,
        cwd: Path | None,
        capture_output: bool,
        env: dict[str, str] | None,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        response_path = Path(command[-1])
        response_path.write_text(
            json.dumps(
                make_schema_failure_response(
                    task_kind="analysis",
                    idempotency_key=request.idempotency_key,
                )
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "finance_autoresearch.mutation.openclaw_client.subprocess.run",
        fake_run,
    )

    client = OpenClawClient(
        mutate_script=tmp_path / "openclaw-mutate.ps1",
        analyze_script=tmp_path / "openclaw-analyze.ps1",
        sleep_fn=sleeps.append,
        workspace_root=tmp_path,
    )

    response = client.invoke(request)

    assert response.ok is False
    assert response.error_type == "schema"
    assert len(calls) == 1
    assert sleeps == []


def test_openclaw_client_preserves_idempotency_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finance_autoresearch.mutation.openclaw_client import OpenClawClient
    from finance_autoresearch.mutation.prompt_builder import build_mutation_request

    request = build_mutation_request(
        run_id="run-001",
        iteration=7,
        stage="mutate_strategy",
        agent_id="research",
        context={"baseline_score": 1.2},
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        timeout: int,
        cwd: Path | None,
        capture_output: bool,
        env: dict[str, str] | None,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        response_path = Path(command[-1])
        response_path.write_text(
            json.dumps(
                make_success_response(
                    task_kind="mutation",
                    idempotency_key=request.idempotency_key,
                    artifact=make_mutation_artifact(),
                )
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "finance_autoresearch.mutation.openclaw_client.subprocess.run",
        fake_run,
    )

    client = OpenClawClient(
        mutate_script=tmp_path / "openclaw-mutate.ps1",
        analyze_script=tmp_path / "openclaw-analyze.ps1",
        workspace_root=tmp_path,
    )

    response = client.invoke(request)

    assert response.idempotency_key == request.idempotency_key


def test_openclaw_client_passes_wrapper_env_to_subprocesses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finance_autoresearch.mutation.openclaw_client import OpenClawClient
    from finance_autoresearch.mutation.prompt_builder import build_analysis_request

    seen_envs: list[dict[str, str] | None] = []
    request = build_analysis_request(
        run_id="run-001",
        iteration=7,
        stage="analyze_candidate",
        agent_id="critic",
        context={"candidate_score": 1.4},
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        timeout: int | None = None,
        cwd: Path | None,
        capture_output: bool,
        env: dict[str, str] | None,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        seen_envs.append(env)
        if "-RolesPath" in command:
            return subprocess.CompletedProcess(command, 0, "ok", "")
        response_path = Path(command[-1])
        response_path.write_text(
            json.dumps(
                make_success_response(
                    task_kind="analysis",
                    idempotency_key=request.idempotency_key,
                    artifact=make_analysis_artifact(),
                )
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "finance_autoresearch.mutation.openclaw_client.subprocess.run",
        fake_run,
    )

    client = OpenClawClient(
        mutate_script=tmp_path / "openclaw-mutate.ps1",
        analyze_script=tmp_path / "openclaw-analyze.ps1",
        healthcheck_script=tmp_path / "check-openclaw.ps1",
        workspace_root=tmp_path,
        wrapper_env={
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH": "C:/mutate.ps1",
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH": "C:/analyze.ps1",
        },
    )

    health = client.check_health(roles_path=tmp_path / "roles.yaml", gateway_url=None)
    response = client.invoke(request)

    assert health.ok is True
    assert response.ok is True
    assert len(seen_envs) == 2
    assert seen_envs[0] is not None
    assert seen_envs[1] is not None
    assert (
        seen_envs[0]["FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH"]
        == "C:/mutate.ps1"
    )
    assert (
        seen_envs[1]["FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH"]
        == "C:/analyze.ps1"
    )
