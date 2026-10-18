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
