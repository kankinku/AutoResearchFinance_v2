# MCP Phase 3-5.3 — Research 상태 집계 정밀화

## 목표

Phase 3-5.2의 typed `RuntimeSnapshot` 중 `runtime.research`를 정밀화한다.

이번 단계는 generation/phase/Intent를 다시 만드는 작업이 아니다. 기존
`system/autoresearch.json` projection을 읽어 다음 운영 정보를 추가한다.

- 전체 generation 진행률
- 마지막 완료 generation
- 마지막 non-degraded generation
- 현재 phase 경과시간
- 마지막 event 이후 경과시간
- phase별 stale 판정
- phase/event/generation projection 일관성

Snapshot 읽기는 계속 side-effect free다.

## 추가 필드

`runtime.research`에 다음 필드가 추가된다.

- `completion_percent`
- `last_completed_generation`
- `last_completed_status`
- `last_non_degraded_generation`
- `phase_started_at`
- `phase_age_seconds`
- `last_event_age_seconds`
- `stale_after_seconds`
- `is_stale`
- `consistency_status`
- `consistency_issues`

기존 필드는 그대로 유지한다.

## Generation 의미

`autoresearch.json.generations[]`는 generation이 끝난 뒤에만 record가 append된다.
따라서 valid generation record가 존재하면 해당 generation은 완료된 것으로 해석한다.

`last_completed_generation`은 가장 큰 generation 번호다.

`last_non_degraded_generation`은 status가 `DEGRADED`가 아닌 가장 최근 완료
generation이다. 이는 투자 성과가 좋았다는 뜻이 아니라, research generation 실행이
degraded fallback-only failure 상태로 끝나지 않았다는 운영 의미다.

`REJECT`도 평가가 정상 수행된 연구 generation이므로 non-degraded로 취급한다.

## 진행률

진행률은 다음으로 계산한다.

```text
completed_generations / requested_generations * 100
```

0~100 범위로 제한하고 소수점 한 자리까지 제공한다.

요청 generation이 0이거나 유효하지 않으면 0.0이다.

## Stale 판정

stale은 `status == RUNNING`인 경우에만 판정한다.

마지막 event timestamp와 현재 시각의 차이가 현재 phase별 보수적 threshold를
초과하면 `is_stale=true`가 된다.

| Phase | stale threshold |
|---|---:|
| STARTING | 300s |
| GENERATION | 300s |
| PROPOSING | 600s |
| VALIDATING | 300s |
| REPAIRING | 600s |
| BACKTESTING | 1800s |
| FINALIZING | 300s |

PROPOSING/REPAIRING은 현재 Codex timeout 300초보다 여유를 두었고,
BACKTESTING은 evaluation job timeout 900초보다 충분히 긴 1800초를 사용한다.

이 값은 프로세스를 자동 종료하는 timeout이 아니다. MCP 관측성에서 “오랫동안
새 event가 없다”는 것을 표시하는 diagnostic threshold다.

terminal phase에는 stale threshold를 적용하지 않는다.

## Consistency 검사

`consistency_status`는 `OK / WARN / UNKNOWN`이다.

다음 projection 이상을 코드로 제공한다.

- `COMPLETED_EXCEEDS_REQUESTED`
- `GENERATION_RECORD_COUNT_MISMATCH`
- `CURRENT_GENERATION_BEHIND_COMPLETED`
- `CURRENT_GENERATION_EXCEEDS_REQUESTED`
- `EVENT_PHASE_MISMATCH`
- `TERMINAL_PHASE_MISMATCH`
- `COMPLETED_RUN_GENERATION_MISMATCH`
- `TERMINAL_EVENT_MISSING`

예를 들어 `last_event=run_completed`인데 `current_phase=BACKTESTING`이면
`EVENT_PHASE_MISMATCH`와 `TERMINAL_PHASE_MISMATCH`가 표시된다.

이 검사는 상태를 수정하지 않는다. 잘못되거나 오래된 projection을 관측성 계층에서
드러내기만 한다.

## Event ↔ Phase 계약

현재 autoresearch emitter의 event 계약을 Snapshot에 명시적으로 반영한다.

- run_started → STARTING
- generation_started → GENERATION
- proposal_* → PROPOSING
- preflight_completed → VALIDATING
- repair_* → REPAIRING
- evaluation_* / fallback_evaluation_* → BACKTESTING
- generation_completed → FINALIZING
- run_failed → FAILED
- run_completed → COMPLETED
- run_interrupted → INTERRUPTED

알 수 없는 future event는 임의로 오류로 판정하지 않는다.

## 안전성과 호환성

이번 단계에서 변경하지 않는다.

- MCP tool 이름/입력 schema
- CLI
- StrategyIR
- evaluation/evidence semantics
- KIS permission/live gate
- paper-only order restriction

raw error/message나 ResearchIntent rationale도 새 필드에 포함하지 않는다.

## 다음 단계

기존 계획의 Phase 3-5.4는 Evaluation Job 상태 집계다.

다만 Phase 3-5.2에서 이미 queue counts, active/queued jobs, latest execution을
typed contract로 통합했으므로 3-5.4에서는 이를 중복 구현하지 않고,
retry/timeout/terminal attempt history와 queue health를 정밀화하는 범위로 좁힌다.
