# Quant AutoResearch — T4 진입·청산 분리 실험 및 모델 실험 설계 개선

기준: 2026-10-20 KST. 분리 실험은 실제 인증 ChatGPT MCP를 통해 완료. 모델 실험 안내 변경은 저장소 개발 브랜치이며 운영 서버에 미배포. 개발용 QQQ RAW 가격은 독립 PIT/OOS 미검증, 수익성 입증 아님.

## 실험 목적
이전 독립 세션 7746c2f00b154c6cbf28399fe4d11d60에서 부모와 비교하여 진입과 청산 규칙을 동시에 바꿨더니 청산 거래 21→51, 체결 43→102, 누적 수익 +35.995%→-4.108%가 되었다. 두 변경을 묶어서는 어느 변경이 원인인지 알 수 없으므로, 본 작업에서 같은 부모를 기준으로 한 번에 한 조건씩 실험했다.

- 신규 세션: 9562430e1b29417d9b7dc66a8a5ce2fe
- 요청 세대 1 / 완료 세대 1. 제출 가설 2 / S7 실제 측정 2.
- 기존 부모: volatility_switch_probe_01, 변동성 국면에 따른 time_series_momentum+sma_pullback, previous_range_breakout+range_low_reclaim 가중 투표.
- QQQ Tiingo RAW 2020-01-02~2025-12-31, 1508봉; 데이터 해시 328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6. 자료 버전/기업행위 PIT 미검증.
- 동일 이전 부모 전략 SHA 66ce5bdb7c6b232ee42f65a4c4d7b756c78ee3a8e284fc64ee32a1ce3452dde4, audit SHA 72482de02bbd7ee0c200d3212f1895a9302dc36014642291a021ff30c9b79973, 계획 SHA ab36b7808402f46cfe140017c0ebbb090be0b449940b3cfe87f524cd2f8eadb8. 데이터/비용/컨트롤 고정.

## 실제 결과

| 항목 | 기준 부모 | 진입 조건만 변경 | 청산 조건만 변경 |
|---|---:|---:|---:|
| 변경 부위 | 원본 | entry.conditions.0: plan_vote_score > 0.8 | exit.conditions.0: plan_vote_score <= 0.8 |
| 거래수 사전 예측 | - | 감소 | 증가 |
| 청산 완료 거래 | 21 | 6 | 356 |
| 실제 체결 | 43 | 13 | 712 |
| 총비용 USD | 342.0961 | 109.8068 | 4711.3072 |
| 초기 10000달러의 최종 equity | 13599.5124 | 11995.5730 | 7084.6037 |
| 누적 수익률 | +35.9951% | +19.9557% | -29.1540% |
| 거래수 사전 예측과 일치 | 기준 | YES, -15 | YES, +335 |

S7 측정 등급: 두 가설 모두 DIRECTION_MATCHED_DEVELOPMENT_ONLY. 청산만 변경하면 거래가 과도하게 증가하고, 비용이 크게 늘었다. 진입만 변경하면 거래는 크게 줄지만 수익률이 악화됐다. 이는 같은 개발 표본에서 각각의 단독 변화에 대한 관측이며 독립 OOS 및 실전 수익성 입증이 아니다. 두 단독 효과를 더해 복합 변경의 효과를 예측하거나 정확한 인과 기여도를 계산할 수 없다. 실제 이전 복합 수정의 51회 거래와 단독 청산 변경의 356회 거래가 다르므로 상호작용도 고려해야 한다.

- S7 report SHA: bf59cc562f6b30bf7b2c4784c36428b872a2c9949d97ccb197d240f5373c6287
- S7 persisted record SHA: fbd5225e8bf6a7e7a6606220d8de82e9b0fef44e90e5d91fb0c7606acc0649e6
- Entry-only child SHA: 1f22048c94bc6171c132b329f1ff489ae6665977ad562611534a6cf4357ef599
- Exit-only child SHA: 91711e3296a3026c97e5c1ebac259490e6d394aa84d34b30b0552128c14c787a

## 코드 개선

- 연구 LLM 진단 안내 academic_diagnostic_quality_hint의 기존 혼합 진입+청산 예시를 진입 한 조건만 바꾸는 예시로 교체.
- causal_attribution_guidance 추가: 1회 1개 부위의 통제 실험 권고, 복합 변경은 JOINT 효과로만 기술, 같은 부모의 진입 단독/청산 단독 대조 권고, 총수익·거래수·거래비용 함께 보고.
- 여러 조건을 결합하는 LLM의 설계 자유도는 보존하고, 단일 원인으로의 과도한 해석만 억제한다.
- 테스트: test_experiment_preflight의 새 회귀 사례, S7 및 academic MCP 세션 호환 테스트. 이전 immutable evidence schema 및 protected core/backtest/costs/StrategyIR 불변.
- **신규 P1-3 GeneralResearchPlan은 운영 MCP에 미연동.** 이번 실험은 기존 AlgorithmPlan을 실제 MCP에서 실행했다. 리포지토리 변경 안내 역시 서버 배포 전까지 운영에서 미적용.

## 미완료 / 다음

- 이번 독립 연구는 1세대·가설 2건. 실제 모델 무인 자율성, 10/100세대 GPT 대 random 동일 예산 대조, PIT/OOS, 실전 주문·수익성, 신 IR의 운영 배포는 미검증.
- 기존 G350 공식 원장은 수정하지 않았고, 실주문 OFF 및 MCP URL/OAuth 상태는 유지. 운영 앱에는 별도의 신규 실험 세션 Evidence만 추가됨.
- 다음: T4 10→100세대 대조·진단 반복·중단/복구, 그다음 P1-3 새 범용 계획의 안전한 opt-in 운영 연결. T4가 제품 로드맵 상 먼저다.
