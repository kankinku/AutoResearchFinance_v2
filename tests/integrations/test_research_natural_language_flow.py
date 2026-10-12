"""End-to-end MCP journey after the model chooses source/data by the catalog."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.types import CallToolRequestParams

from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter
from tests.application.test_research_input_catalog import _catalog_fixture


def test_user_journey_uses_catalog_preflight_batch_and_evidence(tmp_path: Path) -> None:
    _catalog_fixture(tmp_path)
    adapter = create_chatgpt_sdk_adapter(
        project_root=tmp_path, state_dir=tmp_path / "state"
    )

    async def invoke(name: str, args: dict[str, object]) -> dict[str, object]:
        response = await adapter.call_tool(None, CallToolRequestParams(
            name=name, arguments=args
        ))
        assert response.is_error is False, (name, response)
        return json.loads(response.content[0].text)

    async def journey() -> None:
        # Simulate one natural-language intent: test three QQQ trend conditions.
        brief = await invoke("get_research_brief", {})
        catalog = brief["research_inputs"]
        assert catalog["ready_for_batch"] is True
        source = next(item for item in catalog["sources"] if item["family"] == "trend")
        market = next(item for item in catalog["datasets"] if "QQQ" in item["symbols"])
        parameter = source["numeric_parameter_paths"][0]
        request: dict[str, object] = {
            "source_path": source["source_path"],
            "data_path": market["data_path"],
            "intent": {
                "mode": "structure",
                "parent_ids": [source["strategy_id"]],
                "operations": [],
                "rationale": "Compare three existing QQQ trend parameter settings",
            },
            "generations": 1,
            "method": "grid",
            "count": 3,
            "parameter_domains": [{"name": parameter, "values": [2, 3, 4]}],
            "min_trades": 0,
            "min_annual_trades": 0,
            "seed": 8,
        }
        preview = await invoke("preflight_research_batch", request)
        assert preview["status"] in {"READY", "READY_WITH_WARNINGS"}
        assert preview["orders_enabled"] is False
        assert preview["preview_unique_strategies"] == 3
        started = await invoke("start_research_batch", request)
        job = str(started["job_id"])
        for _ in range(160):
            await asyncio.sleep(.2)
            status = await invoke("get_research_batch_status", {"job_id": job})
            if status["status"] not in {"QUEUED", "RUNNING"}:
                break
        assert status["status"] == "COMPLETED", status
        report = await invoke("get_research_batch_report", {"job_id": job})
        assert report["final_report_ready"] is True
        assert report["evaluated_candidate_instances"] == 3
        assert report["unique_candidate_count"] == 3
        assert report["failure_analysis"]["source"] == "immutable_evidence"
        assert report["failure_analysis"]["sealed_oos"] == "NOT_MEASURED"
        assert report["orders_enabled"] is False

    asyncio.run(journey())
