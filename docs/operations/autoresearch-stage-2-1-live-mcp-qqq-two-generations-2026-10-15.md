# Quant Autoresearch — [2-1 / 전체 5단계] 실제 ChatGPT MCP 연구 2세대와 무거래 전략 오류 수정

검증 일자: 2026-10-15. 실제 연결된 기존 Quant MCP/인증 호출, URL 불변. 연구 데이터는 development Tiingo QQQ 2020-01-02~2025-12-31 raw 1,508봉. **NON-PIT 개발 자료**이며 sealed OOS·broker 사용 금지.

## 실제 연결·세션 수락

- 기존 ChatGPT 연결에서 연구 도구 32개 전부 접근 가능, workspace READY, paper only/orders_enabled=false.
- 연결된 Quant MCP 직접 호출로 start_algorithm_research → (GPT 작성 typed AlgorithmPlan) → submit_algorithm_plan → (GPT 거래 진단 후 typed DiagnosticResponse) → submit_algorithm_diagnosis를 **2세대 완주**.
- 세션 ID 9836a99dc9ec46898727c554dd100f8e, 서버 상태 COMPLETED, completed_generations=2/2. 원본 감사 Evidence 해시는 각각 a761d5ff0b086e045c44b4bfd852404e2c31e752da16a1bf932314b07abe21c2 / ba3dcdb33eb2460d9ae88f529bb901a687ccadde4b8601b70ab776d250b22677.
- 1세대: SMA 레짐 + EMA/dual SMA 투표, 개발 총 수익률 81.97%, max drawdown 20.13%, closed trades 78. 증빙 ID를 갖는 손실($628)을 근거로 진입 확인 강화를 가설로 제출했고, 개발 대조군에서 MDD **20.13%→26.35%로 악화** (DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY). 서버 다음 방향 EXPLORE.
- 2세대: SMA 레짐 + 20일 range-low reclaim / previous-range breakout 조합, 총 수익률 -16.59%, MDD 21.47%, trades 116, exposure 13.93%. 대조 실험에서 동시 확인을 강제하니 parent 232 fills → child 0 fills. child MDD 0%를 기존 실행 코드가 **DIRECTION_MATCHED_DEVELOPMENT_ONLY**로 잘못 표시했다. 아무 거래도 하지 않은 방어적 '성과'로 오인하면 안 되는 핵심 결함.
- 첫 DiagnosticResponse에서 모델이 win_rate를 실험 기준으로 요청했으나 S7 실제 지원 지표 집합에 포함되지 않아 오류가 발생했다. 기존 체크포인트를 확인했더니 소모되지 않았고, 실제 S7 지원값 max_drawdown으로 정정한 후 제출·완료했다.
- 최종 연구 서버 응답은 real_model_connection_verified=false, model_autonomy_verified=false, independent_profitability_verified=false로 표기. **이 대화에서 GPT가 직접 두 세대의 판단·툴 호출을 수행한 것은 관찰했지만, 서버 차원 외부 모델 인증·10~100세대 자율 실행 검증은 아니다.** 이 점을 그대로 유지한다.

## 신규 개발 변경 (기존 운영 서비스에는 미배포)

1. research/indicator_engine/controlled_experiments.py: 부모가 실제 거래하는데 변경 후보가 모든 체결을 제거한 경우, 방향이 맞아도 새 상태 DEGENERATE_INACTIVE_CHILD로 분류한다. 측정된 0% MDD와 0건 fill 및 비교 수치를 숨기지 않는다.
2. research/llm/adaptive_direction.py: 새 상태 또는 **과거 immutable** DIRECTION_MATCHED 기록의 parent_fill_count>0/child_fill_count=0를 연구 조언에서만 비활성으로 읽는다. 원본 해시/DB/과거 보고서를 수정하지 않으며, 마지막 실험이 무거래뿐이면 EXPLORE / LAST_CONTROL_INACTIVE_CHILD로 분류한다.
3. research/indicator_engine/experiment_preflight.py: LLM의 실험 계획 힌트에 진짜 실행 가능한 SUPPORTED_CONTROLLED_METRICS (total_return/cagr/max_drawdown/sharpe/sortino/trade_count)를 추가한다. typed 진단 모델이 win_rate까지 허용한다 해도 S7은 현재 측정 못한다는 차이를 사용자·GPT에 안내한다. 기존 서명된 연구 컨텍스트 해시 본문은 변경하지 않는다.
4. 관련 테스트: 실제 코어 backtest로 무거래 child 재현, S8 이전 v2 보고서 불변 + 읽기 전용 상태 정규화, 지원 지표 힌트, 기존 S7/S8/SDK 재검사.

## 2-1 / 이후 수락 조건

이번 검증으로 기존 앱을 삭제/재등록하지 않고 **GPT 연구 2세대의 수직 경로**가 실제 작동함을 확인했다. 그러나 전체 2-1 완성 기준은 복구·오류 처리와 여러 조건에서 장기간 정상 동작도 포함한다. 후속 2-2는 10세대 이상 GPT 주도 연속 연구, 실패 재개/시간·비용·세대 증거, 동일 탐색 예산 무작위 비교로 정량 평가해야 한다. 이후 Stage 4에서 독립 OOS/PIT/기업행동/실거래 비용을 평가한다.

**중요:** 새 연구 결과는 기존 프로덕션 MCP가 저장한 원본 그대로 보존한다. 새 코드가 적용되기 전까지 운영 서버는 이전 zero-fill 분류 방식을 유지한다. 새 기능은 별도 개발 브랜치에만 존재하며 기존 URL, OAuth/키, 봉인 OOS, 원장, 주문 비활성 상태와 2026-10-16 예약 수집은 변경하지 않는다.
