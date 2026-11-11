# Quant V05 정식 비용 재실행/선택편향 평가 — [6/16]

**작성:** 2026-11-10 · **범위:** Task 5 / V05 (Q04/Q07/Q09/Q11/Q13/Q20). 실거래와 OOS 데이터 접근 없음.

## 구분해야 할 두 계산

1. **기존 고정 체결 비용 프록시:** `audit_development_economics(...)`. 최초 백테스트의 체결 수량/가격/일시를 고정한 상태로 추가 비용만 사후 차감한다. 기존 스키마 `v05-development-net-capacity-search-diagnostic-v1`, `stressed_net_pnl_proxy_usd`, `fixed_fill_stress_is_true_replayed_backtest=False`, `report_hash`는 그대로 둔다.
2. **새 정식 재실행:** `audit_replayed_development_cost_stress(market, baseline, compiled, ...)`. 먼저 기존 프록시의 비용·체결·데이터 해시·시도 횟수/유동성 게이트를 검증한다. 해당 `CompiledAcademicStrategy`의 원본 `evaluate_compiled_development` 결과와 baseline의 모든 필드가 일치하는지 다시 계산해 확인한다. 이후 `BacktestEngine.run(BacktestRequest(..., cost_stress_multiplier=배수, feature_values_pre_lagged=True))`를 **실행**한다.
3. 재실행 값은 진짜 체결 내역에서 산출한 `replay_trade_count`, `replay_total_paid_costs_usd`, `replay_net_pnl_usd`, `replay_max_drawdown_pct`, `replay_equity_hash`, `replay_fill_trace_hash`로만 기록한다. 기존 고정 체결 추정치는 `proxy_net_pnl_usd`로 분리, 차이는 `replay_minus_proxy_usd`로 공개한다. 시장/전략/비용 모델 버전 및 세율·슬리피지·배수의 정책 해시와 별도 `report_hash`로 재현성을 추적한다.

## CLI 사용 계약

`audit-algorithm-economics`는 기본값 그대로 **기존 프록시 보고서**를 출력한다. **선택 옵션 `--canonical-replay`**를 부여할 때만 별도 스키마 `v05-canonical-cost-stress-replay-v1`로 재실행 보고서를 출력한다. 기존 `--market-parquet`, `--plan-json-file`, `--attempted-trials`, `--max-participation`, `--stress-multiplier`, `--database` 입력을 유지하며, 새로운 공개 MCP 도구/토큰/데이터베이스를 생성하지 않는다.

## 실패 시 차단

- 개발 전용 데이터·정본 체결/손익/비용·전략/신호/입력 불일치, 잘못된 배수·시도 횟수, 없는·무효한 거래량, 일별 참여율 초과, 봉 시가가 아닌 체결, 불가능한 비용(엔진 실행 실패)은 **`ResearchCatalogError`로 거부**한다.
- 동일 시도 횟수를 선언했더라도 전체 실험 원장 확인이 없으면 `full_trial_count_proven=False`, `multiple_trial_statistical_significance_approved=False`. 통계적 유의성·선택편향 제거·효과적인 독립 시행 횟수를 입증했다고 표시하지 않는다. `cohort_dependence_status`와 `iid_equivalent_trials_proxy`는 원래 V05의 훈련 전용 프록시다.
- `status=DEVELOPMENT_ONLY_REPLAY`, `point_in_time_verified=False`, `out_of_sample_approved=False`, `realizable_net_profit_verified=False`, `candidate_promotable=False`, `broker_executable=False` 고정. 개발 구간 재실행이 독립 수익성/실거래 승인으로 변환될 수 없다.

## 검증·미검증

- **RED→GREEN:** 기존 함수만 있던 상태에서 신규 정식 재실행 API ImportError; CLI `--canonical-replay` 인식 실패; 실제 체결 해시/비용 정책 해시 검증 실패를 각각 확인하고 수정.
- 정본과 직접 비교: 실제 `BacktestEngine.run` 재실행의 체결 수·체결 해시·지불 비용·자산 곡선 해시와 감사 보고서 동치. 비용 배수 1이면 baseline과 동치; 비용 배수 5에서 고정 체결 비용 추정과 실제 현금/매수 수량 기반 재실행 손익 차이 관측.
- 고위험 범위 거부(봉인 OOS, 잘못된 baseline/전략, 비용 모델, 비용 배수, 시도 횟수, 유동성 한계), 기본 CLI 결과·해시 불변, opt-in CLI 보고서 별도 검증.
- **실제 검사:** V05 + 개발 벤치마크 **38 PASS**; 핵심 백테스터·학술 전략/감사·전방 윈도·거버넌스까지 포함한 확대 테스트 **381 PASS**. `ruff check .` PASS, `mypy research/indicator_engine/development_economics_v05.py research/indicator_engine/cli.py` PASS, `git diff --check` PASS. 전체 `pytest -q -x`는 **448 PASS, 1 FAIL**, 첫 실패에서 중단: 변경되지 않은 구형 대시보드 테스트 `test_readonly_sqlite_bridge_matches_original_contracts`가 과거 2026-10-21 세션의 `session-id.txt` 결손을 요구함. **전체 suite PASS 아님**.
- 시장 데이터와 카탈로그는 전부 **합성 fixture 및 로컬 임시 파일**. 실제 공급자 PIT, 독립 OOS, 모형 호출, 실제 새로운 G1 세대, 거래·주문·운영 배포 **NOT_RUN**. 기존 150세대 성과·부모·기억을 신규 연구 입력으로 다시 불러오지 않았다.
- 승인된 다음 순서: **[7/16] Task 6 MCP/OAuth 통합 계약 게이트**, V05→T4→V01~V04→V06→V07. 기존 32 MCP와 OAuth 보존. 구형 대시보드의 사라진 역사적 세션 파일에 따른 전수 테스트 미통과가 후속 미해결 항목.
