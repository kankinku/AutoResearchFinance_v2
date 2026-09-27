# MCP Phase 3-5.5 — Evidence / Knowledge 상태 집계 정밀화

## 목표

Phase 3-5.2에서 이미 노출하던 `runtime.evidence`, `runtime.knowledge`,
`runtime.strategy_state`를 더 정확하게 연결한다.

이번 단계는 Evidence 저장 방식, Knowledge 동기화 로직, champion promotion 규칙을
변경하지 않는다. 관측 계층에서 현재 상태와 provenance를 읽기 전용으로 검증한다.

## Evidence 정본

정본은 계속 다음 SQLite journal이다.

```text
state/system/research-evidence/evidence.sqlite
```

Snapshot은 journal을 한 번 검증해 전체 event를 읽고 그 결과를 Evidence, Knowledge,
Champion 관측에 공유한다.

checksum 또는 schema 검증에 실패하면 파생 상태를 추측하지 않는다.

```text
evidence.integrity_status = INTEGRITY_ERROR
knowledge.sync_status = EVIDENCE_INTEGRITY_ERROR
strategy_state.champion_evidence_status = EVIDENCE_INTEGRITY_ERROR
```

## Evidence 상세

기존 필드는 유지하며 다음을 추가한다.

- `link_status`
- `integrity_status`
- `manifest_present`
- `attempt_count`
- `generation_count`
- `last_event_id`
- `last_attempt_id`
- `last_attempt_status`
- `last_generation`
- `last_generation_status`
- `terminal_status`

`last_event_kind`과 `closed`도 기존과 동일하게 유지한다.

Evidence journal에는 timestamp가 없으므로 Snapshot이 임의 시간을 생성하지 않는다.
최신성은 immutable sequence order와 generation/attempt identity로만 표현한다.

## Evidence link 상태

- `NOT_LINKED`: 현재 research_run_id가 없음
- `LINKED`: 현재 research run에 Evidence event가 존재
- `MISSING_RUN`: research projection은 run ID를 가리키지만 Evidence journal에 없음
- `INTEGRITY_ERROR`: journal 검증 실패

현재 run의 terminal 상태는 `end` event가 있을 때만 사용한다.

## Knowledge projection 검증

`knowledge.json`은 정본이 아니라 Evidence에서 다시 만들 수 있는 projection이다.

Snapshot은 `sync_knowledge()`를 호출하지 않는다. 즉 조회만으로 Knowledge가
수정되지 않는다.

Evidence의 attempt candidate 중 다음 status만 projection 대상이다.

- REJECT
- NEAR_MISS
- SURVIVOR
- FRONTIER

실제 `memory.evidence_knowledge`와 같은 식으로
`research_run_id + attempt_id + candidate index + candidate_hash`에서
`experiment_id`를 재계산한다.

그 뒤 `knowledge.json`에 존재하는 experiment ID와 비교한다.

### sync_status

- `NOT_APPLICABLE`: projection 대상 Evidence가 없음
- `IN_SYNC`: 모든 Evidence experiment가 projection에 존재
- `STALE`: Evidence experiment 일부가 projection에 빠짐
- `MISSING`: Evidence는 있으나 knowledge.json 자체가 없음
- `INVALID`: knowledge.json 구조가 잘못됨
- `EVIDENCE_INTEGRITY_ERROR`: 정본 Evidence를 신뢰할 수 없음

추가 지표:

- `evidence_experiment_count`
- `projected_experiment_count`
- `missing_experiment_count`
- `unverified_entry_count`
- `projection_coverage_percent`

legacy/extension entry가 `experiment_id` 없이 남아 있을 수 있으므로
그 항목은 삭제하거나 오류 처리하지 않고 `unverified_entry_count`로만 표시한다.

## Champion provenance

`champion.json`의 candidate hash를 immutable Evidence attempt candidate에서 찾는다.

추가 필드:

- `champion_family`
- `champion_evidence_status`
- `champion_research_run_id`
- `champion_attempt_id`
- `champion_candidate_status`
- `promotion_audit_status`
- `promotion_audit_records`
- `last_promotion_at`

### champion_evidence_status

- `NO_CHAMPION`
- `LINKED`
- `NOT_FOUND`
- `EVIDENCE_INTEGRITY_ERROR`

Evidence에서 candidate hash가 발견되면 해당 attempt의 research run과 generation을
provenance로 사용한다. champion 파일 자체에 generation이 없을 때만 이 verified
Evidence generation을 `champion_generation` fallback으로 사용한다.

candidate hash가 Evidence에서 발견되지 않으면 임의 provenance를 만들지 않는다.

## Promotion audit

기본 운영 audit 경로는:

```text
state/audit.jsonl
```

Snapshot은 `event=promote_champion` record 개수와 가장 최근 timestamp만 읽는다.

중요한 제한이 있다. AuditLog는 promotion 입력 원문 대신 input hash를 저장하므로,
audit record 하나를 특정 champion candidate와 직접 연결했다고 주장할 수 없다.

따라서 `promotion_audit_status=PRESENT`는 “promotion audit trail이 존재한다”는
의미이고, champion 후보 자체의 provenance는 Evidence candidate hash 연결이 담당한다.

## Frontier / Rescue

이번 단계에서도 변경하지 않는다.

```text
frontier_status = NOT_CONNECTED
rescue_status = NOT_CONNECTED
```

durable production writer가 연결되기 전까지 초기화 파일을 실제 runtime 상태로
오인하지 않는다.

## Side-effect-free 원칙

Snapshot은 다음을 절대 수행하지 않는다.

- `sync_knowledge()`
- Evidence 수정
- Knowledge 수정
- champion promotion
- audit append
- frontier/rescue 생성

조회 전후 상태 파일은 동일하다.

## 호환성과 안전 경계

변경하지 않은 항목:

- EvidenceStore append semantics
- Knowledge sync semantics
- candidate promotion 조건
- audit write semantics
- MCP tool 이름/입력 schema
- CLI
- StrategyIR
- KIS/live permission
- order enablement

## 다음 단계

Phase 3-5.6에서는 이미 존재하는 research/evaluation/evidence 오류 정보를 기반으로
오류·복구 상태를 정밀화한다.

중복 구현 대신 다음에 집중한다.

- 최근 오류 source별 우선순위
- retry/recovery 결과 연결
- stale/orphan/interrupt 상태의 단일 health summary
- raw 오류 본문 비노출 유지
