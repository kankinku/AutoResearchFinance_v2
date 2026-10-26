# Quant AutoResearch — SDK 호출 전용 / Quant MCP 자율 진화 계획 v1

**작성:** 2026-10-26 KST
**기준:** `feat/quant-unified-mcp-20261026` (`f8524cf`, 통합 소스; 운영 미배포)
**상태:** `PROPOSED_DESIGN_ONLY` — 실행기/호스트 변경 및 운영 배포는 이번 문서에 포함하지 않음
**연구기억·압축·모든 미통합 기능 세부 설계:** [v2 통합 로드맵](quant-evidence-memory-compression-and-unified-research-roadmap-v2-20261026.md), [21개 수락 게이트](quant-evidence-memory-gate-matrix-v2-20261026.csv). v1의 단순 압축 제안은 v2의 정본 보존·증거 검색·적응형 예산·A/B 통제로 대체. 기존 T4/SDK 권한 경계 유지.
**작업 범위:** T4의 SDK/호스트/Quant 분리 + 미통합 기능 회수 (Q02/Q04–Q12/Q14–Q17/Q19/Q20). 사용자의 기존 직접 ChatGPT↔Quant MCP 선택, V05→T4→V01–V04→V06→V07 순서, 운영 OAuth/고정 URL/원장 보존 및 orders=OFF/OOS=SEALED가 우선한다. 변경 승인 없이 모델 제공자·MCP 기본 경로·거래 권한 전환 금지.

## 1. 확정 목표와 엄밀한 역할

| 주체 | 책임 | 하면 안 되는 일 |
|---|---|---|
| SDK (thin deterministic orchestration) | `session_id`/checkpoint 조회, 정확한 모델 차례 호출 요청, 완료 검사, 실패/리플레이 감지, 세대 예산·중지·재개, 최소 결과 보고 | 자체 GPT 판단/전략 생성, 백테스트, 부모 선정, 임의 원장 수정, 미인증 모델 콜백 신뢰 |
| **Quant AutoResearch** (연구 주체) | 연구 정책·방향·후보군 관리, 기존 173 지표 카탈로그와 검증된 typed 계획, 실체결 비용·S7, 실패 기억, 다중 부모/국면·계승, 원장 append-only, 후속 연구 컨텍스트 생성 | 공급자/호스트 없이 스스로 LLM 응답을 만들어냈다고 주장, 미검증 지표·전략을 정식 세대로 승격 |
| **ChatGPT 모델 호스트** (Quant에 지능 제공) | Quant가 생성한 계획/진단 컨텍스트에서 실제 모델 추론 및 typed 응답을 제출하고 결과를 읽음. Quant 정책을 실행하는 연구 판단 협력자 | SDK가 별도 하드코딩한 지표 임계값으로 대신 전략을 선택, 임의로 권한 확대 |
| Moon | 운영 코드·파일·프로세스 개발/호스팅, 로컬 테스트 | Quant와 별개의 판단·원장 근거를 생성 |

**중요 기술적 전제:** MCP 클라이언트가 Quant `tools/call`을 실행하는 것만으로 ChatGPT 추론이 생기지 않는다. **호스트의 모델 차례 실행 권한·메시지 전파·응답 제출**이 실제로 가능한지가 첫 번째 수락 게이트다. 기존 ChatGPT 내 MCP 작업을 우선 재사용하고, 독립 Python SDK의 새로운 Codex 전략 생성 모델을 기본값으로 지정하지 않는다. 서버→호스트 sampling은 2026-07-28 MCP 사양에서 deprecated이므로 호스트 지원을 증명하기 전 자동 추론 우회로로 간주하지 않는다.

아키텍처:

```text
User: run 100 completed generations
      |
[SDK RUN CONTROLLER]       deterministic / no strategy reasoning
  start/check/reconcile → [ChatGPT HOST WORKFLOW] authenticated real GPT
                                |  read Quant's model_context and constraints
                                |  typed Plan / Diagnosis via real GPT
                                v
[Quant MCP (existing 32-tool surface, OAuth, fixed URL)]
   get_algorithm_research → submit_algorithm_plan → S2 costed trade trace
   submit_algorithm_diagnosis → S7 measured controls → verified parent/child
   cross_generation_memory/F1–F4/F5 → next research context / hash chain
      ^                         |
      |-- checkpoint + minimal status / progress ---|
[SDK checks terminal state, budget, no duplication; repeats only on verified success]
```

기존 서명 수집기 증거는 provider invocation 독립 증명이 아니며, 모델 턴 ID/토큰 정보는 SDK 자체 보고 여부를 별도 표기한다. `TEST_ONLY`, non-PIT, independently attested 모델, OOS-approved, paper/real trading 등은 섞어 세지 않는다.

## 2. 기존 코드에서 재사용할 구성요소

- `application/academic_checkpoint_service.py`: `start/get/submit_plan/submit_diagnosis/evaluate_experiments/reconcile/resume/extend_completed_session` 및 체크포인트 토큰·해시 검증, 조건부 부모 선택.
- `integrations/chatgpt_mcp_sdk.py`: 32개 ChatGPT MCP 표면, plan/diagnosis/S7 도구; 현재 인증·기존 URL 정책 유지.
- `application/t4_checkpoint_orchestrator.py`: 사전 차단, 불확실한 실행 실패 처리, 테스트 전용 실행기 경계. 운영상 `EXTERNAL_MCP_UNVERIFIED`를 허용 모드로 바꾸지 않는다.
- `integrations/python_mcp_direct.py`: 현재 **read-only 3-tool allowlist**. 실행 전용 SDK 제어기를 이것과 구별되는 최소 권한 클라이언트로 도입; allowlist를 무작정 전체 쓰기로 넓히지 않는다.
- `research/llm/*`, `research/indicator_engine/*`: S7/연구방향/기억/부모 V2/일반화 P4/지표 F1–F3/V3 컴포넌트와 검증된 백테스트를 재사용.
- PythonMCP의 `t4_codex_structured_model.py`는 **선택적 격리 개발도구**이며, SDK 호출 전용 신규 기본 연구 판단자가 아니다.

## 3. SDK↔모델 호스트↔Quant 실행 계약 (신규 설계; 현재 API로 주장 금지)

**A. 정확한 모델 호스트 게이트** (`M0`, T4 시작 전에 mandatory)

- 기존 ChatGPT MCP 호스트의 실제 **연속 모델 턴 실행 및 Quant 도구 접근**을 먼저 확인. 호스트 안에서 SDK가 모델 턴을 생성/스케줄할 수 있는 지원 API가 없다면 `BLOCKED_MODEL_HOST_DISPATCH`, 연구 세대 0 추가, SDK 모의 결정을 금지.
- 모델 응답이 Quant가 제공한 `model_context`/`context_hash`와 동일하며 올바른 실세션·체크포인트 토큰을 가리키는지 검증.
- 기존 OAuth·MCP URL 그대로; 단순 Python MCP client와 모델 호스트를 혼동하지 않음. 다른 유료 API/직접 provider 연결은 별도 사용자 승인 전 도입하지 않음.

**B. SDK 오케스트레이터** (`R1`):

```text
run_id (distinct) + session_id (immutable) + target + max_calls + max_time + max_tokens
  → read get_algorithm_research(session_id)
  → assert dataset/hash/phase/OOS/orders/policy/parent context unchanged
  → AWAITING_PLAN: request authenticated GPT HOST turn with Quant context pointer
                  host does real typed plan and invokes Quant MCP
  → AWAITING_DIAGNOSIS: request authenticated GPT HOST turn with measured S2 evidence
                  host does real typed diagnosis and invokes Quant MCP
  → after diagnosis: require immutable S7 experiment report linked to generation hash
  → re-read status; if completed count advanced exactly once, checkpoint hash verified
      record one completed generation, hand control to next generation
  → if lost reply: reconcile(session_id, token, request digest) BEFORE any retry
  → if uncertain/not authorized/unsupported host, STOP with reason; never fake completions
```

- 실행 인터페이스 제안: `run(target=N)`, `run(until_stopped=True, bounded_budget=...)`, `status`, `stop`, `resume`, `reconcile`; 모든 호출은 기존 Quant MCP 서비스 아래에서 이루어짐. `stop`은 다음 경계에서 안전 정지하되 진행 중 S2/S7 결과를 버리지 않음.
- 단일 작성권: session-scoped generation lease + unique `(session_id, generation, phase, checkpoint_token_hash, model_request_digest)`; 동일 요청은 idempotent, 다른 세션/후보 교차 제출 거절. 분산 락과 lease TTL/epoch fencing은 기존 원장 SQLite transaction과 별도 검증.
- 소스·진단·비용·모델 사용량·시간을 별도 로그에 기입하되 원본 immutable evidence는 수정하지 않음. GPT 호출 1회가 곧 1세대 아님.
- 컨텍스트 비용 최적화: ChatGPT에는 `history` 전체 대신 마지막 hash, 부모 frontier, 실패 패턴, 압축된 S7/기회 설명과 필요 시 read-more refs. SDK는 금융 전략 내용을 요약/평가하지 않음. 정보량 한도와 재현 검사는 Quant가 책임.
- 재개 정책: `AWAITING_PLAN/DIAGNOSIS`와 `COMPLETED` 정확히 구분, 잃어버린 응답은 `reconcile` → `get` 후 판단, 오류·토큰 제한 시 정지. 1/3/10/100 단계별 원장 증명.

## 4. 필수 단계별 작업 및 수락 게이트

| 순서 | 작업 묶음 / 우선순위 | 개발 내용 | 수락 기준 (테스트/운영) |
|---|---|---|---|
| **P0 (V05 유지)** | 기준 원장·안전·비용 고정 | 통합 SHA/32 MCP/173 지표, 과거 P5 28 / v2 68 / PythonMCP 33 등 별도 session/head/dataset/hash 스냅샷. V05 비용·슬리피지·거래량/용량·다중검정/QQQ benchmark missing gate 정밀 점검. **운영 원장은 조회만** | Git checkout/테스트/DB quick_check/본인 소유 세션 분리, orders OFF OOS SEALED, 보존 해시 전후 동일, V05 fail-closed |
| **P1 (T4 M0)** | 실제 ChatGPT 모델 호스트 ↔ Quant MCP 지원성 | ChatGPT 호스트가 SDK 반복 요청을 받아 Quant 컨텍스트를 읽고 실제 GPT 1 plan + 1 diagnosis/S7을 마치는 경로 확인. 비지원이면 `BLOCKED_MODEL_HOST_DISPATCH` | 새로운 모의 100세대 금지, 실제 턴 증거/누락 진단 대조, 1세대 증거 체인 PASS; 직접 API/새 OAuth는 승인 없으면 사용 불가 |
| **P2 (T4 R1)** | SDK 실행기, 런 예산·중단·재개 | 타입 제한 MCP 클라이언트, 파라미터 대신 `session_id` 중심, 단계 state machine, lock/lease, context budget, retries=read/reconcile first, 정확한 완료 집계 | 같은 요청 3회/프로세스 강제 종료/중복 호스트/순서 역전 시 중복 counted 0, side effects 0, 정상 복구; 1→3세대 |
| **P3 (S6, S9)** | 173 지표 활성 연구 어댑터 | feature registry 173항목의 계산·단위·입력자료·look-ahead·추가 데이터·licensing 조사; VERIFIED 신호를 academic typed `AlgorithmPlan`/컴파일러에 등록. 8개 운영 검증 지표를 단계적으로 확장. 수식/상태기계/Pine 유래 지표는 원본+원리·성능 재현 및 증거 보존 | 변경 목록별 replay·정렬·unit tests, 표준 S2 경로에서 신호 벡터/거래 확인, OOS/PIT 요구 충족 전 실거래/정식 승인 금지. 173 모두 통과한다고 선포 금지 |
| **P4 (S7/S8, F1–F5)** | Quant의 연구 기억과 판단 진화 | 실측 F3 효과를 F4 장기 연계 기억(`weakness→feature→trade IDs→S7 evidence→parent`)로 연결, F5 동일 예산 GPT/랜덤/부모 진화 효과 비교. 부적격 부모면 기준 하향 없이 신규 전략 탐색으로 복귀 | 저장 기록의 해시·실제 거래 ID 검증, 기록 변경 시 fail-closed, 다음 GPT 3~10세대에서 명시적 인용/가설 반전 관측, matched budget control; 자동 이익 보장 주장 금지 |
| **P5 (V3)** | 다중 부모 진화·국면별 복합 알고리즘 | `composite_crossover_v3`/`regime_router_v3`/`regime_portfolio_v3`를 기존 StrategyIR → S2 → S7 → 부모 계승에 정식 연결. 부모별 성과, 공통 NAV/현금·동시 익스포저, 국면 전환, 중복 체결·비용·위험 검증 | 합성만 성공한 전략은 counted 아님. 부모 해시/자식 고유성, 실제 fills 공유자본 보존, regime leakage 검사, 복합 전략 3세대 연속 S7 후 부모 승격 증명 |
| **P6 (Legacy)** | 이전 19개 레거시 경로 기능 동등성 | 과거 학술 대시보드 7, 체크포인트/복구 3, 정책 IR 5, provenance/PIT/control 4. 각 파일을 **동등 테스트 PASS / 안전한 selective port / 의도적 레거시 격리** 중 하나로 분류하고 추적 원장 문서에 이유 남김 | 19/19 행별 실제 증거, 빠진 기능 없으면 중복 이식 금지, protected core 위험 regression 0 |
| **P7 (T4 E2E)** | GPT/Quant/SDK 실제 연구 1→3→10→100 | 최종 typed 계획·진단·S7·부모·다른 탐색팔 모델 문맥·예산 집행·중단 복구 점검. 독립 원장은 계속 별개 | `COUNTED_REAL_GPT_MCP` 완결/해시/S7/실제 모델 출처 구분, 100/100이라도 비PIT 개발 연구로만 표기. 동일 예산 무작위 대조, QQQ·MDD·노출·거래수 보고 |
| **P8 (V01–V07 후속)** | PIT/OOS와 무주문·출시 | PIT/기업행동 시점 안전·독립 OOS 봉인, V06 paper-only, V07 3단계 GO/NO-GO, 최종 배포 전에 운영 브랜치와 원장 백업·rollback rehearsal | 원본 세션 복구, fixed URL/OAuth 영향 0, paper only, live orders 0. OOS 허가/거래 전환은 별도 승인 |

병렬성: 19개 레거시 조사와 지표·F4/V3 개발용 테스트는 P1/P2 호스트 연결 테스트와 병행할 수 있다. 하지만 **정식 GPT 100세대 검증·운영 승격은 P0→P1→P2 및 필요한 P3–P5 게이트가 선행**되어야 한다. 사용자가 승인한 V05→T4→V01–V04→V06→V07은 고정한다.

## 5. Quant에 넣어야 할 신규/수정 계약 (제안)

1. **SDK 실행 상태 레코드** — `run_id, session_id, requested, verified_completed, phase, budget_used, current_head_hash, dataset_hash, origin_branch_sha, paused_reason, safety_scope, last_model_turn_attestation_class`. 원본 `generations`는 복제·수정하지 않음.
2. **모델 턴 요청 전달자** — host-session capability detection, model-context ref and typed schema, per-stage budget, no unsafe server-sampling fallback. 구현 전 호스트 지원 방식 조사 필수.
3. **최소 상태 MCP API** — 기존 32도구로 가능한 것 우선 사용. 정말 필요한 SDK `dispatch/resume/stop` 기능만 opt-in 별도 계약으로 추가하되 기존 tool naming/ABI 불변. 도구 수가 늘면 하위 호환성 테스트와 허가 필요.
4. **정식 출처 증명 격리** — GPT model-self-reported tokens/turn IDs, 독립 provider invocation, signed external collector, test fixture 각각 다른 속성으로 보존. 어느 것도 다른 증명으로 자동 승격하지 않음.
5. **가설의 실험이익/무효 구분** — G1→G2 전후 백테스트 결과와 paired S7 반증, 비용·표본·시장 노출 및 시장 레짐별 개선 근거를 Quant가 저장. SDK는 `complete/blocked`만 검사.

## 6. 실패 시 행동

- **모델 호스트 없음 / 권한 만료:** 상태 `BLOCKED_MODEL_HOST_DISPATCH`로 정지; 원장 변경 0, 인증 재등록 자동 시도 0.
- **수정 불가/부적격 부모:** Quality Gate 우회 금지; 다음 세대는 부모 없는 새 전략 탐색 가능 (별도 테스트로 확인된 P4 패치).
- **계획 중복/지표 미등록/무효 단위/거래 0건:** 새 모델 연구 요청 전 preflight에서 거절하고 이유 기록; `counted_generation` 증가 0.
- **중복 송신/중단된 응답:** `reconcile` 후 원장·checkpoint token 확인; 무조건 재전송하지 않음.
- **S7 누락/수익 계산 불일치:** 보류·다음 세대 차단; 증거 없는 `COMPLETED` 금지.
- **벤치마크 미측정/데이터 공급자·PIT 부재:** missing을 실제 벤치마크 열위 0으로 대체 금지; 개발 평가에만 제한.
- **주문 권한 상승/OOS 접근 요구:** 즉시 보안 게이트 중단. 자동 승인 없음.

## 7. 보고 지표·최종 인수 기준

매 실세대는 ① 이전 부모/가설/실패 메모리 참조, ② 새 StrategyIR 또는 유효한 변형, ③ 원본 거래 ID/변동 증거, ④ S2 비용후 성과, ⑤ 실제 GPT 근거 진단·반례, ⑥ S7 수정 통제실험, ⑦ append-only hash·S7·parent 증거, ⑧ 다음 연구 방향이 **모두 완결**돼야 counted. 실패한 plan proposal, duplicate preflight, LLM 호출 횟수, API 요청 수는 세대 증가와 분리한다.

대시보드: 수익률·CAGR·MDD·Sortino·Sharpe·trade count·exposure·turnover·QQQ 동일기간 비교·회차별 토큰·개발/OOS 분리·선호 국면·부모 계보·상태 (`RUNNING`, `WAITING_HOST`, `AWAITING_PLAN`, `AWAITING_DIAGNOSIS`, `BLOCKED`, `COMPLETED`)를 표시; 68/100, P5 28/100, PythonMCP 33/100, deterministic 100/100을 절대 자동 합산하지 않는다.

**실제 완료 정의:** (A) SDK 모델 판단 불개입 및 Quant↔ChatGPT 원래 MCP ABI 유지, (B) 실제 모델 호스트 증빙된 10/100 연속 세대(결정론적 fixture 불가), (C) 과거 연구원장 온전, (D) 검증된 지표·F4·V3/레거시 항목의 출처·활성 범위 명확, (E) 0 주문·0 OOS 개봉, (F) 저장소 전체 회귀/타입/문서/복구 검증과 GitHub branch/rollback 확인. OOS/수익성은 별도 단계 목표.

## 8. 바로 다음 개발 묶음(3개 작업 단위)

1. **M0 환경·호스트 실증:** 기존 로그인·고정 Quant MCP 사용, native ChatGPT 호스트에서 SDK→연속 turn 실행 가능 여부를 단일 연구 턴으로 입증. 불가능하면 정확한 blocker 진단서 작성, 기존 모델 API 기본값 변경 금지.
2. **R1 상태기계/중복방지 TDD:** 운영 별개 격리 세션에서 checkpoint 1/3세대, 프로세스 crash+resume, budget-exhaustion 검증. SDK는 계획·진단 내용을 만들어내지 않음.
3. **지표→typed Compiler 경로 조사:** 173개 등록–계산–unit–lookahead–live academic eligible 매핑 표 자동 출력, 실사용 가능한 우선 그룹부터 incremental compile+costed replay 테스트.

완료 보고 시에는 작업 SHA/테스트/원격 PUSH와 남은 P0/P1/선행조건을 `docs/operations/autoresearch-master-progress.md`에 실제대로 기록한다. 새 운영 배포·OAuth·승인없는 외부 모델 API 교체는 이 문서의 범위가 아니다.
