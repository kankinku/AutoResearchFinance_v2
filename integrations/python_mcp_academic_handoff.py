"""D3: deliberately narrow, externally signed academic MCP checkpoint handoff.

No GPT provider, collector private key, model emulator, research-generation
counter, order or OOS access lives here. A signed collector assertion proves
the collector's signature only; it does NOT prove provider invocation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import stdio_client

from integrations.python_mcp_direct import QuantMCPDirectClient
from research.llm.model_provenance_v1 import parse_public_key, verify_capture


class AcademicSubmissionRejected(ValueError):
    """The signing/identity/phase boundary rejected the model handoff."""


class AcademicSubmissionUncertain(RuntimeError):
    """A reply failed: re-read the existing checkpoint, never blindly replay."""


class SignedAcademicHandoff:
    """Accept only a captured decision signed by an independently held key."""

    def __init__(self, client: QuantMCPDirectClient) -> None:
        self.client = client
        settings = client.settings
        if settings.surface != "chatgpt_academic" or settings.scope_session is None:
            raise AcademicSubmissionRejected("academic scoped MCP surface required")
        if settings.capture_public_key_hex is None:
            raise AcademicSubmissionRejected("trusted external capture public key required")
        self._key = parse_public_key(settings.capture_public_key_hex)

    @staticmethod
    def _assert_checkpoint(state: Mapping[str, Any], session_id: str) -> None:
        if state.get("session_id") != session_id:
            raise AcademicSubmissionRejected("signed handoff session mismatch")
        if state.get("orders_enabled") is not False:
            raise AcademicSubmissionRejected("orders are not disabled")
        if state.get("independent_oos_approved") is not False:
            raise AcademicSubmissionRejected("sealed OOS boundary changed")
        if not isinstance(state.get("model_capture_context_hash"), str):
            raise AcademicSubmissionRejected("checkpoint lacks pinned P4-2 capture")
        audit = state.get("model_capture_audit")
        if not isinstance(audit, dict) or not audit.get("external_collector_signature_verified"):
            raise AcademicSubmissionRejected("trusted collector checkpoint audit missing")
        if state.get("checkpoint_phase") not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
            raise AcademicSubmissionRejected("checkpoint is not accepting model decisions")

    async def submit(
        self,
        session_id: str,
        payload: dict[str, Any],
        model_capture: Mapping[str, Any],
        *,
        checkpoint_token: str,
        require_execution_change: bool = True,
        require_trade_activity: bool = True,
    ) -> dict[str, Any]:
        """Stage a plan or commit a diagnosis with existing canonical checks.

        Both the calling Python process and the academic MCP server verify the
        signed external collector assertion. The payload is not a model proof.
        """
        self.client.assert_session(session_id)
        if not isinstance(payload, dict) or not payload:
            raise AcademicSubmissionRejected("structured model response required")
        if not isinstance(model_capture, Mapping) or not model_capture:
            raise AcademicSubmissionRejected("signed capture required")
        if not isinstance(checkpoint_token, str) or len(checkpoint_token) != 32:
            raise AcademicSubmissionRejected("exact 32-character checkpoint token required")
        if (
            type(require_execution_change) is not bool
            or type(require_trade_activity) is not bool
        ):
            raise AcademicSubmissionRejected("precommit flags must be booleans")

        before = await self.client.read_academic_checkpoint(session_id)
        self._assert_checkpoint(before, session_id)
        if before["checkpoint_token"] != checkpoint_token:
            raise AcademicSubmissionRejected("stale checkpoint token: re-read before submitting")
        phase = before["checkpoint_phase"]
        kind = "plan" if phase == "AWAITING_PLAN" else "diagnosis"
        receipt = dict(model_capture)
        verify_capture(
            receipt, self._key,
            session_id=session_id,
            generation=before["completed_generations"] + 1,
            phase=kind,
            response=payload,
            context_hash=before["model_capture_context_hash"],
            checkpoint_token=checkpoint_token,
            prior_receipt_hash=before["model_capture_audit"]["chain_head"],
        )

        tool_name = (
            "submit_algorithm_plan" if kind == "plan" else "submit_algorithm_diagnosis"
        )
        args: dict[str, Any] = {
            "session_id": session_id,
            "checkpoint_token": checkpoint_token,
            kind: payload,
            "model_capture": receipt,
        }
        if kind == "plan":
            if require_execution_change:
                # The canonical service only accepts this strict preflight
                # when an inherited verified parent exists.
                if not before["model_context"].get("counted_parent_inheritance_ready"):
                    raise AcademicSubmissionRejected(
                        "strict execution-change requires a verified inherited parent"
                    )
                args["require_execution_change"] = True
            args["require_trade_activity"] = require_trade_activity

        # A second canonical read in the same MCP process closes the preflight
        # race with another caller. On lost replies, STOP; never guess success.
        after: dict[str, Any] | None = None
        submitted: dict[str, Any] | None = None
        rejected = False
        try:
            async with stdio_client(self.client._server_params()) as (read, write):
                async with ClientSession(read, write) as channel:
                    await channel.initialize()
                    available = {t.name for t in (await channel.list_tools()).tools}
                    if {tool_name, "get_algorithm_research"} - available:
                        raise AcademicSubmissionRejected("academic MCP contract unavailable")
                    current_result = await channel.call_tool(
                        "get_algorithm_research", arguments={"session_id": session_id}
                    )
                    current = self.client._validated_payload(current_result)
                    self._assert_checkpoint(current, session_id)
                    if (
                        current["checkpoint_token"] != checkpoint_token
                        or current["checkpoint_phase"] != phase
                        or current.get("model_capture_context_hash")
                        != before["model_capture_context_hash"]
                    ):
                        raise AcademicSubmissionRejected(
                            "checkpoint changed; re-read before submitting"
                        )
                    reply = await channel.call_tool(tool_name, arguments=args)
                    rejected = bool(reply.is_error)
                    if not rejected:
                        submitted = self.client._validated_payload(reply)
                        reread = await channel.call_tool(
                            "get_algorithm_research", arguments={"session_id": session_id}
                        )
                        after = self.client._validated_payload(reread)
        except AcademicSubmissionRejected:
            raise
        except Exception as exc:
            raise AcademicSubmissionUncertain(
                "MCP reply uncertain; re-read canonical checkpoint before any retry"
            ) from exc
        if rejected:
            raise AcademicSubmissionRejected(
                "canonical academic MCP rejected response; inspect unchanged checkpoint"
            )
        if submitted is None or after is None:
            raise AcademicSubmissionUncertain("missing authoritative post-submission read")
        if submitted.get("checkpoint_token") != after.get("checkpoint_token"):
            raise AcademicSubmissionUncertain("acknowledged and canonical checkpoints differ")
        if kind == "plan":
            if (
                after.get("checkpoint_phase") != "AWAITING_DIAGNOSIS"
                or after.get("completed_generations") != before["completed_generations"]
            ):
                raise AcademicSubmissionUncertain("plan did not stage at the expected generation")
        elif after.get("completed_generations") != before["completed_generations"] + 1:
            raise AcademicSubmissionUncertain("diagnosis was not canonically counted")
        if (
            after.get("orders_enabled") is not False
            or after.get("independent_oos_approved") is not False
        ):
            raise AcademicSubmissionUncertain("research boundaries changed")
        return {
            "session_id": session_id,
            "checkpoint_phase": after["checkpoint_phase"],
            # Terminal COMPLETED checkpoints intentionally expose no new token.
            "checkpoint_token": after.get("checkpoint_token"),
            "completed_generations": after["completed_generations"],
            "model_capture_scope": "SIGNED_EXTERNAL_COLLECTOR_NOT_PROVIDER_PROOF",
            "provider_invocation_verified": False,
            "orders_enabled": False,
            "independent_oos_approved": False,
        }
