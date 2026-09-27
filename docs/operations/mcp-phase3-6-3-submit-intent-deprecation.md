# MCP Phase 3-6.3 — submit_research_intent soft deprecation

## 목적

`submit_research_intent`를 실제 제거하기 전에 기존 caller를 깨지 않는 soft-deprecation
단계를 적용한다.

이번 단계에서도 `tools/list`는 **18개**를 그대로 유지한다.

## 변경 내용

### Tool description

기존:

```text
Validate and record a ResearchIntent.
```

현재:

```text
[DEPRECATED] Validate and record a ResearchIntent only; this does not execute research.
Use start_system for managed research, run_evaluation for one-shot evaluation,
validate_strategy for static validation, and get_system_status for progress.
```

비표준 `deprecated=true` 같은 Tool schema metadata는 추가하지 않았다.

### 성공 응답

기존 payload의 필드는 그대로 유지한다.

예:

```json
{
  "status": "VALIDATED",
  "intent": {
    "...": "..."
  }
}
```

여기에 additive compatibility metadata만 추가한다.

```json
{
  "status": "VALIDATED",
  "intent": {
    "...": "..."
  },
  "_compatibility": {
    "status": "DEPRECATED",
    "replacement_tools": [
      "start_system",
      "run_evaluation",
      "validate_strategy",
      "get_system_status"
    ],
    "note": "This tool only validates and records an intent; it does not execute research. Use start_system for managed research or run_evaluation for one-shot evaluation."
  }
}
```

## 기존 동작 보존

`ResearchService.validate_and_record_intent()`는 변경하지 않았다.

따라서 실제 동작은 여전히:

```text
ResearchIntent validation
→ sanitize
→ state/llm/intents.jsonl append
→ VALIDATED response
```

이다.

Compatibility metadata는 MCP adapter에서만 붙인다.

따라서 journal에는:

- `_compatibility`
- `DEPRECATED`
- replacement Tool 정보

가 기록되지 않는다.

즉 audit/supporting journal의 의미를 오염시키지 않는다.

## 실패 호출

잘못된 ResearchIntent는 기존처럼 validation error가 발생하고 generic MCP tool error로
처리된다.

Soft-deprecation 때문에 invalid payload가 기록되거나 compatibility metadata가
journal에 쓰이지 않는다.

## Replacement 기준

호출 목적별 migration은 다음과 같다.

- managed 자동 연구 실행 → `start_system`
- 단일 전략/세대 평가 → `run_evaluation`
- 전략 정적 검증 → `validate_strategy`
- 연구 진행 상태 확인 → `get_system_status`

새로운 external intent consumer는 추가하지 않는다.

## 공개 surface

Phase 3-6.3에서는 다음이 유지된다.

```text
tools/list count = 18
submit_research_intent visible = true
inputSchema unchanged = true
dispatch unchanged = true
```

즉 soft deprecation일 뿐 실제 hiding/removal은 아니다.

## 다음 단계

Phase 3-6.4에서 목표 공개 surface를 13개로 전환한다.

`tools/list`에서 숨길 대상:

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

단 Phase 3-6.7까지는 기존 caller 호환을 위해 legacy direct dispatch를 유지한다.

따라서 3-6.4의 핵심 검증은:

1. `tools/list` exact 13
2. 제거된 5개가 list에는 없음
3. legacy direct calls는 여전히 기존 동작
4. legacy call 결과에는 migration metadata
5. hidden dispatch를 security boundary로 취급하지 않음

이다.
