# MCP Phase 6.1 — Post-cutover stabilization inventory

## 목적

Phase 5에서 공식 Python MCP SDK가 canonical transport가 되었지만, cutover 직후 구조에는
의도적으로 rollback window를 위한 legacy 코드가 남아 있다.

Phase 6의 목표는 이 rollback 경로를 즉시 삭제하는 것이 아니다. 목표는 **canonical SDK 경로와
legacy manual transport의 코드 소유권을 명확히 분리해, 공식 SDK가 legacy protocol 구현에
의존하지 않도록 안정화**하는 것이다.

기계 판독 가능한 정본은
`docs/operations/mcp-phase6-1-post-cutover-inventory.json`이다.

현재 보존 계약:

```text
canonical transport = official_sdk
public tools = 13 public
hidden compatibility = 5 hidden legacy
public response contract = v1
runtime snapshot = v2
orders_enabled=false
manual rollback = verified and retained
```

## 현재 구조

Phase 5.5 이후:

```text
integrations.codex_mcp_server
  -> integrations.codex_mcp_sdk_server
      -> integrations.codex_mcp_core
      -> integrations.codex_mcp_protocol.text_content

integrations.codex_mcp_manual_server
  -> integrations.codex_mcp_core
  -> integrations.codex_mcp_protocol.serve_lines
```

canonical entrypoint 자체는 공식 SDK지만, 내부 의존성 관점에서는 legacy transport helper가
아직 완전히 격리되지 않았다.

## 확인된 기술부채

### 1. SDK adapter가 legacy protocol module의 serialization helper를 사용

`codex_mcp_sdk_server.py`는 Tool payload를 JSON text content로 만들기 위해
`codex_mcp_protocol.text_content`를 import한다.

이 helper의 직렬화 규칙 자체는 transport-neutral하게 재사용할 가치가 있지만,
파일 소유권이 legacy protocol module에 있어 canonical SDK가 rollback 구현에 의존하는 형태가 된다.

따라서 Phase 6.2에서 **neutral payload codec**으로 분리한다.

### 2. shared core 안에 manual JSON-RPC envelope 처리 코드가 남아 있음

`CodexMCPServer.handle()`은 다음 책임을 가진다.

- raw mapping request validation
- initialize/ping/tools/list/tools/call routing
- JSON-RPC success/error envelope 생성
- 2024-11-05 protocol response

이는 application dispatch가 아니라 manual transport 책임이다.

현재 많은 regression test가 이 `handle()`을 직접 호출하므로 Phase 5.5 cutover에서는
의도적으로 그대로 보존했다.

Phase 6.3에서는 **manual JSON-RPC ownership**을 rollback adapter 쪽으로 이동하고,
shared core는 Tool schema/dispatch/application contract만 소유하게 한다.

### 3. shared core가 legacy protocol helper를 import

현재 `codex_mcp_core.py`는 다음 helper를 import한다.

```text
error
success
text_content
```

이 의존은 주로 `handle()`과 `_tool_error()` 때문에 존재한다.

Phase 6.2~6.3 완료 후 shared core가 `codex_mcp_protocol.py`를 import하지 않는 것을 목표로 한다.

### 4. hidden legacy Tool과 manual rollback transport는 서로 다른 문제

다음 5개 hidden legacy Tool:

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

은 **Tool surface migration compatibility**다.

반면 `codex_mcp_manual_server`는 **transport rollback**이다.

둘을 동시에 삭제 대상으로 취급하면 안 된다.

Phase 6에서는:

```text
manual rollback transport deletion = NO
hidden legacy direct-dispatch deletion = NO
```

를 기본값으로 한다.

둘의 제거는 각각 별도 근거와 별도 승인 이후에만 수행한다.

## Phase 6.2 — neutral payload codec extraction

목표:

- JSON text payload 직렬화를 transport-neutral 모듈로 이동
- SDK adapter는 legacy protocol module을 import하지 않음
- manual transport도 같은 neutral codec을 재사용
- 기존 `ensure_ascii=True`, key sort 및 payload wire text semantics 유지

예상 구조:

```text
integrations/codex_mcp_payload.py
  -> encode_tool_payload / text payload helper

codex_mcp_sdk_server
  -> codex_mcp_payload

codex_mcp_protocol
  -> codex_mcp_payload
```

이 단계에서는 `handle()`을 이동하지 않는다.

## Phase 6.3 — manual JSON-RPC ownership isolation

목표:

- raw JSON-RPC `handle()` 책임을 manual rollback layer로 이동
- shared core는 Tool dispatch와 contract metadata만 담당
- canonical SDK와 manual rollback이 같은 dispatch core를 공유
- pre-cutover 2024 transport acceptance 계속 PASS

예상 구조:

```text
codex_mcp_core
  -> application dispatch only

codex_mcp_sdk_server
  -> official SDK envelope
  -> codex_mcp_core

codex_mcp_manual_server
  -> legacy JSON-RPC envelope
  -> codex_mcp_core

codex_mcp_protocol
  -> line framing / legacy response helpers
```

기존 `CodexMCPServer` Python import contract가 필요한 테스트/consumer는 migration shim 또는
명시적 manual adapter test로 단계적으로 옮긴다.

## Phase 6.4 — post-cutover contract and documentation consolidation

Phase 6.2~6.3 이후 다음을 다시 검증한다.

- canonical SDK subprocess PASS
- 2024 client compatibility PASS
- manual rollback subprocess PASS
- 13 public Tool exact
- 5 hidden legacy direct dispatch exact
- public contract v1
- RuntimeSnapshot v2
- sanitized error boundary
- `orders_enabled=false`
- full ruff / mypy / pytest PASS

또한 역사 문서와 현재 운영 문서를 명확히 구분한다.

특히 과거 문서의:

```text
18 public Tool
manual transport canonical
shadow SDK
```

표현은 당시 이력으로 남기되 현재 운영 정본으로 오해되지 않게 한다.

## 삭제하지 않는 것

Phase 6 stabilization 동안 다음은 삭제하지 않는다.

- manual rollback transport
- `codex_mcp_protocol.py`
- hidden legacy 5 direct dispatch
- public Tool
- Application Service
- StrategyIR
- evaluation/finance logic
- KIS safety gate

rollback window 종료와 hidden compatibility 종료는 별도 결정이다.

## 안전 경계

Phase 6은 transport ownership 정리다.

다음 권한은 추가하지 않는다.

- order execution
- live account activation
- credential exposure
- sealed OOS promotion bypass
- arbitrary code MCP Tool

항상:

```text
orders_enabled=false
```

를 유지한다.

## Phase 6.1 검증

```text
ruff = PASS
mypy = PASS (163 source files)
pytest = PASS (772 tests)
```

## Phase 6.1 판정

현재 cutover 후 기술부채와 책임 경계를 전수조사했고, 다음 순서를 확정했다.

```text
Phase 6.2 = neutral payload codec
Phase 6.3 = manual JSON-RPC ownership isolation
Phase 6.4 = final stabilization/contract consolidation
```

다음 작업은 **Phase 6.2 — neutral payload codec extraction**이다.
