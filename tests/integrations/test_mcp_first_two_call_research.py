"""MCP SDK tool plane: an actual 2-write generation with no model API transport.

The GPT proposals here are deterministic fixtures; this proves MCP semantics,
not external LLM creativity or out-of-sample trading profitability.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from mcp import types
from mcp.server import ServerRequestContext

from core.data.parquet import ParquetDataProvider
from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter
from tests.research.test_academic_algorithm_plan import _market
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def test_existing_mcp_sdk_executes_complete_generation_in_two_model_writes(
    tmp_path: Path,
) -> None:
    root = tmp_path / 'project'
    (root / 'data').mkdir(parents=True)
    ParquetDataProvider.write(root / 'data' / 'study.parquet', _market())
    adapter = create_chatgpt_sdk_adapter(project_root=root, state_dir=tmp_path / 'state')

    async def run() -> None:
        context = cast(ServerRequestContext[Any], None)
        published = await adapter.list_tools(context, None)
        tools = {item.name for item in published.tools}
        assert len(tools) == 32
        assert {
            'start_algorithm_research', 'submit_algorithm_plan',
            'submit_algorithm_diagnosis', 'evaluate_algorithm_experiments',
        } <= tools

        async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            reply = await adapter.call_tool(
                context, types.CallToolRequestParams(name=name, arguments=arguments)
            )
            assert reply.is_error is not True, name
            item = reply.content[0]
            assert isinstance(item, types.TextContent)
            body = json.loads(item.text)
            assert body['_contract']['orders_enabled'] is False
            return body

        started = await call('start_algorithm_research', {
            'data_path': 'data/study.parquet', 'generations': 2,
        })
        research = ScriptedResearcher()
        for generation in (1, 2):
            staged = await call('submit_algorithm_plan', {
                'session_id': started['session_id'],
                'checkpoint_token': started['checkpoint_token'],
                'plan': research.propose(started['model_context']),
            })
            completed = await call('submit_algorithm_diagnosis', {
                'session_id': started['session_id'],
                'checkpoint_token': staged['checkpoint_token'],
                'diagnosis': research.propose(staged['model_context']),
            })
            assert completed['completed_generations'] == generation
            assert completed['controlled_experiments_automatically_evaluated'] is True
            assert completed['latest_controlled_experiments']['generation'] == generation
            assert completed['latest_controlled_experiments'][
                'original_generation_evidence_hash'
            ] == completed['history'][-1]['evidence_hash']
            if generation == 1:
                assert completed['model_context']['prior_research'][
                    'controlled_experiments'
                ]['record_hash'] == completed['latest_controlled_experiments']['record_hash']
                assert completed['model_context']['research_direction'][
                    'experiment_outcome_count'
                ] > 0
            started = completed
        assert started['status'] == 'COMPLETED'
        assert started['orders_enabled'] is False
        previous = await call('evaluate_algorithm_experiments', {
            'session_id': started['session_id'], 'generation': 2,
        })
        assert previous == started['latest_controlled_experiments'] | {
            '_contract': previous['_contract']
        }

    asyncio.run(run())
