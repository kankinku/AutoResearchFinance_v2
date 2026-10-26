# Quant AutoResearch — 증거 보존형 연구기억·압축·자율진화 통합계획 v2

- **기준일:** 2026-10-26 KST
- **상태:** `DESIGN_APPROVED_FOR_RESEARCH_PLANNING_ONLY`, 운영·모델·OOS·실거래 승인 아님
- **기준 소스:** `feat/quant-unified-mcp-20261026`, 기존 ChatGPT ↔ Quant MCP 직접 연구
- **ID:** `T4-P2-F4-F5-EVIDENCE-MEMORY-ARCH-20261026`
- **연결 ADR:** `docs/decisions/2026-10-26-quant-checkpoint-handoff-resume-architecture-v1.md`
- **결정:** 연구 증거는 **절대 압축 삭제하지 않고**, 원장으로부터 재생성 가능한 **유형화된 연구 기억·쿼리별 인계서**를 사용한다. 고정 8천 자로 모든 연구를 축약하거나 중요도를 GPT 감으로 정하지 않는다. **개발 세대 판단의 질이 보전되는 최소 문맥**을 실증적으로 선택한다.
- **잠금:** 기존 32개 MCP 도구, OAuth/고정 URL, 이전 모든 세대·해시, `orders_enabled=false`, 봉인 OOS, P4 공급자 증명/모델 감사, 사용자 확정 Q01–Q20 및 V05→T4→V01–V04→V06→V07 개발/승인 순서 변경 금지. 오직 계획 기록. SDK는 상태·예산·재개만 담당하며 새로운 전략을 독립적으로 판단하지 않는다.

## 1. 무엇을 개선해야 하는가: 실측과 오해 제거

2026-10-26 기존 운영 Quant의 `get_algorithm_research` 읽기 전용 응답: **68/100 `AWAITING_PLAN`**. `JSON.stringify`에 해당하는 직렬화 **문자 길이 기준** 전체 **664,081자**, `history` **548,966자**, `model_context` **113,581자**, 최근 generation 행 약 **8,147자**. 실제 입력 토큰/요금·UTF-8 바이트와 혼동하지 말 것. 새 research context를 GPT에 전달하는 비용 비교의 **정상 기준은 113,581자**이며, 전체 status payload 664,081자가 매번 모델에 그대로 들어간다고 가정하지 않는다.

현재 모델 문맥 주요 길이(문자, 수치 측정치): `cross_generation_memory` 29,614; `loss_attribution` 18,211; `experiment_learning` 17,084; `feature_weakness_guidance` 10,096; `prior_research` 9,183; `economic_feedback` 8,185; `inherited_research_intent_schema` 5,975; `trade_cohort_review` 3,407. **중복 증거와 서술은 많지만 위험한 실패·희귀 국면·실측 거래 정보도 섞여 있다.** 단순 앞부분 자르기, Markdown 1페이지, 상위 수익률만 요약하면 부정확한 가설 반복, 부적격 부모 재선정과 설명 환각이 증가할 수 있다.

기존 코드 재사용 범위: `research/llm/cross_generation_memory.py`는 불변 S7 해시와 부모별 정확한 개입 fingerprint/변형 family, 실비용, inactive/반복 손실을 분리; `experiment_learning.py`는 반증/무효 거래와 다음 실험 설계; `economic_feedback.py`, `adaptive_direction.py`는 S8 지침; `parent_portfolio_v2.py`는 검증 부모 frontier; `loss_attribution`, `trade_cohort_review`, F1/F2는 손실·특성 연결. 현재 `application/academic_checkpoint_service.py::_context`가 이 결과를 **전량** 모델 문맥에 넣으며 F3 실측 기여도는 아직 자동 장기기억 F4로 연결되지 않는다. 개발용 V3 sidecar는 별도 선택 연결. 신규 문서는 이러한 기존 안전 근거를 절대 약화하지 않는다.

구별해야 할 세 가지: **① 원본 증거 보존율 100%, ② 인계서 정보 충실도는 실증 지표, ③ GPT 입력 크기/토큰 비용은 별도 최적화 목적.** ChatGPT의 가중치를 재훈련하는 시스템이 아니라 *검증된 관측과 연구 정책을 외부 기억으로 계승해 후속 의사결정을 개선*하는 구조다.

## 2. 계층형 기억 구조 — 데이터 중복 방지

| 계층 | 무엇을 보관하나 | 형식/유효기간 | 보존 및 안전 |
|---|---|---|---|
| **L0 Canonical immutable evidence** | 원본 S2 체결/코스트/지분곡선/전략IR/분석/진단/S7/해시/부모/시장 데이터 스냅샷 | 기존 SQLite·불변 해시/아카이브, 연구 수명 전체 | **손실 압축 금지**, 삭제·덮어쓰기 금지, PIT/OOS 접근 권한 별도 |
| **L1 Generation event** | 한 세대 `goal→hypothesis→parent→change→execution→S7→decision→counterevidence` | 별도 증거 포인터를 가진 작은 typed event, 세대별 append-only | 모든 accepted generation 최소 한 이벤트, 기각된 proposal은 counted generation과 분리된 시도 로그 |
| **L2 Long-term research memory** | 반복 실패·성공/실패가 혼합된 변형 family, 희귀 위험 사건, 반증, 잠정 시장국면, 출처검증 부모, 지표별 약점, 미완결 연구 질문 | immutable events 위에서 재빌드하는 index/aggregation; 전체 인덱스는 100세대 제한 없이 성장 | 과거 반증/위험사례 버리지 않음, 계산식·부모·데이터·기간이 바뀌면 집계 동일시 금지 |
| **L3 Query-specific handoff** | 다음 단계가 *계획인지 진단인지*에 맞는 L2 검색 결과 + 최근 1–3세대 + 요청 의사결정 + 충분한 참고 증거 | 버전·source head hash·dataset/catalog/phase 결박, 다시 만들 수 있는 캐시 | **여기만 유손실 요약 허용**; 모자라면 상세 근거를 읽는 `REPLAY`로 확장 |
| **L4 Human report/dashboard** | 사용자에게 다음 실행 목표·관측·실험·위험·비용·남은 일 보고 | Markdown/CSV/그래프, 자동 생성·읽기전용 | 사람용은 모델의 단독 입력 원본이 아님; raw token, OAuth 보관 금지 |

L1/L2는 증거의 *구조화·색인·집계*이지 원장을 임의로 새로 만드는 것이 아니다. L3 handoff는 canonical 증거 해시가 불일치하면 폐기; 파생 JSON/Markdown이 마지막 성공 세대의 진실을 대체하지 못한다. 원장 검증 실패 시 압축을 풀어서 넘어가는 것이 아니라 **FAIL CLOSED**한다.

### L1 연구 이벤트 스키마 (구현 대상, 현재 운영에 적용된 것으로 주장하지 않음)

필수 필드: `schema_version`, `session_id`, `generation`, `phase`, `dataset_hash`, `data_zone`(non-PIT 개발), `catalog_version`, `strategy_hash`, `effective_signal_hash`, `parent_generation/parent_hash`, `typed_intent_exact_hash`, `intervention_family_hash`, `hypothesis_id`, `hypothesis_status`(HYPOTHESIZED/OBSERVED/CONTRADICTED/INCONCLUSIVE/INVALID), `claim_kind`(OBSERVATION/INFERENCE/UNTESTED), `observed_trade_ids`, `original_evidence_hash`, `s7_record_hash`, `costed_execution_change`, `outcome_metrics`(return/MDD/cost/exposure/trade_count/benchmark), `market_regime_definition_id`, `competing_explanation`, `next_discriminating_test`, `data_limitations`, `provider_attestation_class`, `source_created_at`, `validated_at`, `event_hash`.

- 원본을 요약한 문장에는 필수적으로 `source_generation`, `evidence_hash`, `s7_hash`, `trade_id` 또는 측정 단위를 연결한다. *관측*과 *기전 추정*을 다른 필드로 보관한다. `NOT_ESTABLISHED`는 확증으로 바꾸지 않는다.
- 0거래 / 무효 시장노출 / 음수 성과 / 수익 개선과 MDD 악화 / 부적격 부모 / 누락 QQQ 비교군 / 시점 누수 / 사라진 진입 기회 / 반복 중복 탐색을 모두 **음성 경험 기억**으로 기록한다. 성공만 상위 N개 저장 금지.
- 하나의 거래 차이를 유효한 개선이라 정의하지 않는다. 부호, 비용, 투자기간, QQQ, 다중 비교, 거래 수 및 4개 개발 하위구간을 별개로 기록한다. 단일 개발 S7은 독립 반복실험이 아님.
- 통합 V3/173-feature 출처 문맥을 기록하려면 `strategy_ir_hash`, component parent roles, indicator implementation/unit hash, shared-NAV/overlap cost, route regime lookahead 정의까지 기록해야 한다.

### L2 재사용 가능한 연구 지식 항목

1. **전략 계보(episodic):** G57의 실패를 G58의 부모 맥락에서 보존하되 “다른 부모에서 같은 개입”은 새 실험으로 취급.
2. **개입 family/음성 지식(semantic):** `(same parent hash, exact typed intervention)`은 중복 사전거절 후보. family 수준 반복 손실은 탐색 방향을 바꾸는 근거지만 전 시장에 대한 금지규칙 아님.
3. **시장 국면/경제성:** 같은 지표라도 상승·하락·횡보, 변동성/거래 비용, 체결 환경에 따라 성능이 다를 수 있으므로 기간·국면 조건을 보존. 개발 데이터 기반 분류만 허용.
4. **미완결 질문(open):** 원인을 모르는 손실/상충하는 결과/측정 불능/부족한 표본은 삭제하지 말고 `NEEDS_TEST`로 승격. 근거 없는 확신은 `UNKNOWN`으로 남김.
5. **절차 지식(procedural):** 잘못된 계획이 검증에 걸린 사유, 다시 시도할 때 필요한 입력·제약, MCP API 계약 변경, Pine/지표 계산 검증 규칙 등 전략 수익과 독립적인 안정성 기억.
6. **장기 지표/모듈 개선:** F3→F4/S8/F5와 연결된 `weakness→feature/regime→observed executions→S7→future action→followup outcome` 경로를 집계하되, 선택적 모델 경로만으로 인과 추론하지 않음.

## 3. 얼마만큼 압축할 것인가 — 고정 8천 자가 아닌 3단계 적응형

**검증 전 가설적 초기값** (하드 프로덕션 정책 아님):

| 컨텍스트 모드 | 전체 모델 문맥 예산(UTF-8 문자 아닌 **직렬화 문자**) | 113,581자 기준 감축 | 선택 조건 |
|---|---:|---:|---|
| **S / compact plan** | 12,000–20,000자(초기 기본 20,000자) | 약 82–89% | 정식 부모·신규 가설·최근 S7·반증 충분히 포함된 단순 계획 |
| **M / complex plan or diagnosis** | 20,000–32,000자 | 약 72–82% | V3·국면·규칙 복합, 거래별 근거, 상반된 관측; 진단은 실측 S2 상세 필요 |
| **L / evidence replay** | 32,000–48,000자, 또는 직접 증거 조회 | 약 58–72% | 회수율 부족, 미검증 가설·충돌/복잡한 실패, 희귀 위험 사례, 정확한 계보 복구 |
| **Baseline** | 현 문맥 113,581자 | 0% | A/B 시험에서 비교하는 full context, 운영 고정값 아님 |

**변경 불가 원칙:** 누락되면 판단이 바뀌는 정보는 문자 제한을 초과하더라도 자동 삭제 불가. `ESCALATE_EVIDENCE_REPLAY`로 증거를 확장하고 선택적 한도를 기록한다. 시스템/도구 schema, 모델 자체 사고 토큰, 반복 모델 턴 토큰까지 포함한 **실제 provider 입력·출력 토큰**을 따로 계량해 예산 목표를 조정한다. 12k/20k/32k는 문자 예산이지 토큰 수가 아니다.

20,000자 기본 계획 인계서의 **초기 예산 할당안** (변동 가능):

| 항목 | 문자 예산 | 반드시 남길 사실 |
|---|---:|---|
| 정체성·데이터/모델/권한·현재 phase | 1,000 | 세션·head·dataset·catalog·orders/OOS/증명수준, 절대 raw checkpoint token 금지 |
| 연구 목표·typed 전략 계약·품질 게이트 | 2,000 | 허용 지표/부모/룰과 반증·거래/비용·QQQ 정책 |
| 최근 1–3세대의 실제 결과/결정 | 3,500 | 관측치, 수익·MDD·trades·비용·증거 링크, 원인 추정 구분 |
| 검증된 부모 frontier/대안 | 3,000 | 최고수익과 위험/거래회전/다양성 및 부적격 사유 |
| 반복 실패·충돌·반증/중복 금지 | 3,500 | parent exact fingerprint, repeated families, 비활성 전략·거래 회피 |
| 새 연구 후보·대안 가설·확인 실험 | 2,500 | 테스트 가능한 기전, 실제 측정 가능 지표, 반론 후보 |
| 지표 약점·시장 국면·데이터 제약 | 2,000 | F1/F2/F3 및 unit/lookahead, OOS 불확실성 |
| QQQ·비용·관측 통계 | 2,000 | 동기간 측정, missing 처리, exposure/trade count |
| provenance pointers/잔여 용량 | 500 | source hashes, 필요 시 read-more |
| **합계** | **20,000** | 예산은 *순위/검색 정책의 시작점*; 필수 증거가 많으면 확대 |

진단 인계서는 계획과 다르다. **S2 체결 전후 비교/손실 거래/미체결·비용/실패 가설/진단 출처 및 `context_hash`**가 우선이며, 제출 이후에만 발생하는 S7 결과를 진단 작성 전에 삽입하지 않는다(시간상 누수 방지). 압축된 모델 계획 스키마 자체의 길이는 회차별로 정확히 계량하고 20k 안에 들어오는지 테스트한다.

## 4. 압축의 핵심은 내용 선택 알고리즘 (단순 요약 금지)

**1차 필수 게이트(정량 점수보다 우선):** ① 현재 세대와 phase ② signed/canonical head/dataset·catalog ③ 부모 검증·품질 제한 ④ 다음 차례가 plan/diagnosis ⑤ 마지막 실측 S2/S7 및 결손 상태 ⑥ 비용·QQQ 동일기간/데이터 한계 ⑦ 중요한 음성 기억(동일 부모 개입 중복, 무거래, 위험 위반) ⑧ typed 입력 스키마. 누락 시 compact 생성 실패.

**2차 재현 가능한 랭킹:** `relevance_to_current_decision`, `evidence_integrity`, `actionability`, `information_gain`, `regime_or_parent_match`, `recency`, `contradiction_and_risk`를 각각 0–1로 *측정 근거로만* 채점. 예시 초기 결합 `(0.25 relevance + 0.20 measured utility + 0.20 contradiction/risk + 0.15 regime-parent similarity + 0.10 information gain + 0.10 recency)`은 **검증용 실험 가설**이고 결과에 맞춰 과최적화 금지. `evidence_integrity`는 가중치가 아니라 **하드 필터**: 검증되지 않은 개선 주장 배제, `UNKNOWN` 증거는 확인할 필요가 있는 미결 질문으로 별도 표시. GPT 자기확신도는 실측 신뢰도가 아니다.

**중요한 실패를 무조건 버리는 역선택 방지:** 최근 1–3회와 정확한 same-parent 실패/미해결 충돌은 우선 포함, high-risk rare adverse/0 trades 사례는 오래돼도 상단 보존, 긍정·부정·미해결 각 집단에서 관련 이벤트를 균형 추출. 오래된 실험이라도 현재 부모/지표/국면과 강하게 일치하면 우선. 반대로 동일 증거를 여러 섹션에 완전 반복하지 않고 한 번만 본문에 두며 나머지는 source pointer로 참조.

**3차 점진적 조회:** `LOOKUP`(정확한 부모/신호/거래)→`COMPOSE`(여러 세대·국면의 상충 증거 합성)→`REPLAY`(정본 S2/S7·체결까지 확장) 중 질의에 맞는 방식을 선택한다. 기본은 원본·지표 결합 조회이며 필수 증거 유실 감지 시 자동 REPLAY. `recent`만 과대 반영하지 않는다. 안전/계보 질문은 생성형 요약이 아닌 raw hash replay가 답이다.

**4차 중복·증거 다루기:** `exact intervention × parent hash`, `effective_signal_hash`, `child_strategy_hash`는 구분한다. 다른 parent·regime·data hash면 동일 intervention family라도 과거 결론을 무조건 계승하지 않는다. family level은 연구방향의 힌트로만 사용한다. 해시뿐 아니라 실제 compiler semantic equivalence 검사를 요구하고 규칙 순서·포지션 크기·체결 시차·비용/규모가 달라지면 별도 변형으로 유지한다.

**5차 위치·형식:** 가장 위는 불변 연구상태/무역/현재 판단 질문, 끝은 이번에 필요한 행동과 반증 검사. 중간은 부모·실측·음성 증거, ID/해시 연결 표. 전체 유효성 검증을 거쳐서만 생성. 모델에게 “무엇을 모르고 있는지”를 명시하고 과거 사실·가설·추정을 분리한다.

## 5. Quant 연구가 실제로 개선되도록 기억을 업데이트하는 방식

**매 성공한 세대마다**, canonical `submit_algorithm_diagnosis` + S7 report가 해시 검증된 후 `L1(event)`를 추출하고 `L2(memory projection)`을 갱신한다. checkpoint commit과 별도 **원자적 버전 교체 가능한 파생 캐시** 또는 전용 저장소 snapshot를 사용하되, 복구 시 canonical head를 기준으로 **항상 재생성**할 수 있어야 한다. 원장의 commit 성공 후 캐시 갱신 실패는 `handoff stale`로 표시하고, 다음 호출에서 rebuild. 원장 행/해시·기존 DB schema를 손으로 수정하지 않는다.

**학습 업데이트 6개 흐름**:

1. 예측·대안 가설: GPT의 주장, 기대 방향·측정 지표, 예상 실험 결과를 **사전 등록**. 사후 합리화와 구분.
2. 체결/결과: 부모 대비 자식의 S2 실제 거래·비용·MDD·노출·QQQ를 측정. 실패가 단순 수익 감소인지 ‘전혀 거래하지 않음’인지 분리.
3. 반증: S7의 개입 실측·4개 개발 구간·거래 변화·불변 trace·효과 없음·비용 뒤집힘 등으로 가설을 `SUPPORTED_DEV_ONLY/REFUTED/INCONCLUSIVE/INVALID` 계열에 정렬(정식 상태명 신규 계약).
4. 국면·조건: 실패가 특정 손실 거래/market exposure/시장변동성에서만 관측되었는지 기록하고 *기간/데이터 범위* 밖 일반화 금지.
5. 다음 판단: 같은 부모/동일 typed operation 반복을 막고, F1/F2/F3 기여 신호·여러 부모 Pareto frontier·개입을 바꿀 근거를 제공. 모델은 반증 가능한 새 가설을 내야 한다.
6. 사후 확인: 다음 세대가 실제로 어떤 기억 ID를 참조했는지, 선택한 변형이 반복이었는지, 실측 거래가 달라졌는지, 그 효과가 증명됐는지 기록. 인용만 하면 학습된 것이 아니라 **판단 변화·실험 결과**까지 확인해야 한다.

**기억 업데이트 메트릭**: 정확한 source-ID grounding rate, 복구 가능한 trade evidence, failed-fingerprint revisit rate, 전략 고유성(`effective_signal_hash`/child hash), 신규 실험의 측정 가능한 지표 비율, actionable counterhypothesis 수, GPT가 기억을 읽고 이전 가설을 수정한 비율, 중복 재제출·비활성 자식·거래 수/노출, S7 방향·경제성 일치, 비용후 QQQ 대비 성과, MDD·회전율. 현재 세대의 수익이 개선됐다는 이유만으로 memory scoring을 조정해선 안 된다.

**기억 버전·정정:** `active/superseded/contradicted/requires_more_evidence`를 갖고, 이전 근거를 영구 링크하며 *새 주장*만 superseding event로 추가. 운영 데이터 정책/계산기/unit 변화, 출처 공급자 오류, 오래된 시장 구간에 대한 유효성 조건이 달라지면 영향받은 L2/L3 인덱스를 무효화하고 갱신. 기각/실패도 검색 가능해야 한다. `UNKNOWN`은 침묵이 아니라 **실험할 항목**이다.

## 6. 압축이 정말 좋은지 평가하는 실험 설계 (F5와 독립된 기억 A/B)

### Gate A — 정본 재현·안전 (`M0`, 모델 호출 0)

- 이미 기록된 실세션의 **읽기전용 스냅샷**을 격리 저장소로 복사, dataset/catalog/parent head 확인. 68세대 시점 사용 시 새 모델 호출로 운영 원장을 변경하지 않음. pinned fixtures와 다른 연구세션이 섞이지 않음.
- L0→L1/L2/L3 재생성 *결정론* 검사: 동일 입력 동일 handoff hash, 이전 S7 hash 변경/순서 역전/시점 누수/원장 일부 누락/부모 자격 박탈 시 구문검사 통과 여부와 무관하게 fail closed.
- 30–50개 이상의 **근거 질문**을 운영상 민감한 조건으로 만들어 원본 대비 검증: 마지막 parent·거래 수·이전 음성 증거·동일 개입·가설 반론·미완결 S7·데이터 시점·QQQ missing. 목표: **금지·보호 사실 누락 0**, 허위/unsupported 추정 0, 거래/성과 숫자·문맥 source 재현 100%; 기타 관련 recall 목표 ≥95%는 평가 초안이며 실제 샘플 크기·검정력 확인 후 확정.

### Gate B — 내용 품질/재현 (`M1`, 실험 가능한 경우 모델 호출)

- 동일한 실제 Quant 연구 진입점에서 계획/진단별 `FULL(원본 113,581자)`, `L(최대48k)`, `M(최대32k)`, `S(기본20k/확장12k)`를 **4개 조건**으로 비교. 단순 잘라내기 baseline도 **negative control**로 둬서 구조화한 기억의 부가가치 측정. 조합 효과를 구별하기 위해 `S + exact-evidence replay` 추가.
- 5개 유형의 미리 정한 학습 과제: 최근 손실 진단, 오래된 반복 실패 회상, 상반된 S7 결론, 부모/국면 전환, 신규 지표·계산기의 시점/단위 위험. 각 유형 8–12케이스(총 ≥40–60) 권고. 동일 모델/typed schema/가격 스냅샷·호출 예산, 평가 기준 사전등록, 평가자에게 군 이름을 숨김.
- **주요 평가:** `evidence-correctness`, exact failure retrieval, next valid plan rate, trade-backed counterhypothesis quality, decision change attributable to retrieved evidence, cost-adjusted S7 executed activity; 그리고 `input_tokens`, `output_tokens`, 총 model turns/latency, rejection/duplicate/no-trade rate. 앱 자체 토큰 보고와 독립 공급자 청구·서명을 구별.
- **비열등성 제안 (사전등록 후 변경 금지):** 안전·과거 실패·parent·S7 필수 사실 recall 100%; 전체 사실 회수 ≥95%; 정책 위반/원본과 상충 0; typed plan validation success가 FULL보다 **3%p 이상 낮아지지 않을 것**을 임시 한계로 검토(최소 샘플·95% CI로 통계적으로 평가), 입력 토큰은 FULL 대비 **최소 50% 절감** 목표. **40–60회만으로 3%p 비열등성을 강하게 입증하기 어려울 수 있으므로** 단계적 표본 크기 재계산과 CI 실패 시 '미결' 처리. 수익률 단독 기준 금지.
- 12k가 기억 손실로 더 많은 GPT 재시도/거부를 초래하면 20k/32k로 자동 확장. “상시 90% 압축” 강행보다 *quality-per-total-token*과 정상 세대 완결률을 우선한다.

### Gate C — 연구 진화의 증분 효과 (`M2`, 비용과 품질 통제)

- Gate B 통과 후 **동일 68세대 정본을 복제한 비PIT 개발 브랜치 세션**에서 먼저 각 방식 1→3세대씩 검증, 이후 10세대씩 **복수 독립 반복**을 설계. 유사 시점 기준 데이터 고정, 동일 모델/예산/제약, 방법별 독립 연구 트리(부모 계보 혼합 금지). 매일 다시 시작하는 듯한 호출에서도 같은 증거 정체성 확인.
- F5의 학습기반 대조군은 `FULL + existing memory`, `S/M + structured memory`, `S/M minus negative memory`, `S/M minus F3/F4`, `random/naive novelty` 등 단계적 ablation. F5의 **학습 개선 효과**와 별개의 *압축으로 인한 정보 손실*을 혼동하지 않음. 병렬 증거 검증에 비용이 크므로 작은 단계에서 성공/실패를 파악해 다음 군에 예산을 할당.
- 주요 성공 조건: **새로운 경제적으로 측정 가능한 규칙/시장 국면 가설 비율 증가**, 부적격 부모/동일 개입 반복 감소, 중단 복구 성공, GPT 의사결정 근거 회수. 수익률, MDD, 거래 수, 익스포저, 비용, 동기간 QQQ 성능은 보조 결과로 명시. n=10 연구 트리의 수익 차이를 통계적 우위로 단정하지 않음; bootstrap은 시계열 블록/국면 의존을 반영하고 필요하면 95% CI·multiple-testing notice.
- **독립 OOS는 최종 고정 성능 심사 전까지 절대 열지 않는다.** 2026 OOS 결과를 handoff scoring 규칙이나 부모 학습에 넣으면 평가 오염. 개발의 4개 retrospective windows는 독립 증명이 아니고, 공표 모델 출처/실제 GPT의 공급자 증명을 별도로 확인한다.

### Gate D — 30/100/500세대 규모·운영 안정성 (`M3`)

- 30, 100, 500 completed에서 L0 선형 성장·L2 인덱스 update 비용·get_handoff latency/size·retrieval quality 경향 기록; 100세대까지 예측한 캐시 성능이 500세대에서 유지되는지 stress. 오래된 희귀 위험을 잃는 recency bias 감시.
- 중간 `AWAITING_DIAGNOSIS`, 불확실 네트워크 응답, 일시정지 후 resume, 동일 세대 다중 SDK 트리거, 캐시 부패/삭제, 서버 재시작에서 **정본 중복 증가 0, 증거 해시 변경 0**.
- 기존 차단 상태 `BLOCKED_MODEL_HOST_DISPATCH` 유지: 수동 `다음`을 통한 GPT 활성 턴은 가능하지만 Python SDK `tools/call` 반복만으로 새로운 ChatGPT 모델 턴이 시작된다고 주장하지 않는다.

## 7. 추가 누락 개발 기능: 실행 계약·의존성까지 정리한 통합 로드맵

**전제:** 기능 파일이 존재하는 것과 Quant 학술 세대에서 실제 plan/S2/진단/S7/계승/기억까지 이어지는 것은 다른 수준. 아래는 **현재 검사된 상태와 앞으로 필요한 작업**이다.

| ID·우선 | 기능 / 코드 기초 | 현재 판정 | 필요한 통합·평가 / 반드시 통과할 조건 |
|---|---|---|---|
| **P0/V05** | 비용·슬리피지·용량, 독립성/다중검정, QQQ 벤치마크 누락 게이트 | 대부분 코드·테스트 존재, 완료 승인 미확인 | 실제 데이터 snapshot·비교군 hash·동일 비용 가정, benchmark-missing/거래 0/비정상 가격 fail closed; QQQ 상회 요구와 *연구 가설 생성*을 구분 |
| **P0/T4-H** | Quant canonical evidence→L1/L2→L3 `ResearchHandoffBuilder` + 별도 간결 서버 read view | **이번 ADR로 설계**, 운영 구현 아님 | 버전/phase/source head/dataset/catalog/S7 강제; 재생성/불일치 실패/스냅샷 테스트. 기존 32 MCP ABI 불변; 새 opt-in read 도구는 클라이언트 호환성 검증 후 승인 |
| **P0/T4-R** | SDK 재진입·중복/정확한 단계 재개 | 기존 로컬 lease, 실제 상태/ S7 계약 호환·겹친 요청 처리 코드 존재 | 서버 스코프 idempotent receipts + native 모델 호스트 계약. `plan`-`diagnosis` 동일 요청 재시도·동시 프로세스·실패 복구, evidence/parent match; 운영 세대 변경 없이 격리 실험. 수동 ChatGPT 직접 MCP 연구는 우선 계속 허용 |
| **P0/T4-A** | 실 ChatGPT 모델 호스트 자동 호출·독립 model capture | SDK→host-turn 미검증, `BLOCKED_MODEL_HOST_DISPATCH` | 지원된 호스트 API/사용자 승인 없이 무인 자동 세대 진행 금지. 직접 ChatGPT MCP는 사용자 호출에서 진행, SDK는 단순 상태 추적. 실제 provider attestation과 collector/local 로그 구별 |
| **P1/S6** | 범용 **173 지표**, academic VERIFIED **8** / proposed 3 | 카탈로그 보존, 수식/단위 일부만 검증 | 147 일반 OHLCV 후보 + 21 외부 자료 + 5 특수 자료는 단계적 input alignment/PIT/lookahead/typed compiler/S2/S7; 검증만 정식 등록. Garman–Klass 표준편차 vs 분산 등 단위 검증, Pine 변형 동일성 |
| **P1/F1–F3** | 지표 프로파일 F1·약점 F2·비용/체결 기반 F3 | 개별 구현·테스트 존재; F3→공식 다음 문맥 미연결 | 거래 ID→특성/회피한 손실 또는 놓친 이익의 사후 편향 표시→S7 replay→GPT 다음 계획에 연결, 실제 개선 반증 실험 |
| **P1/F4** | `weakness→typed intervention→parent/child fills→S7→long memory→future experiment` | **신규 통합 필요** | 출처/컴파일/시장 국면/데이터/비용 구분, 반증/보류 상태 versioned; L2 재생성·기존 S7 불변·next-context 정확 회수·모델 반영 로그 |
| **P1/F5** | 압축 실험 및 학습방식 성능 평가 | 정식 동일예산/반복 검증 미완료 | Gate A–C: FULL/compact/replay, F4 ablation, 무작위 및 기존 전략 대조, 거래·부모·S7/QQQ·토큰/시간·모델 선택 이유 비교. 10세대는 신뢰성 우선, 100은 승인 후 |
| **P1/S8** | EXPLORE/EVOLVE/TEST_HYPOTHESIS 적응형 방향 | 현재 *ADVISORY*, 실제 운영 진화 루프 일부 연결 | 과거 실패·실행 거래 기반 연구 정책 자동 선택/예산은 각 세대 선택 근거·대안·반증 기록; 맹목적 25세대 균등 분할 금지; 독립 데이터 성과로 정책 재튜닝 금지 |
| **P1/V3** | 복수 부모 교배·시장 국면 다중 sleeve | compose/router/shared NAV 개발 코드 존재, canonical counted S2/S7 미통합 | 다부모 provenance/결정론 typed StrategyIR, 공동 현금·실제 비용/중복 체결·레짐 시점 안전/거래 노출; P4 품질·무거래·S7 후 승격, 성공 없으면 EXPLORE 복귀 |
| **P1/Pine** | TradingView PineCode 원리+원본 재현+새 규칙 창안 | 수집/실험 일부, 최종 GPT 연구 활용 전수 증명 없음 | 15개 소스별 공개 라이선스/컴파일·원본/원리 결과 비교, Pine v4/v6 semantics/수익 계산 차이, 지표 등록→GPT 실제 계획 사용 후 완료. 원본 증거/저작권 보존 |
| **P1/generalization** | 2025 이전 개발 vs 2026 봉인 OOS, QQQ 동일기간/P4 품질 | 개발 자료 및 블라인드 승인 게이트 존재, 독립 OOS 아직 미승인 | PIT/기업행동/생존 편향·walk-forward/embargo·다중검정/우승자 편향, 최종 동결 전략만 독립 OOS. 매 세대 OOS 성과를 memory에 적재해 튜닝 금지 |
| **P2/legacy** | **19개** 빠진 과거 Python 고유 소스 경로/2026-05 TypeScript 12개 계열 | 전체 브랜치 인벤토리 완료, 동등성 미검증 | 파일별 현대 소스와 **행동 테스트** 비교→대체 확인/안전한 port/격리로 19/19 근거. 현재 보안 게이트를 깨는 무관 Git history merge 금지 |
| **P2/ops** | 대시보드·모델 메타로그·고정 URL·재개 | 8081/8082 관측 화면 차이, P5 28 vs 운영 68, PythonMCP 33 등 다중 원장 | session-specific UI, handoff 해시·정보율·추가 read 차례·실험 성능·모델 비용, 개발/OOS 분리; 다른 원장 숫자 합산 금지 |
| **P3/V06–V07** | Paper only·최종 GO/NO-GO | 보호 게이트 존재, 정식 운영 전환 미승인 | 전체 회귀/복구/원장 integrity·브로커 격리·주문 OFF, 서면 승인 없는 실거래 비활성 |

**우선순위의 핵심:** L0 정본/보호와 현재 GPT MCP 직접 세대 진행은 기존 기능을 사용한다. **T4-H handoff builder와 F4 계보 구조를 먼저 구축하면** 173-feature/V3/Pine 확대 시 매번 60만 자 이력을 다시 들고 오지 않아도 된다. 다만 V05의 비용·통계 안전 게이트 완료 전 수익성/알파를 승인하지 않으며 OOS 봉인은 유지한다.

## 8. 개발 작업 분할·정확한 인수 기준 (3개씩 병행 가능)

| 묶음 | 세부 작업 | 예상 변경 파일/모듈 (신규 제안) | 인수 기준 |
|---|---|---|---|
| **D1: 모델 없이 시작** | 연구 메모리 이벤트 계약·canonical read adapter·hash validator, FULL context 크기/토큰 베이스라인 | `research/llm/research_memory_event.py`, `application/research_handoff_builder.py`, `tests/research/test_research_handoff_builder.py` | 원본 불변, 68 fixture로 재생성 결정론·변조 차단; 실패/확증/미검증 관측 구별 |
| **D2: 검색·문맥 정책** | 부모/개입/국면 인덱스, multi-criteria 선정, 20k plan/32k diagnosis 적응 예산, `LOOKUP→COMPOSE→REPLAY` | `research/llm/memory_retrieval.py`, `research/llm/memory_budget.py` | 검증된 근거 출처 100%, 안전 중요 사실 유실 0, oversize 시 REPLAY/STOP, 원본 단일 사실 중복 최소화 |
| **D3: 재진입·호환성** | 서버 측 opt-in compact read 계약, 파일 handoff 캐시/원자 갱신, SDK read/phase 검사·기존 32툴 호환, user-triggered GPT 실제 세대 smoke | `application/academic_checkpoint_service.py` 읽기 추가, `integrations/chatgpt_mcp_sdk.py` opt-in facade, `tests/integrations/test_research_handoff_mcp.py` | token/OAuth 유출 0, plan·diagnosis·S7/reconcile 정확 재개, G→G+1 증거·S7·부모 확인, 기존 공용 도구 unchanged |
| **D4: 실험·검증** | 40–60 evidence QA, FULL/S/M/L/REPLAY, F4 ablation, 동일 예산 1→3→10 및 장기 30/100/500 stress | `scripts/audit_research_memory_quality.py`, `evaluation/research_memory_quality.py`, dashboard | 최소 50% input-token 절감 가설·성능 비열등성/95% CI 실측, 누락 시 자동 확대; 모델 출처 구분 |
| **D5: 기존 기능 회수** | F3→F4, S8, 173학술, Pine, V3, 레거시 19, generalization | 각 기존 모듈의 안전 어댑터·증거 인계 경로; module별 독립 PR | 각 파일·각 활성 도구의 `code→typed plan→S2→S7→parent→next model context` E2E 근거, 일부만 구현되면 PARTIAL 표기 |
| **D6: 배포·운영 게이트** | 전체 회귀/mypy, 롤백 rehearsal, read-only staging, fixed URL/OAuth 보존, 독립 PIT/OOS, paper, GO/NO-GO | 운영 스크립트/대시보드/개별 승인 문서 | protected originals SHA 동일, 서명·해시·백업, 주문 OFF/봉인 OOS, 별도 승인이 있을 때만 cutover |

**작업 보고 필수:** 각 `D#` 이후 (1) 변경 소스 SHA, (2) 실행 테스트/실패·건너뜀, (3) 지금 실제 운영 연결된 범위, (4) 보존된 세션·원장·승인 경계, (5) 다음 우선순위/블로커, (6) GitHub Push/rollback 상태와 남은 과제 3개를 기록. 구현하지 않은 파생 handoff API, 모델 자동 호출, F4/V3 승격은 완료라고 하지 않는다.

## 9. 설계 실패 유형과 중단·롤백 규칙

- **Overcompression/기억 유실:** 긴 과거 사례가 빠져 잘못된 부모 선택·반복 실패 발생 → 해당 문맥 S/M/L에서 `REPLAY_EVIDENCE_REQUIRED`, source retrieval 확장. 모델에게 모르는 것을 묻고 추정 성공 금지.
- **Summary drift:** 누적 요약의 요약을 반복하며 원본 가설/측정치가 변함 → 항상 **L0 canonical로 다시 빌드**, previous summary를 재요약 원본으로 사용 금지.
- **Survivorship/hindsight:** 우승자만 memory에 남거나 뒤늦은 비용후 수익에 맞춰 가설 변경 → 모든 accepted 세대와 거부/반증·실측 실패·0거래 로그 유지, 기전 주장 사전등록.
- **Overfitting:** 예전 개발시장 고성과에 맞춰 memory ranking/feature threshold를 튜닝 → 개발 스냅샷 내 별도 validation과 승인 전 OOS 봉인, 멀티트라이얼 보정.
- **Model hallucination/instruction injection:** 자유 서술 요약을 시스템 명령처럼 주입 → source-marked data-only schema, typed validators, raw tool inputs는 신뢰 경계 검사, 명령/도구 권한을 memory가 변경할 수 없음.
- **Stale cache/race:** handoff head/dataset/catalog과 최신 Quant phase/hash가 불일치 → 해당 파생물 무효화 후 생성; 동시 호출은 원장 CAS/reconcile; 동일 세대 두 번 증가 불가.
- **Performance deterioration:** input token 감소해도 계획 반려·모델 재시도 증가/수익-MDD 악화 → 총 비용/성능으로 비교; noninferiority 실패하면 FULL baseline rollback, 증거는 온전히 보존.
- **Unsupported unattended execution:** SDK `tools/call`로만 새 GPT 턴이 생긴다고 가정 → `BLOCKED_MODEL_HOST_DISPATCH` 유지, 기존 ChatGPT 사용자의 '다음' 호출 기반 진행.

## 10. 참고 연구와 프로젝트에 적용하는 범위

- Liu et al., **Lost in the Middle**, TACL 2024: 긴 문맥 중간의 중요한 정보는 모델이 놓칠 수 있음 → *전체 문맥 확대만으로 기억 개선을 보장하지 않음*. https://aclanthology.org/2024.tacl-1.9/
- Wu et al., **LongMemEval**, ICLR 2025: 기억 검색 정확도·시간·업데이트·모름 판단을 별도 평가해야 함 → 위의 증거 질문 세트와 unknown 처리. https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html
- Park et al., **Generative Agents**, UIST 2023: 관측·기억의 반영·계획을 분리 → L1/L2/L3 계층 설계의 참고 사례. https://research.google/pubs/generative-agents-interactive-simulacra-of-human-behavior/
- Yu et al., **FinMem**, AAAI Symposium 2024: 금융 연구 에이전트에 계층형 기억을 적용한 탐색적 연구. 동일한 실거래 성과를 Quant에 보장하는 결과로 사용하지 않음. https://doi.org/10.1609/AAAISS.V3I1.31290

**최종 판단:** 기억을 짧게 만드는 게 목표가 아니라, **정본 증거가 가리키는 실패·원인·새 실험을 GPT가 다음 세대에서 더 정확히 재사용하도록 만드는 것**이 목표다. 따라서 데이터 보존·증거 충실도·모델 입력 절감·진화 성과를 네 별도 평가축으로 관리하고, 압축은 연구 성능을 잃지 않는 한도에서만 승인한다.

## 부록 A. 실제 GPT에게 제공할 인계서의 판독 방식(예시 템플릿)

다음은 **가상의 예시 구조**이며 실제 G68 성과나 승인된 거래를 나타내지 않는다. GPT에게는 JSON typed fields와 필요 시 근거 원문을 함께 제시한다. 성공/실패 사유는 반드시 **원본 근거→관측→경쟁 가설→판단→검증 요청** 순서로 구성한다.

```yaml
scope:
  session_id: <unchanged server-issued ID>
  completed_generation: <canonical count>
  next_phase: AWAITING_PLAN
  source_head_hash: <canonical actual evidence hash>
  dataset_hash: <development snapshot identity>
  verified_qqq_comparator: <measured, or MISSING>
  orders_enabled: false
  independent_oos_approved: false
current_decision:
  question: "Which falsifiable typed intervention should be tested next?"
  parent: <audited parent strategy hash or NO_VERIFIED_PARENT>
  permitted_modes: [EXPLORE, TEST_HYPOTHESIS, EVOLVE]
measured_recent_events:
  - event_id: <actual L1 event hash>
    observed: <costed parent-child effect; direction, exposure, fills>
    supported_claim_kind: OBSERVATION
    original_s7_receipt_hash: <actual S7 immutable record hash>
    uncertainty: "reused dev window; not causal, not independent OOS"
important_long_term_failures:
  - event_id: <older typed same-parent repeated failure>
    why_relevant_now: <same exact strategy parent and typed operation fingerprint>
    reuse_rule: "do not blindly repeat unless a discriminating new control exists"
competing_hypotheses:
  - unknown: <mechanism not established>
    required_measurement: <specific trade-level effect and control>
next_action:
  request: "submit a valid typed AlgorithmPlan or ResearchIntent, not a broker order"
  retrieve_raw_if: [S7_conflict, evidence_missing, rare_risk_case, parent_ambiguous]
```

`get_research_handoff`가 도입되기 전에는 이 템플릿을 **테스트용 파생 데이터에서만** 생성한다. 해시·세션·거래 사실을 임의로 채워 정식 계획으로 제출하지 않는다. SDK 저장 문서에는 checkpoint token/credential을 기록하지 않는다.

## 부록 B. 객관적인 최종 인수 판정

- **P0 차단 실패 = 전체 실패:** 봉인 데이터 접근, 거래 권한 상승, OAuth/토큰 인계서 누출, canonical 해시 덮어쓰기, 세대 중복 증가, S7 미완료 counted. 하나라도 발생하면 즉시 실험 중단·이전 전체문맥 read 경로 복구.
- **기억 안전 실패 = 압축 모드 비승인:** 0거래/계산 단위/부적격 부모/QQQ missing/동일 부모 개입 중복과 같은 필수 사실의 회수 실패 1건이라도 발생하면 해당 S/M 설정은 재설계, 과거 정본은 유지.
- **성능 비열등성 미결 = 확대 보류:** 토큰만 줄었고 GPT가 과거의 반증을 올바르게 사용했는지 검증되지 않은 상태에서 무인 100세대 실행·성능 개선을 선언하지 않는다.
- **E2E 통과 = 실제 GPT 호스트에 한정:** 모델 호출 서명/출처 수준을 원래 증거와 혼동하지 않고, plan→S2→diagnosis→S7→next memory 및 원장 해시 연결이 실측으로 한 세대 이상 확인되어야 한다.
- **점진 배포:** 기본 기존 32도구는 변화시키지 않고 compact view는 선택적으로 추가. 정보 품질·비용·오류율이 FULL보다 유리하다는 근거를 얻기 전에는 자동 기본값 전환하지 않는다. 전체 회귀/롤백 rehearsal/사용자 별도 운영 승인 후만 cutover.
