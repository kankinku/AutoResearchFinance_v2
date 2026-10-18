# T4 P0-5 — 동일 예산 3-arm 비교: 사전 고정 원장

기준 2026-10-19 KST. 기존 20문답/계승/원장·모델 API·주문 차단 계약 변경 없음.

## 먼저 고정한 연구 조건 (아직 성과 측정하지 않은 상태)

- Source session `c1eadd67bad94d7ea182dc274224dbce`, generation **25**, canonical original SHA `319ed66048ab152515305db45cddc92d94320e0272d1d348d3e4a394749383b6`. Existing source has 53/100 completed and is NOT advanced by this research. No source DB write or production restart.
- Source: verified 2020-01-02~2025-12-31 **non-PIT QQQ development** dataset, same hash as canonical G25, catalog `catalog-s6-v2.sqlite` copied in temp, recompiled StrategyIR identity and original fills/costs audit verified prior to freezing. Same strategy parent, fee model and bars for all three arms.
- Exactly **five** saved, externally proposed client model research intents (one change per candidate) vs **five** seeded uniform random control proposals vs **five** deterministic 5% local threshold control proposals. Total **15** backtests + one shared parent. `GPT_HISTORICAL` is legacy engine's arm name; this turn's source is **`DECLARED_CHATGPT_CLIENT_UNVERIFIED`**, not an authenticated model identity nor proof of independent causal GPT reasoning. All arms constrained to one supported entry/exit numeric rule mutation; this does NOT test model freedom to design new multi-regime algorithms.
- Random seed `20261019`. Frozen **before any arm outcome was measured**. Plan SHA `dfecd3dfee1143d62a1dedd4b3af0bf10e28a9ea3d8720110dd2ec160a9d2376`; complete manifest at [frozen plan](evidence/t4-p05-g25-fixed-5x3-20261019/fixed-budget-frozen-plan.json).
- Hypotheses are guided by **already-known prior development data** (G25 original lost 3.37% with ~6.96% exposure / 59 completed trades, and earlier S7 tested confidence tightening). Even if this specific 15-candidate manifest is frozen before its results, it is NOT a blinded or independent pre-registration of the entire research pipeline. Do not call it statistically established GPT superiority.
- Existing code `research/llm/fixed_budget_arms.py` reused. A pre-evaluation discovered that the **random/local candidate generator tried to REPLACE_RULE a `regime_filters.0` path**, which the typed intent bridge correctly rejects. Corrected by restricting BOTH model and controls to the same supported entry/exit numeric condition coordinates; no mutation engine change, hidden retries, or evaluation budget inflation.
- Evaluate score only *after* frozen source and code are committed and pushed; no tuning/resampling allowed on results. Negative outcomes and same-fill candidates count towards each arm's allocated 5 slots.
- Original MCP OAuth URL, 32 exposed tool registrations, live trading OFF, canonical database, PIT/OOS gates and runtime checkout `54a515f` remain unchanged.

## Scoring / next remaining acceptance criteria

Run frozen manifest through the existing canonical 3-arm scorer. Record all 15 results, same-fill/no-effect candidates, cost/return/MDD/exposure/trades/QQQ gap, side-by-side arm means and the full result hash. Each arm gets the same backtest count, **not necessarily equal total compute or GPT token budget**. Multiple seeds and honest GPT model provenance, changing parents, independent unseen markets and generalizability remain future work. This study alone cannot authorize resume of the pending 47 T4 counted generations.

## 1차 5×3 파일럿의 반증 — 결과를 폐기하지 않고 보존

사전 등록 SHA `dfecd3df...` 고정 및 Git SHA `1260266` Push **후** canonical scorer를 실행. 기록 보고서 SHA `dbc733184124f5431c9f256f13053b2b1870b462a9556f390d9a7ee60df9acb1`, [전체 15 trial](evidence/t4-p05-g25-fixed-5x3-20261019/fixed-budget-results.json).

| arm | 평균 costed 수익 | 평균 MDD | 실제 거래 변화 없는 후보 |
|---|---:|---:|---:|
| 모델 제안(`GPT_HISTORICAL`, 인증되지 않은 레이블) | −0.5714% | 18.4639% | 0/5 |
| 무작위 | −3.3687% | 6.5632% | **5/5** |
| 국소 변형 | −3.3687% | 6.5632% | **5/5** |

결론: **이 비교는 통제군의 탐색 공간이 잘못 설정되어 GPT 우월성을 평가할 수 없다.** 기존 control `_eligible_thresholds`는 `plan_entry` 같은 이진 신호 자체의 numeric threshold를 변경한다. 이 값이 0 또는 1이므로 0.1~0.9 사이 이동해도 동일 체결인 반면 모델 제안군은 `plan_vote_score`라는 연속형 신호로 바꿨다. 이는 제안군에게 일방적으로 효과적인 변형을 허용한 불공정 계약이었다. 비교 코드/비용 엔진과 원장은 정상 작동했고, 실패 결과는 숨기지 않으며 15개 평가를 연구 예산 소비로 보존한다.

**후속 진단용 2차 비교**에서는 동일 5개 GPT 후보를 그대로 고정해 재사용하고 무작위·국소 군의 결정 공간을 사전 정의된 `plan_vote_score` 대치로 바꾸어 공평한 변경 가능성을 부여한다. 첫 15개 결과는 이미 관찰됐으므로 2차 비교도 완전 전향/블라인드가 아니며 통계적 GPT 우위 입증에 사용할 수 없다. 임의 재시도/성과 기준 시드 교체는 하지 않는다.

## 2차 비교 — 공통 연속형 투표 점수 대조군, 두 번째 **사전 고정**

1차 실패를 확인한 **후** 비교기에서 기존 레거시 제어정책을 삭제하지 않고 opt-in 정책 `PLAN_VOTE_SCORE_MATCHED_COORDINATES_V2`를 추가했다. 모든 arm의 제안은 정확히 **한 개**의 `entry.conditions.0` 또는 `exit.conditions.0` 조건을 연속형 `plan_vote_score`로 교체하며, 수량·신호 계산기·가격 구간·체결/수수료 모델은 같다. Random 5개는 `seed=20261019`로 0.35~0.90 점수에서 1회씩 샘플하고, local 5개는 원래 vote threshold 0.50 주변의 미리 고정한 ±0.06 단계 탐색이다. 후보가 무효하거나 부모와 같은 실제 체결을 발생시키더라도 해당 예산은 소비된다.

- **사전고정 2차 SHA:** `4dee7c596effe61a79bf9f66343d54230db4c884767fc6d80b265ce3ee373336` ([2차 frozen manifest](evidence/t4-p05-g25-matched-5x3-20261019/fixed-budget-frozen-plan.json)). 1차 source G25 / GPT 제안 5개 / 난수 시드는 모두 그대로. 각 GPT strategy hash 및 intent 원본의 byte-equivalence를 회귀 테스트로 확인.
- 1차 결과를 이미 확인한 시점에 **대조군의 작동 범위를 수정**했으므로 2차는 **1차와 결합해 사후 설계 수정이 발생한 개발 교정 실험**이다. 모델군의 실제 판단 출처는 `DECLARED_CHATGPT_CLIENT_UNVERIFIED`이며, 2차에서 숫자가 높더라도 자율 GPT 우월성을 입증하지 않는다.
- 기존 G179 3-arm 레거시 frozen policy가 동일하게 재생되는지 테스트해 이전 자료를 파괴하지 않았다. 새 정책의 실제 후보/원장 모든 항목을 평가 **전에** Git에 Commit·Push한다.

## 2차 동일 탐색 공간 실측 결과 — 후보 교체 없음

2차 완전 manifest SHA `4dee7c596effe61a79bf9f66343d54230db4c884767fc6d80b265ce3ee373336`를 **커밋 `271953d` 및 Push 완료 후** `score_frozen_budget`으로 15개 모두 평가했다. 비용 포함 고정 결과 SHA **`ec6fa28bffe4ac6ceb28fd9059e04cef5c27471a7b1edd947fe6d70333b17b19`**, [모든 15개 trial](evidence/t4-p05-g25-matched-5x3-20261019/fixed-budget-results.json). 같은 5개 모델 제안 strategy SHA·intent는 1차 결과와 완전 동일하며, 대조군 정책만 교정했다.

| 공통 G25 부모 및 arm | 평균 costed 누적 수익률 | 평균 MDD | 평균 노출률 | 평균 수수료($) | 부모 대비 이익 후보 | 원본과 체결 완전 동일 |
|---|---:|---:|---:|---:|---:|---:|
| G25 원본(공통 baseline) | −3.3687% | 6.5632% | 6.9629% | 926.43 | 해당 없음 | 해당 없음 |
| 모델 제안(`GPT_HISTORICAL`, 선언만 한 GPT) 5회 | **−0.5714%** | **18.4639%** | 20.9682% | 1,408.89 | 3/5 | 0/5 |
| 동등 연속형 점수 난수군 5회 | −15.6944% | 27.5394% | 22.5464% | 2,615.40 | 1/5 | 1/5 |
| 동등 연속형 점수 국소군 5회 | −6.7518% | 26.7762% | 23.4483% | 2,049.60 | 2/5 | 0/5 |

- **모든 arm에서 `no_worse_mdd_and_better_return = 0`**. 원본 대비 위험 개선과 수익 개선을 동시에 달성한 후보는 하나도 없다. 모델 제안군의 평균 수익은 대조군보다 높지만 **절대 평균 수익은 여전히 음수**이며 G25 원본보다 평균 MDD가 높다.
- **개별 최고**: 모델 제안 +20.025%(MDD 10.09%, 완료 거래 22), 난수/국소 양군 +37.782%(MDD 10.09%, 완료 거래 19). 전자는 같은 equity/fills로 되풀이되는 점수 변경 두 개이며, 후자는 30개 완료 거래의 기존 기준을 충족하지 못함. 따라서 단일 최고치 비교로 수익 알고리즘 승격 불가.
- 연구 기간 QQQ 동일 raw-price·일회매수 비용 포함 buy-and-hold는 **+187.7724%**, 위 후보 전부 하회. 배당 재투자/실질 PIT/OOS/보유 이자 또는 실제 체결 가능 여부는 이 값에서 증명되지 않음.
- 세 arm의 backtest budget은 **각 5**, 통일된 종목·기간·원본 전략·비용/수수료 계산·평가 스크립트를 사용. 다만 모델의 입력 해석·반복 사고 시간, GPT token 비용, 기존 과거 연구에서 사용한 숨은 탐색 예산 및 연구 공간 자유도는 동등하지 않다. **`model_identity_verified=false` 및 `statistical_superiority_established=false` 유지.**
- 기존 레거시 파일럿의 무작위/국소 10개 no-op은 **대조군 연산 설계 결함**이었음을 정확히 기록했고, 첫 단계 결과를 삭제하거나 통합 평균에 넣지 않았다. 이 2차 비교는 이미 1차 결과를 본 **사후 교정 연구**이므로 독립 사전등록이나 GPT 효능 우월성의 통계적 검증이 아님. 추후 다중 부모·여러 seed·모델 연결 증거·독립 시계열 구간 검증 전에는 기존 53/100세대 연구를 무인 승격하지 않는다.

## 재현성과 회귀 범위

- `tests/research/test_t4_p05_matched_budget.py`: 새로운 V2 정책 후보가 실제 연속 신호를 사용하며 기존 V1 레거시와 공존, 사전등록 정책·모델 출처 위조 거부, 5개 모델 제안 의도 재사용 동일성 검증.
- 원본 QQQ 53세대 **읽기 전용 SQLite**, 임시 catalog 복제, frozen plans 2개를 다시 canonical backtest하여 리포트 SHA와 trial 전체 동일성·동일체결 개수(1차=10, 2차=1)를 비교하는 golden E2E 테스트 추가. 기존 부모 계승·경제성/LLM 출처와의 회귀를 별도로 확인한다.
- 신규 개발 파일/리포트는 `feat/quant-t4-p0-5-equal-budget-20261019`에만 추가; **운영 53/100, parent selections 0, 계승 lineage 0, orders OFF, URL/OAuth/32개 도구 및 운영 고정 SHA 유지**. 연구 데이터셋 외부 다운로드, 모델 API 호출, 무인 추가 연구 수행하지 않음.

### 다음 확정 과제

P0-5는 기존 비교기의 **동일 평가 예산·실제 체결 변화 확인·연구군 출처 제한**까지 검증한다. 이것이 20문답의 독립적 GPT 자율 연구 검증 완료는 아니다. 다음에는 GPT가 각 세대의 정확한 원인·증거를 읽고 자유롭게 새로운 규칙을 작성했는지 실제 authenticated MCP 호출로 몇 세대 종단 간 시험하고, 모델 출처의 미인증 상태와 외부 증빙 가능 여부를 그대로 기록한다. 동예산 비교 역시 여러 사전등록 seed/부모 및 OOS가 필요한 한계를 가진다. 원래 47세대는 **실행하지 않았다**.

## 기존 P3-1/G179 사전 고정 보고서의 역호환성 검증

2026-10-17 P3-1에 이미 고정된 G179 parent/source manifest는 현재 추가된 `research_origin` 필드가 없다. P0-5의 새로운 출처 메타데이터를 강제하면서 과거 freeze/report의 SHA가 달라져서는 안 된다. 이에 다음 **읽기 전용 archive compatibility**를 최소 복구했다.

- 과거 버전 manifest는 **모델 출처 필드가 모두 없는 완전한 옛 형식**과 레거시 제어정책일 때만 허용하고, 해시·parent·시장 자료·후보·seed는 기존대로 엄격 검증한다. 출처를 VERIFIED로 소급 표시하지 않는다.
- 과거 후보 재생은 과거 `_eligible_thresholds`의 regime 인덱스 포함 후보 좌표순을 그대로 보존한다. P0-5 이후 신규 frozen manifest는 유효하지 않은 regime REPLACE_RULE 후보를 제외한다. 두 가지 의미를 자동으로 섞지 않는다.
- 실제 phase1-20261017-1950 **읽기 전용 archive**의 G179(세션 `2ba41aaeacd547319cfbf7e6f266ad11` / 79세대)를 임시 catalog 사본에서 비용 포함 전량 재컴파일하고, 기존 `fixed-budget-frozen-plan.json` SHA **`197bfe93...`** 및 **기존 최종 결과 SHA `0ea16cb21fbfec26533a0ade5a9e739cf8142e8c80250444a41922c8dda3b567` 완전 동일** 확인. `tests/research/test_t4_p05_matched_budget.py` golden test로 회귀 고정.
- 새 G25 1차 manifest SHA `dfecd3df...`와 교정 2차 SHA `4dee7c59...` 역시 그대로 읽고 스코어 재생 결과가 각 Git 저장 리포트와 완전히 일치하는지 테스트한다. 과거 해시를 변경하거나 기존 원본 세대를 수정하지 않았다.

## 최종 P0-5 관련 회귀 결과 및 종료 경계

- 저장소 전체 Ruff **PASS**, Mypy **279 source files PASS**.
- 실제 기존 G25 원장·1차/2차 5×3 frozen manifest·후보 backtest 전량 다시 산출해 각각의 원본 `report_hash` 및 결과 JSON 전체 동일성 검증, 과거 10/17 G179 frozen/report의 완전 동일성 검증까지 포함하여 **64 tests PASS / 0 FAIL (67.13초)**. 범위: fixed budget, P0-4 경제성, P0-3 출처, P0-2B 부모 계승, MCP 세션 및 범위 잠금. 전체 Pytest(약 1,700개 이상)를 별도로 실행한 것은 아니므로 전체 회귀 통과를 주장하지 않는다.
- 원본 연구 DB의 `cycles.sqlite`와 `gateway.sqlite` `PRAGMA quick_check=ok`, 세션 **53/100**, S7 report **53**, 부모 선택 **0**, 계승 계보 **0** 모두 동일. 실제 counted 세대 추가 **0**. 사용자 OAuth·MCP URL·주문 가능 상태·운영 pinned SHA는 변경하지 않았다.
- 사용자에게 보고할 확정 판정은 **동일 후보 backtest 예산 아래에서 연구 모델 제안군의 상대적인 기술통계 이득은 관측됐지만, 그 결과를 근거로 자율 GPT 연구 또는 GPT 우위/실전 수익성이 입증됐다고 결론내릴 수 없음**이다. 대조군 설계 교정 시점이 모델 결과 관찰 이후였고, 재사용된 비PIT QQQ 동일 기간·단일 부모·미검증 모델 origin·낮은 표본/다중검색 효과가 있기 때문이다.
- 다음 작업은 **새로운 연구 방식 개발보다 이미 보존된 모델 호출 provenance와 실패 원인 입력을 실제 GPT가 사용했는지 확인하는 절차**에 집중한다. 동일 예산 다중-seed/다중-parent, 독립 PIT/OOS, 후보의 리스크·수익 동시 개선 확인 전에는 T4 남은 47세대의 완전 자율 완료를 선언하지 않는다.
