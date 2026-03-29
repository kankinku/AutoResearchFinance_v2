from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .candidate_workspace import CandidateWorkspace
from .prompt_builder import (
    ExpectedSchema,
    OpenClawRequest,
    build_analysis_request,
    build_mutation_request,
)


ErrorType = Literal["transport", "schema", "model", "timeout"]

_REQUIRED_RESPONSE_KEYS = {
    "ok",
    "task_kind",
    "idempotency_key",
    "artifact",
    "error_type",
    "message",
    "retryable",
}
_REQUIRED_MUTATION_KEYS = {
    "kind",
    "target_path",
    "hypothesis",
    "change_summary",
    "full_file_contents",
    "expected_effects",
}
_REQUIRED_GENOME_KEYS = {
    "kind",
    "target_path",
    "hypothesis",
    "change_summary",
    "expected_effects",
    "family_id",
    "rationale",
    "regime_policy",
    "indicator_specs",
    "entry_clauses",
    "exit_clauses",
    "risk_clauses",
    "params",
}
_REQUIRED_ANALYSIS_KEYS = {
    "strengths",
    "weaknesses",
    "coverage_gaps",
    "regime_observations",
    "next_hypothesis_hints",
    "summary",
}
_RETRYABLE_ERROR_TYPES = {"transport", "timeout"}


@dataclass(slots=True, frozen=True)
class OpenClawResponse:
    ok: bool
    task_kind: str
    idempotency_key: str
    artifact: dict[str, Any] | None
    stage: str
    error_type: ErrorType | None
    error_code: str | None
    message: str
    retryable: bool


@dataclass(slots=True, frozen=True)
class HealthCheckResult:
    ok: bool
    message: str


class OpenClawClient:
    def __init__(
        self,
        *,
        mutate_script: Path | str,
        analyze_script: Path | str,
        healthcheck_script: Path | str | None = None,
        sleep_fn=time.sleep,
        workspace_root: Path | str | None = None,
        wrapper_env: dict[str, str] | None = None,
    ) -> None:
        self._mutate_script = Path(mutate_script)
        self._analyze_script = Path(analyze_script)
        self._healthcheck_script = (
            Path(healthcheck_script) if healthcheck_script is not None else None
        )
        self._sleep_fn = sleep_fn
        self._workspace_root = Path(workspace_root) if workspace_root is not None else None
        self._wrapper_env = dict(wrapper_env) if wrapper_env is not None else None

    def mutate(
        self,
        *,
        run_id: str,
        iteration: int,
        stage: str,
        agent_id: str,
        context: dict[str, Any],
    ) -> OpenClawResponse:
        return self.invoke(
            build_mutation_request(
                run_id=run_id,
                iteration=iteration,
                stage=stage,
                agent_id=agent_id,
                context=context,
            )
        )

    def analyze(
        self,
        *,
        run_id: str,
        iteration: int,
        stage: str,
        agent_id: str,
        context: dict[str, Any],
    ) -> OpenClawResponse:
        return self.invoke(
            build_analysis_request(
                run_id=run_id,
                iteration=iteration,
                stage=stage,
                agent_id=agent_id,
                context=context,
            )
        )

    def invoke(self, request: OpenClawRequest) -> OpenClawResponse:
        last_response: OpenClawResponse | None = None
        for attempt in range(2):
            response = self._invoke_once(request)
            last_response = response
            if not self._should_retry(response, attempt):
                return response
            self._sleep_fn(2.0)

        if last_response is None:
            raise RuntimeError("OpenClaw client did not produce a response")
        return last_response

    def check_health(
        self,
        *,
        roles_path: Path | str,
        gateway_url: str | None = None,
    ) -> HealthCheckResult:
        if self._healthcheck_script is None:
            raise ValueError("healthcheck script is not configured")

        command = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self._healthcheck_script),
            "-RolesPath",
            str(Path(roles_path)),
        ]
        if gateway_url:
            command.extend(["-GatewayUrl", gateway_url])

        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            cwd=self._healthcheck_script.parent,
            env=self._wrapper_env,
            text=True,
        )
        message = (result.stdout or result.stderr).strip()
        return HealthCheckResult(ok=result.returncode == 0, message=message)

    def _invoke_once(self, request: OpenClawRequest) -> OpenClawResponse:
        workspace = CandidateWorkspace.create(
            base_dir=self._workspace_root,
            task_kind=request.task_kind,
            run_id=request.run_id,
            iteration=request.iteration,
            stage=request.stage,
        )
        workspace.reset_transport_files()
        workspace.write_request(request)
        command = self._build_command(request=request, workspace=workspace)

        try:
            result = subprocess.run(
                command,
                check=False,
                timeout=self._timeout_seconds_for(request.task_kind),
                cwd=self._script_for(request.task_kind).parent,
                capture_output=True,
                env=self._wrapper_env,
                text=True,
            )
        except subprocess.TimeoutExpired:
            return self._failure(
                request=request,
                error_type="timeout",
                error_code="wrapper_timeout",
                message="wrapper timed out before producing a response envelope",
                retryable=True,
            )
        except OSError as exc:
            return self._failure(
                request=request,
                error_type="transport",
                error_code="wrapper_launch_failed",
                message=f"failed to launch wrapper process: {exc}",
                retryable=True,
            )

        if result.returncode != 0:
            return self._failure(
                request=request,
                error_type="transport",
                error_code="wrapper_nonzero_exit",
                message=self._build_process_failure_message(result=result),
                retryable=True,
            )

        try:
            payload = workspace.read_response()
        except FileNotFoundError:
            return self._failure(
                request=request,
                error_type="transport",
                error_code="wrapper_response_missing",
                message="wrapper response envelope was not created",
                retryable=True,
            )
        except ValueError as exc:
            return self._failure(
                request=request,
                error_type="transport",
                error_code="wrapper_response_malformed",
                message=str(exc),
                retryable=True,
            )

        return self._validate_response(request=request, payload=payload)

    def _build_command(
        self,
        *,
        request: OpenClawRequest,
        workspace: CandidateWorkspace,
    ) -> list[str]:
        script = self._script_for(request.task_kind)
        return [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-AgentId",
            request.agent_id,
            "-RequestJson",
            str(workspace.request_path),
            "-ResponseJson",
            str(workspace.response_path),
        ]

    def _script_for(self, task_kind: str) -> Path:
        if task_kind == "mutation":
            return self._mutate_script
        return self._analyze_script

    def _timeout_seconds_for(self, task_kind: str) -> int:
        if task_kind == "mutation":
            return 180
        return 120

    def _should_retry(self, response: OpenClawResponse, attempt: int) -> bool:
        return (
            attempt == 0
            and response.error_type in _RETRYABLE_ERROR_TYPES
            and response.retryable
        )

    def _validate_response(
        self,
        *,
        request: OpenClawRequest,
        payload: dict[str, Any],
    ) -> OpenClawResponse:
        if not _REQUIRED_RESPONSE_KEYS.issubset(payload):
            return self._schema_failure(
                request=request,
                message="wrapper response envelope shape is invalid",
            )
        if not isinstance(payload["idempotency_key"], str) or not isinstance(
            payload["task_kind"], str
        ):
            return self._schema_failure(
                request=request,
                message="wrapper response idempotency_key and task_kind must be strings",
            )

        if payload["task_kind"] != request.task_kind:
            return self._schema_failure(
                request=request,
                message="wrapper response task_kind does not match request",
            )
        if payload["idempotency_key"] != request.idempotency_key:
            return self._schema_failure(
                request=request,
                message="wrapper response idempotency_key does not match request",
            )

        if bool(payload["ok"]):
            artifact = payload["artifact"]
            if not isinstance(artifact, dict):
                return self._schema_failure(
                    request=request,
                    message="wrapper response artifact must be an object",
                )
            artifact_error = self._validate_artifact_schema(
                artifact=artifact,
                expected_schema=request.expected_schema,
            )
            if artifact_error is not None:
                return self._schema_failure(request=request, message=artifact_error)
            return OpenClawResponse(
                ok=True,
                task_kind=request.task_kind,
                idempotency_key=request.idempotency_key,
                artifact=artifact,
                stage=request.stage,
                error_type=None,
                error_code=None,
                message=str(payload["message"]),
                retryable=False,
            )

        error_type = payload["error_type"]
        message = str(payload["message"])
        retryable = bool(payload["retryable"])
        if error_type not in {"transport", "schema", "model", "timeout"}:
            return self._schema_failure(
                request=request,
                message="wrapper response error_type is invalid",
            )
        if error_type == "schema":
            retryable = False
        return OpenClawResponse(
            ok=False,
            task_kind=request.task_kind,
            idempotency_key=request.idempotency_key,
            artifact=None,
            error_type=error_type,
            stage=request.stage,
            error_code=f"wrapper_reported_{error_type}",
            message=message,
            retryable=retryable,
        )

    def _validate_artifact_schema(
        self,
        *,
        artifact: dict[str, Any],
        expected_schema: ExpectedSchema,
    ) -> str | None:
        if expected_schema == "mutation_artifact":
            kind = artifact.get("kind")
            if kind == "strategy_replacement":
                if not _REQUIRED_MUTATION_KEYS.issubset(artifact):
                    return "mutation artifact does not match the strategy_replacement schema"
                if not all(
                    isinstance(artifact.get(key), str)
                    for key in (
                        "target_path",
                        "hypothesis",
                        "change_summary",
                        "full_file_contents",
                    )
                ):
                    return "mutation artifact text fields must be strings"
                effects = artifact.get("expected_effects")
                if not isinstance(effects, list) or any(
                    not isinstance(effect, str) for effect in effects
                ):
                    return "mutation artifact expected_effects must be a list of strings"
                return None
            if kind == "strategy_genome_v1":
                if not _REQUIRED_GENOME_KEYS.issubset(artifact):
                    return "mutation artifact does not match the strategy_genome_v1 schema"
                for key in (
                    "target_path",
                    "hypothesis",
                    "change_summary",
                    "family_id",
                    "rationale",
                    "regime_policy",
                ):
                    if not isinstance(artifact.get(key), str):
                        return f"mutation artifact {key} must be a string"
                effects = artifact.get("expected_effects")
                if not isinstance(effects, list) or any(
                    not isinstance(effect, str) for effect in effects
                ):
                    return "mutation artifact expected_effects must be a list of strings"
                for key in ("indicator_specs", "entry_clauses", "exit_clauses", "risk_clauses"):
                    value = artifact.get(key)
                    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                        return f"mutation artifact {key} must be a list of objects"
                if not isinstance(artifact.get("params"), dict):
                    return "mutation artifact params must be an object"
                shadow_raw = artifact.get("shadow_strategy_replacement")
                if shadow_raw is not None:
                    if not isinstance(shadow_raw, dict):
                        return "mutation artifact shadow_strategy_replacement must be an object"
                    shadow_error = self._validate_artifact_schema(
                        artifact=shadow_raw,
                        expected_schema="mutation_artifact",
                    )
                    if shadow_error is not None:
                        return shadow_error
                return None
            return "mutation artifact kind must be strategy_replacement or strategy_genome_v1"

        if not _REQUIRED_ANALYSIS_KEYS.issubset(artifact):
            return "analysis artifact does not match the analysis schema"
        for list_key in (
            "strengths",
            "weaknesses",
            "coverage_gaps",
            "regime_observations",
            "next_hypothesis_hints",
        ):
            value = artifact.get(list_key)
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                return f"analysis artifact {list_key} must be a list of strings"
        if not isinstance(artifact.get("summary"), str):
            return "analysis artifact summary must be a string"
        return None

    def _schema_failure(
        self,
        *,
        request: OpenClawRequest,
        message: str,
    ) -> OpenClawResponse:
        return OpenClawResponse(
            ok=False,
            task_kind=request.task_kind,
            idempotency_key=request.idempotency_key,
            artifact=None,
            error_type="schema",
            stage=request.stage,
            error_code="wrapper_schema_invalid",
            message=message,
            retryable=False,
        )

    def _failure(
        self,
        *,
        request: OpenClawRequest,
        error_type: ErrorType,
        error_code: str,
        message: str,
        retryable: bool,
    ) -> OpenClawResponse:
        return OpenClawResponse(
            ok=False,
            task_kind=request.task_kind,
            idempotency_key=request.idempotency_key,
            artifact=None,
            stage=request.stage,
            error_type=error_type,
            error_code=error_code,
            message=message,
            retryable=retryable,
        )

    def _build_process_failure_message(
        self,
        *,
        result: subprocess.CompletedProcess[str],
    ) -> str:
        detail = (result.stderr or result.stdout).strip()
        if not detail:
            return f"wrapper exited with code {result.returncode} before producing a response envelope"
        first_line = detail.splitlines()[0].strip()
        return f"wrapper exited with code {result.returncode}: {first_line}"
