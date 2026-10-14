"""S8 deterministic, bounded and non-claiming research direction recommendations."""
from copy import deepcopy

import pytest

from research.llm.adaptive_direction import ResearchBudgetError, build_research_direction


def _history(n: int = 1):
    return [{
        'generation': i,
        'evidence_hash': f'{i:064x}',
        'algorithm_semantic_hash': f'{i+100:064x}',
        'hypothesis_ids': [f'test_{i}'],
        'metrics': {'total_return': 3.0},  # No return-chasing in guidance.
    } for i in range(1, n + 1)]


def _report(history, *, state='NO_OBSERVED_EFFECT', added=0, resized=0, multi=False):
    return {
        'original_generation_evidence_hash': history[-1]['evidence_hash'],
        'record_hash': 'd' * 64,
        'report': {
            'causal_status': 'NOT_ESTABLISHED',
            'multiple_comparison_notice': multi,
            'experiments': [{
                'hypothesis_id': 'test_1',
                'status': state, 'causal_status': 'NOT_ESTABLISHED',
                'execution_delta': {
                    'added_event_count': added,
                    'removed_event_count': 0,
                    'resized_event_count': resized,
                },
            }],
        },
    }


def test_first_generation_recommends_exploration_not_fake_alpha():
    result = build_research_direction([], {})
    assert result['recommended_mode'] == 'EXPLORE'
    assert result['completed_generations'] == 0
    assert result['independent_oos_approved'] is False
    assert result['llm_may_override'] is True
    assert result['allocation_is_not_fixed_quota'] is True
    assert result == build_research_direction([], {})


def test_unchecked_loss_hypothesis_prioritizes_causal_experiment_not_evolution():
    a = build_research_direction(_history(), {})
    assert a['recommended_mode'] == 'TEST_HYPOTHESIS'
    assert a['reason_code'] == 'LATEST_GENERATION_HAS_UNTESTED_HYPOTHESES'


def test_control_no_effect_and_wrong_direction_promote_exploration():
    h = _history()
    for state in ('NO_OBSERVED_EFFECT', 'DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY'):
        r = build_research_direction(h, {1: _report(h, state=state)})
        assert r['recommended_mode'] == 'EXPLORE'
        assert r['experiment_outcome_count'] == 1


def test_change_of_position_size_is_not_auto_alpha_discovery():
    h = _history()
    record = _report(h, state='DIRECTION_MATCHED_DEVELOPMENT_ONLY', resized=53)
    r = build_research_direction(h, {1: record})
    assert r['recommended_mode'] == 'TEST_HYPOTHESIS'
    assert r['execution_change_counts']['SIZE_ONLY_CHANGED'] == 1
    assert r['causal_status'] == 'NOT_ESTABLISHED'


def test_timing_change_recommends_further_evolution_but_without_profit_claim():
    h = _history()
    record = _report(h, state='DIRECTION_MATCHED_DEVELOPMENT_ONLY', added=2)
    r = build_research_direction(h, {1: record})
    assert r['recommended_mode'] == 'EVOLVE'
    assert not r['real_trading_enabled']
    record = deepcopy(record)
    record['report']['multiple_comparison_notice'] = True
    assert build_research_direction(h, {1: record})['recommended_mode'] == 'TEST_HYPOTHESIS'


def test_multiple_generations_avoid_overcounting_trials_and_duplicates():
    h = _history(3)
    h[1]['algorithm_semantic_hash'] = h[0]['algorithm_semantic_hash']
    h[2]['algorithm_semantic_hash'] = h[0]['algorithm_semantic_hash']
    r = build_research_direction(h, {1: _report(h[:1]), 3: _report(h)})
    assert r['completed_generations'] == 3
    assert r['repeated_strategy_count'] == 2
    assert r['unique_strategy_count'] == 1
    assert r['recommended_mode'] == 'EXPLORE'
    assert r['experiment_outcome_count'] == 2


def test_forged_evidence_rejected_not_promoted_to_guidance():
    h = _history()
    altered = _report(h)
    altered['original_generation_evidence_hash'] = 'f' * 64
    with pytest.raises(ResearchBudgetError, match='original generation'):
        build_research_direction(h, {1: altered})
    altered = _report(h)
    altered['report']['experiments'][0]['execution_delta']['added_event_count'] = -1
    with pytest.raises(ResearchBudgetError, match='counts'):
        build_research_direction(h, {1: altered})
    with pytest.raises(ResearchBudgetError, match='completed generation'):
        build_research_direction(h, {2: _report(h)})
    with pytest.raises(ResearchBudgetError, match='order'):
        build_research_direction(list(reversed(_history(2))), {})
