# MCP Phase 3-5.1 — Runtime 상태 데이터 전수조사

기준 커밋: `ad4efda`
조사일: 2026-09-27

## 1. 결론

현재 저장소에는 이미 `runtime/runtime_snapshot.py`가 존재하며, 연구 진행 상태·평가 Job·Evidence 일부를 통합해서 `SystemController.status()`의 `runtime` 필드로 노출한다.

따라서 다음 단계는 RuntimeSnapshot을 새로 만드는 작업이 아니다. 현재 구현을 기준으로 상태 소스의 권위 순서를 명시하고, 아직 Snapshot에 빠진 ResearchIntent·LLM·worker/process·recovery·Knowledge/champion/frontier 계층을 안전하게 합치는 작업이어야 한다.

현재 상태는 세 종류로 나뉜다.

1. **강한 정본(authoritative durable state)**
   SQLite transaction 또는 immutable journal로 보호되는 Evaluation Queue와 Research Evidence.
2. **복구 가능한 최신 projection**
   `system.json`, `autoresearch.json`, worker status, heartbeat, `knowledge.json` 등.
3. **진단·호환·캐시 상태**
   JSONL 로그, dashboard cache, legacy test ledger, 초기화 placeholder.

RuntimeSnapshot은 이 세 층을 같은 신뢰도로 취급해서는 안 된다.

---

## 2. 상태 소스 권위 등급

| 등급 | 의미 | 사용 원칙 |
|---|---|---|
| **A — 정본** | transaction/무결성 규칙이 있는 durable state | 충돌 시 최우선 |
| **B — 최신 projection** | 원본 상태로부터 재구성 가능하거나 현재 상태 표시용 | 정본과 일치 여부 확인 후 사용 |
| **C — audit/diagnostic** | 사건 기록·진단 로그 | 설명·최근 이벤트용, 상태 판정 정본으로 사용하지 않음 |
| **D — cache/legacy** | UI cache 또는 구 버전 호환 데이터 | fallback/표시용 |
| **E — placeholder** | 초기 구조는 있으나 현재 canonical loop에서 갱신되지 않음 | 존재만으로 실제 상태라고 판단하지 않음 |

---

## 3. 전체 Runtime 상태 맵

### 3.1 Managed system / process lifecycle

| 경로 | 등급 | Writer | Reader | 갱신 시점 | Scope / 복구 의미 |
|---|---|---|---|---|---|
| `state/system/system.json` | B | `SystemController` | `start/status/stop` | system start/stop | `managed_run_id`, PID, process identity marker 저장. 실제 생존 여부는 OS process table과 재검증해야 함 |
| OS process table | A* | OS | `process_lifecycle`, `SystemController` | 실시간 | 프로세스 생존성 정본. 단 PID만 믿지 않고 command-line marker와 함께 확인 |
| `state/system/lifecycle.lock` | B/lock | `lifecycle_lock` | start/stop | lifecycle 변경 동안 | 상태 데이터가 아니라 cross-process serialization primitive |
| `state/system/research_worker.json` | B | `runtime.system_worker` | `SystemController` | worker 시작/성공/실패 | `managed_run_id`로 현재 managed run과 일치 여부 확인 |
| `state/system/dashboard-supervisor.log` | C | dashboard supervisor | 운영자 | supervisor 이벤트 | 진단 로그. 상태 정본 아님 |

`system.json`은 “이 Controller가 무엇을 관리하도록 시작했는가”의 정본에 가깝지만, 프로세스가 지금 살아 있는지 여부는 OS 확인 결과가 우선한다.

### 3.2 Autoresearch 진행 상태

| 경로 | 등급 | Writer | Reader | 갱신 시점 | 의미 |
|---|---|---|---|---|---|
| `state/system/autoresearch.json` | B | `_ResearchProgress/_write_autoresearch_status`, recovery | RuntimeSnapshot, Dashboard, recovery | phase/event 변화마다 atomic replace | 현재 generation, phase, last event, repair attempt, timing, generation record를 담는 최신 projection |
| `state/system/research-events.jsonl` | C | `_ResearchProgress` | legacy Streamlit dashboard/tests | 각 research event | 세부 phase timeline. append-only지만 checksum/transaction 없음 |
| `state/system/research_loop.json` | D/B | repeated-evaluation/Mimir path | Mimir config recovery | 반복 평가 상태 갱신 | canonical autoresearch와 별도인 호환 경로. 현재 managed autoresearch 상태와 혼합하면 안 됨 |
| `state/system/repair-knowledge.jsonl` | C | `research_loop` | 운영 문서/tests | repair/fallback 사건 | intent repair 진단 기록. 현재 RuntimeSnapshot은 읽지 않음 |
| `state/system/feature-proposals.jsonl` | C | `research_loop` | tests | feature proposal 발생 | feature lifecycle audit. 현재 RuntimeSnapshot은 읽지 않음 |

`autoresearch.json`은 실시간 UI에 가장 적합하지만 immutable history가 아니다. crash 후 `recovery_state.mark_autoresearch_interrupted()`가 RUNNING을 INTERRUPTED로 바꿀 수 있다.

### 3.3 ResearchIntent / LLM 상태

| 경로 | 등급 | Writer | Reader | 갱신 시점 | 문제점 |
|---|---|---|---|---|---|
| `state/llm/intents.jsonl` | C+ | `record_intent`, ResearchService, autoresearch | 직접 runtime reader 없음 | validated/repaired intent마다 | timestamp + intent만 있고 `research_run_id/generation` 연결이 없음 |
| `state/llm/status.json` | B/C | `CodexExecProvider` | DashboardStateReader | proposal/repair call 전후 | provider ONLINE/OFFLINE/last_result/last_call. RuntimeSnapshot 미포함 |
| `autoresearch.json.generations[].intent` | B | autoresearch | Dashboard generation view | generation 완료 시 | 현재 run과 generation에 연결된 Intent를 알 수 있는 가장 직접적인 projection |

**중요:** “현재/마지막 ResearchIntent”를 Snapshot에 넣을 때 `llm/intents.jsonl`만 읽으면 run/generation 귀속이 불명확하다. 현재 managed run에서는 `autoresearch.json.generations`와 현재 phase를 우선하고, intents.jsonl은 audit 보조 자료로 사용해야 한다.

### 3.4 Evaluation Job

| 경로 | 등급 | Writer | Reader | 갱신 시점 | 의미 |
|---|---|---|---|---|---|
| `state/system/evaluation-jobs/queue.sqlite` | **A** | `PersistentJobQueue`, executor, worker, controller recovery | executor, worker, SystemController, RuntimeSnapshot | enqueue/claim/succeed/fail/timeout/retry/cancel | Evaluation Job lifecycle 정본 |
| `state/system/evaluation-jobs.jsonl` | C | `QueuedEvaluationExecutor` | RuntimeSnapshot latest_job | 각 attempt 종료 | execution_mode, isolation, timeout 등 운영 로그. queue 상태를 덮어쓰면 안 됨 |
| `state/worker-heartbeats/*.json` | B/C | LocalScheduler / evaluation worker | Dashboard | worker 상태 변화 | freshness/last heartbeat. Job status 정본은 queue.sqlite |

현재 RuntimeSnapshot의 Job count와 active/queued 목록은 올바르게 `queue.sqlite`를 우선한다. `evaluation-jobs.jsonl`은 latest execution 설명에만 사용하므로 방향이 적절하다.

### 3.5 Research Evidence

| 경로 | 등급 | Writer | Reader | 갱신 시점 | 무결성 |
|---|---|---|---|---|---|
| `state/system/research-evidence/evidence.sqlite` | **A** | `EvidenceStore/EvidenceSession` | research evidence, knowledge projection, RuntimeSnapshot | run/manifest/attempt/generation/end | append-only, unique event id, checksum 검증, UPDATE/DELETE trigger 차단 |

현재 시스템에서 연구 결과의 가장 강한 정본이다.

RuntimeSnapshot의 `evidence`는 이 DB를 읽고 현재 `research_run_id`와 연결한다. 이것도 올바른 방향이다.

### 3.6 Knowledge

| 경로 | 등급 | Writer | Reader | 갱신 시점 | 의미 |
|---|---|---|---|---|---|
| `state/knowledge.json` | **B (derived projection)** | `sync_knowledge()` | Dashboard, Research context | Evidence 동기화 시 | `evidence.sqlite`에서 재생성 가능 |
| `failure_context()` | derived view | runtime computation | ResearchContext | context 작성 시 | knowledge.json 임의 필드를 믿지 않고 Evidence journal에서 실패 패턴 재구성 |

Knowledge의 정본은 `knowledge.json`이 아니라 Evidence다. Snapshot에서 knowledge 수치를 표시할 경우 JSON을 그대로 신뢰하기보다 Evidence 또는 검증된 projection을 사용해야 한다.

### 3.7 Champion / Frontier / Rescue

| 경로 | 등급 | Writer | Reader | 현 상태 |
|---|---|---|---|---|
| `state/champion.json` | B | workspace init, `memory.promotion` | Dashboard/Workspace | 실제 promotion 경로가 호출되면 갱신 가능 |
| `state/frontier.json` | **E** | workspace init 외 현재 production persistence writer 확인 안 됨 | Dashboard, research_evidence | 구조는 존재하지만 current canonical loop의 durable frontier 정본으로 볼 수 없음 |
| `state/rescue_pool.json` | **E** | workspace init 외 현재 production persistence writer 확인 안 됨 | Dashboard | 동일 |
| in-memory `Frontier` / `RescuePool` | process-local | orchestration policies/tests | 일부 planning logic | durable runtime 상태가 아님 |

특히 `frontier.json`과 `rescue_pool.json`은 “파일이 존재한다”는 이유만으로 현재 연구 상태로 노출하면 안 된다.

현재 `ResearchService.context()`와 `build_research_context()`가 frontier를 빈 배열로 전달하는 것도 durable frontier가 아직 연결되지 않았기 때문이다.

### 3.8 Dashboard / Evaluation ledger

| 경로 | 등급 | Writer | Reader | 의미 |
|---|---|---|---|---|
| `state/test-records.jsonl` | D/B | evaluation/dashboard ledger | DashboardStateReader, legacy evidence counter | 후보/세대 결과용 호환 ledger. immutable Evidence와 중복 |
| `state/dashboard.json` | D cache | DashboardService refresh | DashboardService | KIS/account 포함 sanitized UI snapshot cache |
| `state/account.json` | D/B | 외부 snapshot workflow | Dashboard | paper account snapshot. research runtime 정본 아님 |
| `state/mode.json` | **B operator config** | workspace init/set-mode | preflight/dashboard | paper/live 요청값. effective live permission과 별개 |
| `state/audit.jsonl` | C | audit/promotion workflow | CLI/workspace status | promotion/audit history |

Dashboard는 여러 source를 조합하는 read model이다. 따라서 `dashboard.json`을 RuntimeSnapshot의 원본으로 사용하면 안 된다.

### 3.9 Recovery

| 경로 | 등급 | Writer | Reader | 의미 |
|---|---|---|---|---|
| `state/system/recovery-events.jsonl` | C | `recovery_state` | tests/운영자 | interrupted run 처리 기록 |
| `autoresearch.json = INTERRUPTED` | B | recovery | RuntimeSnapshot/SystemController | 현재 research projection의 복구 상태 |
| Evidence `end: INTERRUPTED` | **A** | recovery via EvidenceStore | evidence readers | 해당 research run의 immutable 종료 증거 |
| queue lease / `LeaseExpired` | **A** | PersistentJobQueue | controller/executor | evaluation worker crash 복구 |

복구 결과를 표시할 때는 recovery-events.jsonl보다 Evidence와 queue terminal state가 우선한다.

### 3.10 Experiment cache/result artifact

| 소스 | 등급 | 현재 연결 |
|---|---|---|
| `ExperimentCache` SQLite | D/cache | 실험 결과 캐시 abstraction. runtime canonical status와 분리 |
| `ExperimentResultStore` Parquet | artifact | generation 결과 파일 abstraction. 현재 RuntimeSnapshot source 아님 |

이 두 요소는 관측성 Snapshot의 핵심 source가 아니라 향후 cache/performance 진단용 source다.

---

## 4. 현재 RuntimeSnapshot이 이미 포함하는 것

현재 `runtime/runtime_snapshot.py`는 다음을 이미 구현했다.

### Research
- status
- research_run_id
- current_generation
- current_phase
- completed/requested generations
- last event / timestamp
- repair attempt
- timing summary
- error class

Source: `system/autoresearch.json`.

### Evaluation
- managed run 기준 status counts
- RUNNING Job
- QUEUED Job
- queue attempt / max attempts
- error class
- lease
- latest execution log

Source:
- 정본: `evaluation-jobs/queue.sqlite`
- 설명용: `evaluation-jobs.jsonl`

### Evidence
- current research run 연결 여부
- event count
- 마지막 event kind
- closed 여부
- terminal status

Source: immutable `evidence.sqlite`.

### Safety
- `orders_enabled=false`

따라서 원래 계획의 “3-5.2 RuntimeSnapshot 통합 모델을 처음 설계”는 이미 일부 완료된 상태다.

---

## 5. 현재 RuntimeSnapshot에 빠진 영역

다음은 실제 상태가 존재하지만 현재 Snapshot에는 없다.

1. **Managed process health**
   - dashboard PID/liveness
   - research worker PID/liveness
   - managed_run_id
   - aggregate system state

2. **Worker heartbeat**
   - online/stale/offline
   - last heartbeat
   - worker/job association

3. **LLM provider**
   - ONLINE/OFFLINE
   - last proposal/repair result
   - last call time

4. **ResearchIntent**
   - 현재 generation의 intent
   - intent status
   - repair 횟수 및 마지막 repair outcome

5. **Recovery**
   - interrupted 여부
   - last recovery event
   - orphan Job cleanup 결과

6. **Knowledge**
   - known_good / known_bad / unexplored counts
   - 최근 failure signature
   - Evidence와 projection sync 상태

7. **Champion**
   - current promoted champion
   - generation/score/hash
   - Evidence와 promotion audit 연결 여부

8. **Frontier / Rescue**
   - durable writer가 연결되기 전에는 “현재 상태”로 표현하면 안 됨
   - `NOT_CONNECTED` 또는 `INITIALIZED_ONLY` 같은 명시적 상태가 필요

9. **최근 오류**
   - autoresearch error
   - worker terminal error
   - evaluation error_class
   - LLM failure
   - recovery failure가 서로 다른 파일에 흩어져 있음

---

## 6. 중복 상태와 우선순위

### Evaluation
```text
queue.sqlite                  ← 정본
    ↓
evaluation-jobs.jsonl         ← attempt/실행 설명
    ↓
worker-heartbeats/*.json      ← freshness
```

상태 충돌 시 queue.sqlite를 따른다.

### Research 결과
```text
evidence.sqlite               ← 정본
    ↓
knowledge.json                ← 재생성 가능한 projection
    ↓
test-records.jsonl            ← dashboard/legacy ledger
    ↓
dashboard.json                ← UI cache
```

### Research 진행
```text
autoresearch.json             ← 최신 phase projection
research-events.jsonl         ← 상세 timeline
evidence.sqlite               ← 완료된 generation/run 정본
```

진행 중 phase는 autoresearch.json이 가장 유용하지만, 완료 여부가 충돌하면 Evidence end/generation event를 우선해야 한다.

### Process
```text
OS process + identity marker  ← 실제 생존성
system.json                   ← 관리 의도/PID/managed_run_id
research_worker.json          ← worker terminal projection
```

---

## 7. 발견된 구조적 위험

### 7.1 Snapshot과 System status가 아직 두 층이다

`SystemController.status()`가 process/lifecycle 상태를 계산한 뒤 그 안에 `runtime` Snapshot을 삽입한다.

즉 소비자는:

```text
system status
  + nested runtime snapshot
```

두 구조를 동시에 이해해야 한다.

다음 단계에서는 이것을 하나의 typed read model로 정규화하는 것이 좋다.

### 7.2 ResearchIntent 로그에 run identity가 없다

`llm/intents.jsonl`은 validated intent audit에는 유용하지만 현재 run/generation을 직접 연결할 수 없다.

다음 Snapshot에서는 현재 intent를 `autoresearch.json.generations`에서 읽는 것이 더 안전하다. 별도의 intent audit 개선은 후속 단계에서 `research_run_id/generation`을 기록하도록 변경하는 편이 좋다.

### 7.3 append-only JSONL은 “진짜 immutable”이 아니다

다음 파일은 append-only 사용 관례만 있고 EvidenceStore와 같은 checksum/DB constraint는 없다.

- `research-events.jsonl`
- `recovery-events.jsonl`
- `repair-knowledge.jsonl`
- `feature-proposals.jsonl`
- `llm/intents.jsonl`
- `evaluation-jobs.jsonl`
- `test-records.jsonl`

따라서 Snapshot은 이 파일들을 설명용 자료로만 사용해야 한다.

### 7.4 Frontier/Rescue는 read model이 실제 연결보다 앞서 있다

Dashboard가 `frontier.json`, `rescue_pool.json`을 읽지만 canonical autoresearch pipeline에서 해당 파일을 지속적으로 갱신하는 production writer는 확인되지 않았다.

현재 Snapshot에 이를 “0개”라고 표시하면 “연결은 됐는데 비어 있다”와 “아직 persistence가 연결되지 않았다”를 구분할 수 없다.

---

## 8. Phase 3-5.2에서 적용할 Source Priority

다음 RuntimeSnapshot 보강은 아래 우선순위를 고정한 뒤 구현해야 한다.

```text
1. OS process validation
2. PersistentJobQueue SQLite
3. EvidenceStore SQLite
4. system/autoresearch.json
5. system/system.json + worker status
6. verified derived projection (knowledge)
7. heartbeat/provider projection
8. diagnostic JSONL
9. dashboard/legacy cache
10. initialized-only placeholder
```

정본과 projection이 충돌하면 낮은 순위 자료가 높은 순위 자료를 덮어쓰면 안 된다.

---

## 9. Phase 3-5.2의 실제 작업 범위

기존 계획의 “RuntimeSnapshot을 새로 설계” 대신 다음으로 수정한다.

### 3-5.2 — Existing RuntimeSnapshot schema consolidation

1. 현재 dict 기반 Snapshot을 typed contract로 고정한다.
2. `SystemController.status()`의 process/lifecycle 정보와 RuntimeSnapshot을 한 read model로 합친다.
3. 현재 generation의 ResearchIntent를 `autoresearch.json` 기준으로 포함한다.
4. LLM provider와 worker heartbeat를 포함한다.
5. recovery 상태와 최근 sanitized error를 통합한다.
6. Knowledge/champion은 source provenance와 함께 포함한다.
7. frontier/rescue는 durable writer가 없는 동안 `NOT_CONNECTED`로 표시한다.
8. 모든 field에 source/authority를 직접 노출할 필요는 없지만 내부 구현은 위 Source Priority를 강제한다.
9. Snapshot 조회는 어떤 state 파일도 생성하거나 수정하지 않는 pure read여야 한다.

---

## 10. 3-5.1 완료 판정

이번 단계에서는 runtime 코드를 수정하지 않았다.

완료된 것은 다음과 같다.

- durable state source 전수 식별
- writer/reader/update timing 조사
- authoritative / projection / diagnostic / legacy / placeholder 분류
- current RuntimeSnapshot 기존 구현 범위 확인
- 중복 source의 우선순위 확정
- 다음 단계의 설계를 “신규 Snapshot 생성”에서 “기존 Snapshot consolidation”으로 수정

다음 작업은 **3-5.2 — Existing RuntimeSnapshot schema consolidation**이다.
