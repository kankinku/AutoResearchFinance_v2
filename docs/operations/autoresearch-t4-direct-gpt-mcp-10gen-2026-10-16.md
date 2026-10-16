# Quant Autoresearch T4 — 연결된 ChatGPT MCP 직접 10세대와 증거 복구

기준: 2026-10-16 KST / 2026-10-16 UTC. 범위 잠금 최상위 요구사항 [20문답](../decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md) Q02/Q06/Q07/Q15/Q17/Q20. 기존 Quant MCP URL/OAuth/32개 도구 및 `orders_enabled=false` 유지.

## 이번 턴의 실제 툴 직접 호출 (자동 생성 mock, 외부 유료 LLM API 아님)

- 이 ChatGPT 대화에서 제공된 Quant 커넥터의 `start_algorithm_research`, `get_algorithm_research`, `submit_algorithm_plan`, `submit_algorithm_diagnosis`, `evaluate_algorithm_experiments` 도구를 직접 호출. `start_algorithm_research(generations=10)` 사용.
- QQQ `data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet` (1,508 일봉, 단일 DEVELOPMENT, non-PIT/가격·기업행동 as-of 검증 미확보), 기존 등록 지표/typed AlgorithmPlan와 canonical StrategyIR/Backtest/S7. 주문 0, OOS 미개봉.
- 서버가 발급한 실험 세션 식별자: `49d3033496844ea391f7bdc983da3fc9`. 실제 MCP 상태 `COMPLETED`, 세대 10/10, 서로 다른 `algorithm_semantic_hash` 10/10, S7 10/10 보존 및 이전 세대 원본 `evidence_hash`가 모든 S7의 `original_generation_evidence_hash`와 일치(10/10).
- 매 세대 이전 결과와 거래·손실 사례를 검토하여 ChatGPT가 새 전략 구성/진단을 직접 작성, 제출. 가설은 원인 **추정**으로 남김. 5세대의 실험 `DEGENERATE_INACTIVE_CHILD` 1건, 8세대 예상과 반대 `DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY` 1건, 기대 방향 일치 `DIRECTION_MATCHED_DEVELOPMENT_ONLY` 8건. 이러한 실험 결과의 통계적 유의성은 입증하지 못함.
- 세대의 성과는 **모두 재사용 개발 기간 내** 수치: 최대 관찰된 누적 수익률 약 64.58%는 3세대, 마지막 10세대 누적 수익률 약 34.13% 및 MDD 약 10.69%. *개별 전략 수익률에 PIT/OOS·broker/미래 수익 확률 승인 없음.*
- 기계 판독 감사 증거 `docs/operations/evidence/quant-validation-20261016/t4-connected-mcp-10gen-direct-audit.json`: 각 10세대 계획 ID/시맨틱 해시, 원본 결과 hash, 실제 S7 record/evidence hash, outcome/측정 delta·데이터 scope, 서버의 마지막 요약 불일치/주문·자율성 한계.

## 실제 확인한 T4 장애/차단 사항

1. **실제 S7은 모두 측정됐는데 서버 최종 보고서가 `tested_hypotheses=0`을 돌려줌.** 원인은 `research/llm/autonomous_cycle.py`의 기본 `_final_report`가 gateway 별도 S7 원장을 보지 않고 `0`으로 고정하기 때문. 이는 S7 미실행 의미가 아니라 잘못된 집계이므로 최종 10세대 증거를 각각 따로 직접 재감사함.
2. 연구 개발 브랜치 `feat/t4-gpt-mcp-ten-generation-evidence-20261016`에서 `application/academic_checkpoint_service.py`의 **gateway 표시 계층만** 변경하여, final_report 작성 시 SQLite에 영구 보관된 S7 원장·원본 generation evidence hash·S7 hypothesis ID 및 변조방지 hash를 재검사하고 `tested_hypotheses`/`all_proposed_hypotheses_measured`을 실제 자료 기준으로 갱신. `tests/integrations/test_academic_mcp_sessions.py`에서 **먼저 기존 `0`으로 실패 재현**, 수정 후 2세대 fixture `2` 집계 PASS. Cycle 원본 evidence·protected 평가엔진·모델 권한·실주문 미변경. 운영 MCP는 여전히 해당 수정 **미배포**.
3. 직접 ChatGPT 커넥터 상호작용으로 각 10건의 모델 제안/진단을 관찰했으나 서버는 `real_model_connection_verified=false`와 `model_autonomy_verified=false`를 출력. 이는 독립 모델 identity attestation/장시간 무인 에이전트 실행의 증거가 아니므로 **완전 자율 운영 승인 불가**. 해당 false 상태를 임의로 true로 만들지 않음.
4. 기존 2026-10-15 문서에 10 GPT vs random 10 탐색 기록이 있지만, 실행 버전/경로가 달라 이번 **동일 정책·동일 예산/seed의 독립적 사전등록 무작위 비교는 실행하지 않음.** 실제 100세대 및 재시작/중단 복구·랜덤 장기 비교·독립 PIT/OOS·시장경제적 순수익 **미실행**.

## 100세대로 확대하지 않은 이유 및 다음 작업

- 초기 20문답의 T4는 단순 10개의 백테스트가 아닌 원인 진단·대조실험·다음 계획과 checkpoint 복구, 같은 예산 무작위 비교, 모델 실제 연결성을 요구. 이번에는 10/10 체인·S7 hash는 검증했으나 **최종 집계 버그 및 백엔드 모델 자율성 인증/동예산 대조 부재**가 발견됨.
- 따라서 이번 10세대에 `T4_DIRECT_MCP_10_COMPLETE__100_BLOCKED_ACCEPTANCE_GATES` 상태를 부여. 100세대 세션은 **시작하지 않았다**. 실패/미확인 항목을 통과로 재분류해 100 실행하지 않는다.
- 다음은 **동일 T4 내 연속 검증 작업**: 새 집계 코드 범위 통합 테스트/운영 적용 심사(운영 URL/OAuth 불변) → 사전 고정 동일 예산 랜덤 대조 및 체크포인트 복구 리허설 → 실제 연결 100세대의 모델 주도 생성·계획·진단 매 세대 인증 가능 여부 확인. 별도 모델 API 자동 이용이나 실주문 활성화는 금지. 승인된 V01~V04→V06→V07 순서는 변경 없음.

**범위 잠금 유지:** 본 작업은 Q02/Q06/Q07/Q15/Q17/Q20의 자율 연구 *검증 및 직접 발견한 보고 불일치 수정*만 수행. 새로운 지표/시장 전략 수동 최적화·OOS 개봉·MCP 재등록/키 회전 없음.
