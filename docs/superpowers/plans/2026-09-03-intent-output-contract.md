# Intent Output Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고정된 canonical ResearchIntent 출력 계약으로 LLM 의미 오류와 반복 복구 호출을 차단한다.

**Architecture:** Pydantic discriminated operation 모델이 Codex 출력의 자료형을 고정하고, intent bridge가 부모 Strategy IR 기준 경로·타입·등록 여부를 검증한다. Research loop는 안정적인 오류 signature를 기록하고 동일 복구 결과를 재호출하지 않으며, 실패 세대는 부모 baseline fallback으로 계속 진행한다.

**Tech Stack:** Python 3.10+, Pydantic v2, pytest, JSON Schema, 기존 Strategy IR mutation engine.

---

### Task 1: Canonical operation 모델 테스트

**Files:**
- Modify: `tests/research/test_director.py`
- Modify: `tests/research/test_intent_bridge.py`

- [ ] **Step 1: Write failing tests**

추가할 테스트는 `ResearchIntent`가 `ADD_REGIME_FILTER`의 `condition` 객체를 허용하고,
`value=True`나 `condition=True`를 거부하며, canonical `SET_PARAMETER`가 typed operation으로
변환되는지 검증한다.

- [ ] **Step 2: Run focused tests and confirm RED**

`python -m pytest -q tests/research/test_director.py tests/research/test_intent_bridge.py`

현재 operation이 dict 기반이므로 새 모델 import 또는 잘못된 condition 검증에서 실패해야 한다.

### Task 2: Typed ResearchIntent와 schema 구현

**Files:**
- Modify: `research/llm/director.py`
- Modify: `research/llm/codex_schema.py`
- Modify: `research/llm/intent_bridge.py`
- Modify: `tests/research/test_director.py`
- Modify: `tests/research/test_intent_bridge.py`

- [ ] **Step 1: Add typed operation union**

`RETAIN`, `SET_PARAMETER`, `ADD_RULE`, `REPLACE_RULE`, `ADD_REGIME_FILTER`, remove 계열,
`CHANGE_AND_OR`, `ADD_FEATURE` 모델을 `extra='forbid'`로 정의하고 `ResearchIntent.operations`
가 이 union을 받도록 한다.

- [ ] **Step 2: Add canonical-to-mutation conversion**

canonical operation은 기존 `MutationOperation`으로 변환한다. `ADD_RULE`,
`ADD_REGIME_FILTER`는 `Condition.model_validate()` 결과만 전달한다.

- [ ] **Step 3: Preserve legacy normalization only at the boundary**

기존 JSON Patch payload가 저장된 기록과 테스트를 깨지 않도록 bridge 내부에서만 변환하고,
Codex schema에는 canonical operation union만 노출한다.

- [ ] **Step 4: Run focused tests**

`python -m pytest -q tests/research/test_director.py tests/research/test_intent_bridge.py tests/research/test_codex_exec.py`

### Task 3: Parent IR 경로·타입 preflight 강화

**Files:**
- Modify: `research/llm/intent_bridge.py`
- Modify: `tests/research/test_intent_bridge.py`

- [ ] **Step 1: Add path target tests**

`regime_filters.0`에 add하는 payload와 condition 자리에 bool/list를 넣는 payload가
`IntentEligibilityError`와 안정적인 오류 코드를 내도록 한다.

- [ ] **Step 2: Implement path registry and typed checks**

operation별 허용 대상과 부모 IR의 실제 container를 확인한다. add는 리스트 전체,
replace/remove는 유효한 리스트 원소 또는 실제 필드만 허용한다.

- [ ] **Step 3: Run regression tests**

`python -m pytest -q tests/research/test_intent_bridge.py tests/mutation/test_operations.py`

### Task 4: Codex prompt와 복구 dedup 기록

**Files:**
- Modify: `research/llm/codex_exec.py`
- Modify: `runtime/research_loop.py`
- Modify: `tests/research/test_codex_exec.py`
- Modify: `tests/runtime/test_autoresearch_loop.py`

- [ ] **Step 1: Test canonical prompt contract**

Codex 요청이 canonical operation, typed condition, JSON Patch 금지, 오류 코드 기반 복구를
명시하는지 검증한다.

- [ ] **Step 2: Add stable error and payload signatures**

오류 코드와 canonical JSON payload를 정규화해 signature를 만들고, 같은 signature의
복구 결과는 다음 Codex 호출 전에 차단한다.

- [ ] **Step 3: Persist repair knowledge**

`state/system/repair-knowledge.jsonl`에 민감정보를 제거한 오류·작업·결과·duration을 기록한다.

- [ ] **Step 4: Run focused runtime tests**

`python -m pytest -q tests/research/test_codex_exec.py tests/runtime/test_autoresearch_loop.py`

### Task 5: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/operations/recovery.md`
- Modify: `.env.example`

- [ ] **Step 1: Document canonical output and fallback behavior**

운영자가 오류 코드, repair knowledge, `FALLBACK`을 해석하고 주문이 비활성화된 상태를
확인할 수 있도록 한국어 설명을 추가한다.

- [ ] **Step 2: Run required checks**

`python -m pytest -q`, `ruff check .`, `python -m mypy .`, `git diff --check`

- [ ] **Step 3: Commit implementation atomically**

관련 구현·테스트·문서만 stage하여 `feat: enforce typed research intent contract`로 커밋한다.
