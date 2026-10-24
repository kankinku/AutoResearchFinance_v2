# Quant AutoResearch — P5 신규 목표 100세대, 실제 GPT 체크포인트 G1~G10

**작성일:** 2026-10-24 KST
**단계:** T4(S4/S5) 실제 모델 연구를 수행하는 신규 격리 P5 세션. 사용자 요청으로 목표 100에 착수. **현재 실제 완결 10/100 / 나머지 90 미실행 / 무인 자동실행 아님.**

## 범위·수락 조건

- 원래 20문답 Q02/Q06/Q07/Q08/Q09/Q14/Q15/Q17/Q20. 자율 연구 엔진의 세대란 전략 설계, 정식 실제 비용·체결 재생, 구체적인 관찰ID 기반 모델 진단, 원래 부모와의 S7 paired 통제실험, 다음 세대를 위한 불변 증거 저장을 갖춰야 한다.
- 원래 V05→T4→V01~V04→V06→V07 순서 유지. 이번 요청은 **100세대 연구를 시작할 승인**이며 주문권한·PIT/OOS 게이트 완화 또는 미완결 세대의 100/100 승격 허가가 아니다.
- 연구세션: `3b44e05e52b3497db6fa035681ed0a5d`, `/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024`(운영/종전 P4와 분리). 현 상태 `AWAITING_PLAN` for generation 11, canonical cycle `AWAITING_PROVIDER`. 목표 100, 완결 10. 격리 파일 `p5_session_id.txt`를 유지할 것.
- 프로젝트·시장 데이터 원본 경로: `/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021` / `data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet`, QQQ 원시 비-PIT 1,508봉, 2025-12-31 개발 cutoff. 비용 1bp commission + 2bp spread + 5bp slippage, next-open. `orders_enabled=false`, `independent_oos_approved=false`.
- 새 세션 opt-in: `parent_portfolio_v2=True`, `generalization_parent_v1=True`, `p4_quality_gate_v1=True`, `p4_s7_quality_v1=True`; 서명된 외부 collector 부재로 `p4_model_capture_v1=False`. GPT 제공자 자체 모델 invocation ID/서명 영수증은 **없으므로** 독립적으로 프로바이더 API 호출 및 무인 자율 실행을 증명할 수 없음.

## 실제 GPT 설계·관측·S7로 검증한 10개 counted 세대

GPT가 매 단계 모델 맥락의 실제 전략 지표/관측된 손실 trade_id/decision_id를 확인하여 계획과 진단을 생성했고 이를 실 서비스와 동일한 `AcademicMCPCheckpointService`에 제출했다. `ScriptedResearcher`/랜덤 대조군/이전 100회 결정적 배치를 이번 세대로 재계수하지 않았다.

| G | 비용후 누적 수익률 | MDD | 청산 거래 | 노출 | S7 탐색 주제 |
|---:|---:|---:|---:|---:|---|
| 1 | +9.72% | 21.40% | 55 | 43.30% | 빠른 체결 재진입 감소를 위한 장기모멘텀 청산 |
| 2 | +61.43% | 27.79% | 7 | 65.72% | EMA20 조기 청산 부작용·큰 거래 증가 |
| 3 | +49.78% | 18.74% | 74 | 54.11% | 장기 모멘텀 추가 필터의 방어 효과와 수익 하락 |
| 4 | +62.12% | 22.89% | 23 | 66.05% | 고정 EMA overlay 무효 판정 후 장기 모멘텀 청산 |
| 5 | +7.49% | 14.08% | 48 | **3.78%** | 평균회귀 신호 즉시 청산의 낮은 참여율과 거래비용 |
| 6 | +31.68% | 29.16% | 26 | 57.63% | dual SMA 위험 필터의 수익/MDD 변화 |
| 7 | +7.60% | 22.28% | 34 | 48.08% | 장기모멘텀 exit 가설을 서로 다른 진입 구조에 재검증 |
| 8 | +52.95% | 24.19% | 106 | 56.43% | 돌파 즉시 청산과 거래 빈도의 비용 비교 |
| 9 | +33.48% | 16.92% | 26 | 46.09% | 장기모멘텀 지속 청산과 시장변동성 국면 |
| 10 | +58.29% | 24.91% | 22 | 65.19% | 장기모멘텀 위험 필터와 거래/낙폭 비교 |

- **정식 counted** 10/100, 상이한 StrategyIR hash 10/10, 모델 작성 진단/S7 실제 측정 10건, quality sidecar 승인 10건. **P4-3 `NO_OBSERVED_EFFECT` 거절 1건**은 G4에서 재시도해, 무의미한 실험으로 세대 소모하지 않았다. 참조에 없는 SMA 지표 사용 시도 1건도 컴파일 게이트가 거절했고, 같은 checkpoint 토큰으로 수정했다.
- **P4-1 부모품질 적용으로 적격 부모 미선정:** G1~G10의 모든 counted 전략은 새로운 AlgorithmPlan이며, `inherited_strategy_ir` 실측 **0**. G9/G10도 `NO_VERIFIED_PARENT_FALLBACK_ALGORITHM_PLAN`로 진행했다. 10건의 실측 S7 모두 독립 원본/자식 비교를 완료했으나 자동 계승이 검증되었다고 표시하지 않는다. 향후 왜 quality 적격 부모가 생성되지 않는지 따로 진단해야 한다. 최소 거래/노출·원장/해시 기준을 억지로 완화하지 말 것.
- **최고 실제 counted G4 +62.12%**이지만 거래 23건 및 독립 OOS 없음. G5는 시장노출 3.78%에 불과하므로 낮은 MDD로 좋은 부모라고 판단하면 안 됨. 비교군 QQQ 비용후 단순보유 +187.77%에 **0/10** 우세. 사후 측정 S7 자식 수익(예: G4 +116.99%)은 정식 추가 세대로 계수하거나 독립 검증됐다고 주장하지 않음.
- 이전 `get_research_batch_status`의 2026-10-23 100/100은 **`external_gpt_plan_local_deterministic_worker`**(고정 intent), 이전 report `adaptive_applied_generations=0`, `adaptive_replanned_generations=0`, 45세대 duplicate skip. 이 세션/결과를 오늘 새 GPT 100세대로 대체하거나 합산하지 않았다.

## 격리 감사·복구

현재 측정 후 service `get()` 원장 완전검증:
- counted 10건 및 S7 품질 승인 10건, 동일 전략해시 중복 0, `history.previous_evidence_hash` 전부 이전 세대 Evidence를 정확히 참조, `p4_s7_quality_audit.rejection_count=1`.
- 마지막 G10 Evidence SHA `211a28bfe98da53f36a41a764f0101d2d45b6b32fd78592dd07353e6bb5d68db`.
- 새로운 독립 작업상태 `academic-gpt-checkpoints/cycles.sqlite` SHA256 `7c86f8fdd39d640cbc79aba036094ae880627c0cb8f49cd33daedad7b017d37a`, `gateway.sqlite` SHA256 `26872675b96628c6034772d8f346ada9be0f5bee090088e62c1641abdd0a1eed`, `catalog-s6-v2.sqlite` SHA256 `65a8a35cda78d18022fe0b35b5d1db4344ce24d52daf09fd9f91cabf15db6e97`; SQLite `PRAGMA quick_check=ok` 세 DB.
- 기존 P4 열 세대 `/shared/moon-workspace/AutoResearchFinance_v2-p4-rehearsal-20261024/p4_verified_report.json`와 이전 verifier 재실행 JSON **정확히 동일**; 보고서 SHA `22024e6871c0f905b7afc182bc8837acab9bd79d9f86510a8e635efdee813aeb`. 이전 운영 68/100 세션/OAuth/MCP fixed URL/대시보드 DB에 이번 작업 쓰기 없음. 교차 프로세스에 의한 변경 여부는 별도 확인하지 않았다.
- 관련 provenance·S7·부모선정·거버넌스·academic cycle 테스트 **37 PASS**, 전체 repo tests/mypy **NOT RUN**, 운영 서비스에 새 코드 배포 없음. 작업 문서만 GitHub 저장하며 SQLite/원시 데이터/API 키/git credential은 업로드하지 않음.

## 남은 90세대와 게이트

현재 모델 인터페이스는 각 세대에 **별도 모델 작성 plan과 근거있는 diagnosis 제출을 요구**한다. 실제 외부 모델 공급자 invocation의 자동 호출·signed proof가 없는 상태이며 한 번의 결정적 로컬 배치를 실행하는 것은 원래 Q17 `세대 ≠ 백테스트` 위반이다. 따라서 사용자가 요청한 실제 목표 100세대는 **진행 중(10/100), 완료 NOT ACHIEVED**. 이번 응답에서 완료하지 않은 90세대를 완료/실행 예정이라고 단정하거나 백그라운드 실행 중이라고 주장하지 않는다.

다음에는 이 **동일 세션**의 G11 `AWAITING_PLAN`에서 이어가되 **적격 부모가 없는 실질 이유**를 원장 품질 게이트의 실패 이유로 먼저 확인한다. 필요한 경우 적격 후보가 생성되는지 연구가설로 검증하되 선별 기준을 약화하거나 동일 전략을 재포장하지 않는다. 외부 OAuth 등록/URL 재발급·실거래/PIT-OOS 접근 금지 유지. 독립 모델 프로바이더 영수증 및 새로운 사전 봉인 자료 미확보 사실을 보존한다.
