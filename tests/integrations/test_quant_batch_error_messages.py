"""Readable, non-leaking Quant batch errors and input discovery."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.types import CallToolRequestParams

from application.research_batch_service import ResearchBatchService
from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter
from tests.orchestration.test_evaluation_runner import _write_inputs


def _error(adapter: object, tool: str, args: dict[str, object]) -> dict[str, object]:
    async def run() -> dict[str, object]:
        result = await adapter.call_tool(  # type: ignore[attr-defined]
            None, CallToolRequestParams(name=tool, arguments=args)
        )
        assert result.is_error is True
        return json.loads(result.content[0].text)

    return asyncio.run(run())


def test_batch_preflight_reports_missing_data_without_absolute_path(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    (tmp_path / "bars.parquet").unlink()
    adapter = create_chatgpt_sdk_adapter(project_root=tmp_path, state_dir=tmp_path / "state")
    args = {
        "source_path": "strategy.yaml",
        "data_path": "bars.parquet",
        "generations": 5,
        "intent": {
            "mode": "structure",
            "parent_ids": ["runner-test"],
            "operations": [],
            "rationale": "Test failure without launching research",
        },
    }
    response = _error(adapter, "start_research_batch", args)
    assert response["error_code"] == "DATA_FILE_NOT_FOUND"
    assert "get_research_brief" in response["message"]
    assert str(tmp_path) not in json.dumps(response)
    assert not ResearchBatchService(
        project_root=tmp_path, state_dir=tmp_path / "state"
    ).database.exists()


def test_batch_status_without_job_returns_actionable_error(tmp_path: Path) -> None:
    adapter = create_chatgpt_sdk_adapter(project_root=tmp_path, state_dir=tmp_path / "state")
    response = _error(adapter, "get_research_batch_status", {})
    assert response["error_code"] == "NO_BATCH_FOUND"
    assert response["orders_enabled"] is False


def test_research_inputs_lists_real_strategy_and_market_data_only(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    empty = service.describe_inputs()
    assert empty["ready_for_batch"] is False
    assert empty["data_paths"] == ["bars.parquet", "series.parquet"]
    (tmp_path / "strategies" / "normalized").mkdir(parents=True)
    (tmp_path / "strategies" / "normalized" / "baseline.yaml").write_text(
        (tmp_path / "strategy.yaml").read_text()
    )
    # Only registered normalized JSON candidates are offered by the discovery helper.
    assert service.describe_inputs()["ready_for_batch"] is False
