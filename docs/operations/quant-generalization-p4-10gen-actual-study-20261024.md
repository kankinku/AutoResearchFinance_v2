# Quant AutoResearch P4 — GPT 작성 계획 기반 신규 연구 10세대 실제 실행·검증 보고서

**작성:** 2026-10-24 KST
**판정:** **P4 기술 통합 PASS / 투자 연구 품질 게이트 FAIL / P5 100세대 확대 보류**
**참조 설계:** [일반화 평가 및 세대 연구 v2.0](quant-generalization-research-v2-implementation-20261024.md), [P3-B 출처·계승 검증](quant-generalization-p3b-s7-scoped-integration-20261024.md).

## 1. 실제 수행 (MOCK 아님, 운영과 분리)
- 연구 세션: `2d86df1adb5945259c1b95e394d6a78a`; 목표·완료 세대 **10/10**, `status=COMPLETED`, `checkpoint_phase=COMPLETED`.
- 독립 상태 폴더: `/shared/moon-workspace/AutoResearchFinance_v2-p4-rehearsal-20261024`; 운영 root와 분리된 경로에 새 `cycles.sqlite`, `gateway.sqlite`를 생성. 원래 학술 catalog만 SQLite read-only backup으로 복제. 인증/OAuth/MCP 재등록, 기존 가동 세션 `14626d55fb2b461faa485df911920071`(68/100), 대시보드·실주문 기능에 변경 없음.
- 개발 데이터: QQQ 2020-01-02~2025-12-31 RAW 비-PIT 일봉 1,508개; dataset hash `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`. 2026 데이터는 학습/진단/OOS 테스트에 사용하지 않음.
- 정책: `parent_portfolio_v2=True`, `generalization_parent_v1=True`, 명시적 `generalization_enrollments`(1행), 거래비용 `academic-research-cost-v1`, 다음 봉 시가 체결, `orders_enabled=False`, `independent_oos_approved=False`.
- **실제 GPT가 이 채팅을 통해 작성한** G1~G8 각각의 `AlgorithmPlan` 및 S7 진단과 G9~G10 `InheritedResearchIntent` 및 S7 진단을 2단계 MCP-compatible checkpoint service에 제출. 모든 단계의 진단은 엔진이 측정한 loss case/trade_id/decision_id를 관찰한 후 작성함. Python 고정-rule `ScriptedResearcher` 시뮬레이션은 사용하지 않음.
- **프로비넌스 한계:** 각 세대의 immutable evidence에 별도 `model_invocation_id`, LLM provider 영수증, prompt/response signed receipt는 없음. 따라서 독립 제3자가 모델 호출 주체를 원장만으로 인증할 수 없음. `GPT_AUTHORED_CHAT_TOOL_SUBMISSIONS_NO_INDEPENDENT_MODEL_CALL_RECEIPTS`로 표시. 완전 자율적인 별도 LLM 에이전트 가동 증명이라고 주장하지 않음.

## 2. 재현된 실제 비용후 연구 실측

| GPT 세대 | 전략 개선 가설 / 실제 실험 | 누적 수익률 | MDD | 완료 거래 | 시장 노출률 | S7 결과 |
|---|---|---:|---:|---:|---:|---|
| G1 | 변동성별 EMA/모멘텀 vs 돌파 | +13.00% | 32.53% | 79 | 48.67% | 방향 일치 |
| G2 | 저·고변동성 진입 이중 확인 | +19.79% | 20.82% | 64 | 44.16% | 방향 불일치 |
| G3 | SMA20 추세 국면 분기 | +9.72% | 21.40% | 55 | 43.30% | 체결 변화 없음 |
| G4 | 상승장 눌림목/약세 반등 | +2.10% | 7.43% | 27 | 2.19% | 방향 일치 |
| G5 | 저변동성 EMA 진입 완화 | +13.36% | 30.65% | 76 | 50.00% | 방향 일치 |
| G6 | 상승 추세/약세 반등 분리 | +36.74% | 26.44% | 62 | 52.19% | 체결 변화 없음 |
| G7 | 장기 모멘텀·SMA50 보유 신호 | **+44.77%** | 30.92% | 15 | 70.42% | 방향 일치 |
| G8 | 변동성별 중기 추세·돌파 확인 | +33.95% | 35.36% | 60 | 53.65% | 방향 일치 |
| G9 | **G8의 감사된 S7 자식 계승**, 고변동성 진입 강화 | +32.88% | 34.96% | 58 | 52.72% | 방향 일치 |
| G10 | **G9 정식 세대 계승**, 실험 결과에 따라 과도한 변동성 필터 제거 | +36.41% | 35.22% | 58 | 53.45% | 방향 일치 |

- 개발 데이터 동일 비용 기준 QQQ buy-and-hold: **+187.77241%**, MDD **35.61722%**.
- GPT 연구 후보 10개 중 QQQ 누적 수익률 초과 **0/10**.
- 최고의 **누적 수익률** G7 (+44.77%, MDD30.92%): QQQ보다 큰 저성과, 거래 완료 15건이라 추정력 제한. 이 값을 `발견된 최고 수익 알고리즘`으로 과장하지 말 것.
- 최저 **MDD** G4 (7.43%)는 노출률 2.19% 및 수익률 +2.10%로 낮은 위험이 실제 강건한 투자성과를 뜻하지 않음.
- 모든 실측은 전체 개발 데이터 반복 탐색의 **EX-POST DEVELOPMENT**, 2026 독립 OOS 아님. QQQ 원시 가격 비교는 배당 재투자된 총수익률 벤치마크가 아님.

## 3. 실제 S7·계승 기술 검증
- 정식 generation Evidence **10건**, 서로 다른 StrategyIR 해시 **10개**, 검증된 S7 Experiment Report **10개**.
- S7 `DIRECTION_MATCHED_DEVELOPMENT_ONLY` **7건**, `DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY` **1건**, `NO_OBSERVED_EFFECT` **2건**. 같은 체결·무효 S7 실험을 성공으로 계상하지 않음.
- 원본 G8 S7 `p4_g08_highvol_branch_ablation` 자식의 signed lineage/지표 벡터, 비용·실거래 next-open 재생 및 2021~2025 ex-post 평가를 증거로 G9 부모 선정. 부모 종류 `COUNTED_S7_CHILD`, 원천 세대 8, selection hash `de37d1b69688fe6bdd4c826faf9849a2a5c6ceea6b14c981d56c674af55ade89`, P3 study receipt `6072f0def09a9a8e84b876b9630a05fc027bc19fb7e01b00c53e32de36c6a91f`.
- G10 부모는 **정식 G9** (`COUNTED_GENERATION`), selection hash `8fa25dfebbf493bfeb69c21cadbeff95b12ad0fa866ae0002c1bcb3e202e0b0f`; P3 receipt `0043b3be5bd9faeb14d978c8d2da9b75026ef90549b0d364f785cdb90f6da4a9`.
- 기존 실험에 없는 자식 Rule Path를 사용하거나 G10 원본 체결을 바꾸지 못한 추가 필터 제안은 **세대 소모 없이 검증 단계에서 거절**되어 올바른 진단/구조로 수정해 재제출했다. S7 목표 `exposure`는 스키마상 보이지만 submit 지원 범위에 없어서 `trade_count` 등 허용 지표로 수정 제출함. **지원되는 metric 집합을 계획 안내와 응답 스키마로 일치시키는 UX 수정 필요**.
- 계승 활성화 전 G1~G8에서는 source 후보가 내부 검증 적격성이 없어 독립 typed AlgorithmPlan으로 연구됨. G9/G10에서 진짜 P3-B scoped parent path가 작동함. 기존 세션에는 새 policy를 retroactively 적용하지 않았음.
- 별도 `scripts/quant_p4_verify_10gen.py` 읽기 기반 재감사 도구 구현. `p4_verified_report.json` 결과 digest `22024e6871c0f905b7afc182bc8837acab9bd79d9f86510a8e635efdee813aeb`와 데이터·S7·선정·DB SHA 포함.

## 4. 원장 불변·복구 식별자
- 신 연구 `cycles.sqlite` SHA256 `2818eb153fe320c77b974112b8801414e283f42ba5024dfc268e39c3ef7fcc8d` (`quick_check=ok`).
- 신 연구 `gateway.sqlite` SHA256 `7925fc5934cac4eaa049432cd92b89a705b3b745ff046a8a4f73711319f91fa0` (`quick_check=ok`).
- 신 연구 원본 학술 `catalog-s6-v2.sqlite` SHA256 `478fe89ca8c3a9daf8f61f83a7b3118f52c716ef61527ed92abcd42e280e2de1`.
- 마지막 G10 Evidence hash `a18a97f5f6d5d5ac9afc3007291fe655fa28af3be38ae09445e298e618797241`.
- 운영 원장 (`/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/state/moon-http/research/academic-gpt-checkpoints`): `cycles.sqlite` SHA `565a82d6821996044a691a562e324b9d4e5cc451739fe57650a2346d1efb9027`; `gateway.sqlite` SHA `aa5d2e9276b8fb8bf3519d0f7bf2e5ed2967867d42c7d52993280dfd7c1ff7c9`. **원본 증거 불변**.
- 운영 기존 GPT 연구 세션 68/100 별도 유지. 실거래/OOS 승인 FALSE, 2026 data 공급자 준비 미확인.

## 5. P4 평가 및 P5 진입 게이트
**기술적으로 증명됨:** 신규 격리 세션에서 실제 GPT 작성·진단 입력 → 비용 포함 backtest → S7 원장 → 동일 원본 S7 자식 검증 → P3-B 부모 선정 → 다음 세대 IR 변형 → parent Evidence/해시/복제까지 연결.

**증명되지 않음:** 투자 효용, 발전세대가 지속적으로 QQQ나 동등 위험/노출 벤치마크를 초과, 완전 자동 LLM 호출 provenance, 2026 미노출/미래 데이터 일반화 성능, 사용자의 실계좌에서 실행 가능성.

**다음 우선 작업(100세대 확대 전):**
1. **P4-1 연구품질:** 시장 노출률 2.19%처럼 사실상 현금인 전략을 MDD만으로 좋은 후보로 올리지 않는 사전 적격성 기준 및 QQQ 위험/노출 정합 비교. 개발 원장 단계별 부모 선정이 단순 재최적화에 빠지지 않는지 더 자세한 S7 실패/성공 원인 로그 제공.
2. **P4-2 GPT provenance:** 독립 모델 요청/응답 ID, prompt/context hash, 모델·추론 호출·수정 의사결정 로그를 별도 불변 체인에 연결. 실제 모델 호출 증거를 미수집할 때는 자동 진화라 부르지 않음.
3. **P4-3 S7 계약:** DiagnosisResponse에 exposed `exposure`가 실제 지원되지 않는 오류 등 모델 계약·gateway 사전검증 통일, 무효/중복/동일체결을 GPT가 명확히 진단하게 설계.
4. **P4-4 성능/시장일반화:** 개발 시장 기간별/PIT 분리 워크포워드와 비용 2배/슬리피지·거래 수의 현실성을 확인. 이미 노출된 2026은 최종 독립 시험으로 재사용하지 않음.
5. **P5 고지:** **현재 신규 100세대 실행은 보류 권고.** 기술적 게이트 PASS만으로 잘못된 전략 평가 함수를 100회 반복할 이유가 없음. P4-1~4 보강 후 새 진화 세션을 사전 잠금하고 시작.

**실험 DB 자체는 git에 포함하지 않으며**, `/shared/moon-workspace/AutoResearchFinance_v2-p4-rehearsal-20261024` 상태 폴더에 유지. Git에는 보고서·읽기 검증 도구·진행표만 저장한다.
