# T4 — 실제 연결 ChatGPT 연구 1세대 및 반증된 S7 가설

**2026-10-20 KST · T4_ONE_GENERATION_COMPLETE · AUTONOMY_NOT_VERIFIED · NON_PIT_DEVELOPMENT_ONLY**

## 실행 범위
- 사용자의 기존 20문답 Q02/Q06/Q07/Q08/Q09/Q14/Q17/Q18과 승인 순서 V05 → T4 → V01~V04 → V06 → V07을 따랐다.
- 이 ChatGPT 대화에서 기존 Qaunt AutoResearch MCP에 Plan→Diagnosis→S7을 직접 제출했다. 운영 엔진은 모델 신원 독립 증명(real_model_connection_verified=false), 무인 자율성(model_autonomy_verified=false)을 완료하지 않았으므로 그 이상 주장하지 않는다.
- **별도 1세대 세션** 7746c2f00b154c6cbf28399fe4d11d60, 요청 1/완료 1. 다른 G350 원장의 기존 세대는 이 실험에서 수정하지 않았다. 전체 앱에는 새로운 독립 세션 증거가 추가됐다.
- 개발 데이터 QQQ RAW, 2020-01-02~2025-12-31, 1,508봉, 데이터 해시 328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6. Revisions not-as-of 및 corporate-action adjustment 미검증으로 독립 PIT/OOS 아님.
- **이번에 사용한 것은 기존 운영 AlgorithmPlan**이다. 새 P1-3 GeneralResearchPlan/StateMachine은 기존 MCP에 배포·등록되지 않았고 이 세대에서 실행하지 않았다.

## LLM 제출 계획
- Plan: volatility_switch_probe_01. Quiet: parkinson_variance <=0.0002, time_series_momentum weight 0.6 + sma_pullback_20 0.4, 최소 점수 0.59. Active: parkinson_variance >0.0002, previous_range_breakout 0.65 + range_low_reclaim_20 0.35, 최소 점수 0.6.
- Parent: 누적 **+35.9951%**, CAGR **5.2756%**, MDD **25.7017%**, 21 청산 완료 거래·43 fills, 승률 **33.33%**, 시장 노출 **60.81%**, 비용 **$342.0961**.
- 비교용 개발 QQQ RAW buy-and-hold: **+187.7724%** (동일 데이터 정책, 배당 재투자 및 PIT 미확증). 상대 성과 저조.
- Plan SHA: ab36b7808402f46cfe140017c0ebbb090be0b449940b3cfe87f524cd2f8eadb8.
- Strategy SHA: 66ce5bdb7c6b232ee42f65a4c4d7b756c78ee3a8e284fc64ee32a1ce3452dde4.
- Audit SHA: 72482de02bbd7ee0c200d3212f1895a9302dc36014642291a021ff30c9b79973.

## 실패 가설·반증 실험
- 모델이 참조한 실제 손실 거래 ID: 66ce5bdb7c6b-T-000016 및 66ce5bdb7c6b-T-000002.
- 미검증 가설: 한 개 지표의 가중표결만으로 진입하는 경우 매매 신호가 짧아진다. 진입/청산 점수 모두 0.8 이상(진입 >0.8, 청산 <=0.8)으로 강화하면 거래가 감소할 것으로 예측. 같은 부모/가격/비용 조건에서 S7을 수행했다.
- **관측은 예상 반대:** Parent 21회 / child 51회 청산, fills 43→102, 거래 이벤트 94건 변화. Child 최종 자산 **$9,589.159** 즉 **-4.1084%** (Parent +35.9951%); 거래비용 **$805.5502** (Parent $342.0961). **DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY**, 예측 반증.
- 동시에 entry와 exit를 바꾼 것은 복합 개입이다. 두 조건 중 어느 변화가 거래 증가·손실에 기여했는지는 이 실험으로 판정 불가. 다음 가설 검증은 entry-only와 exit-only를 분리하고 필요시 결합 조건도 별도로 조사해야 한다.
- S7 report/record SHA: e166bf2379e505634da6e33fc164421bc046769f3eb34ba6e902c26459551a5e.
- Gen-1 immutable evidence SHA: 60d7dd79a63a9768bd2d06aaa9bd21b11f5ed32ef331e898d84d33683502ad28.
- Controlled study scope: REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF, broker_executable=false, independent_oos_approved=false.

## 수락 및 미완료
- **PASS:** 연결 ChatGPT typed 제안 → 비용 반영 연구 백테스트 → 체결 근거 진단/후속 개입 계획 → S7 대조 재생 → 해시 근거 보존으로 **1세대 완결**.
- **NOT DONE:** 운영 P1-3 generalized plan 연결; 새 수식/상태기계의 실제 GPT 제출; 10/100세대 공정 random 대조, 운영 무인 자율성·복구, 모델 연결 독립 증명, PIT/OOS, 수익성, 실거래.
- 기존 OAuth/MCP URL, 32 tool, 주문 OFF 및 코드는 변경하지 않았다. 수정 리포 코드는 없고 이 문서와 진행 원장만 Git 커밋한다.
- 다음 고정 T4 단계: 인과 분리 실험 및 다세대 공정 random 기준 검증. P1-3 실제 모델 연결은 안전한 별도 옵션·테스트·운영 rollback 증거 확인 후 추진; 기존 단계 순서는 바꾸지 않는다.
