# MCP Phase 5.1 — 공식 Python SDK 전환 인벤토리·호환성 설계

## 목적

Phase 5는 현재 직접 구현한 MCP JSON-RPC/STDIO transport를 공식 Python SDK로 교체하되,
이미 확정된 연구 기능과 안전 경계를 바꾸지 않는 transport migration이다.

Phase 5.1에서는 production transport를 변경하지 않는다. 현재 계약을 먼저 동결하고,
SDK adapter를 병렬로 추가한 뒤 검증 후 canonical entrypoint를 전환하는 순서를 확정한다.

현재 기준은 다음과 같다.

```text
advertised surface = 13 public
compatibility dispatch = 5 hidden legacy
public response contract = v1
runtime snapshot = v2
orders_enabled=false
transport = manual JSON-RPC over STDIO
```

기계 판독 가능한 정본은
`docs/operations/mcp-phase5-1-sdk-migration-inventory.json`이다.

## 현재 transport

현재 MCP 서버는 두 층으로 구성된다.

### `integrations/codex_mcp_protocol.py`

직접 구현한 기능:

- newline-delimited JSON decode/encode
- JSON-RPC success/error envelope
- `initialize`, `ping`, notification 처리에 필요한 transport loop
- text content serialization
- STDIO flush

### `integrations/codex_mcp_server.py`

현재 함께 들어 있는 기능:

- MCP method routing
- `tools/list`
- `tools/call`
- exact input schema 정의
- Application Service dispatch
- public `_contract` metadata
- legacy `_compatibility` metadata
- sanitized tool error 변환
- server identity

즉 business/application 계층은 이미 분리됐지만 protocol과 MCP adapter 책임은 아직
수동 구현에 남아 있다.

## 현재 보존해야 할 계약

SDK 전환은 기능 확장이 아니다.

### Public surface

`tools/list`에는 정확히 13 public Tool만 노출한다.

- initialize_research_state
- get_workspace_status
- validate_strategy
- import_strategies
- list_strategies
- list_features
- get_research_evidence
- get_dashboard_status
- run_evaluation
- check_system
- start_system
- get_system_status
- stop_system

Tool을 추가하거나 제거하지 않는다.

### Hidden compatibility

다음 5개 이름은 `tools/list`에는 나오지 않지만 기존 caller 호환을 위해
`tools/call`로 직접 호출할 수 있어야 한다.

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

hard removal은 Phase 5 범위에 포함하지 않는다. 별도 승인 없이는 삭제하지 않는다.

### Payload

public Tool의 application payload는 현재처럼 JSON text content로 유지한다.
payload 내부의 `_contract`는 계속 다음 의미를 가져야 한다.

```text
schema_version = 1
tool = <public tool>
plane = <existing public plane>
orders_enabled=false
```

legacy direct call의 `_compatibility` metadata도 보존한다.

## Target SDK

Target은 공식 Python MCP SDK v2의 저수준 `mcp.server.Server`다.

예정 dependency:

```text
mcp>=2.2,<3
```

Python 범위는 현재 프로젝트의 `>=3.10,<3.13`을 유지한다.

고수준 자동 schema 생성 방식보다 저수준 `mcp.server.Server`를 선택하는 이유:

1. 현재 Tool input schema를 그대로 전달해야 한다.
2. public/legacy dispatch를 하나의 handler에서 명시적으로 분리해야 한다.
3. application payload를 기존 JSON text content 형태로 정확히 제어해야 한다.
4. sanitized error result와 `isError` 의미를 직접 유지해야 한다.
5. SDK 자체 lifecycle/STDIO/protocol negotiation만 위임하고 연구 로직은 바꾸지 않아야 한다.

공식 low-level Server는 정확한 schema와 result를 직접 지정할 수 있고, 목록에 광고하지 않은
Tool name의 `tools/call`도 handler로 라우팅할 수 있다. 따라서 현재 13 public + 5 hidden legacy
구조를 유지하기에 적합하다.

## Protocol version 차이

현재 수동 서버는 initialize 응답을 `2024-11-05`로 고정한다.

공식 SDK v2는 2026 계열 protocol과 이전 revision을 함께 지원하며 negotiation을 SDK가 담당한다.
따라서 SDK cutover 이후에는 acceptance가 특정 protocol version 하나를 무조건 강제하는 방식보다
다음을 검증하도록 변경한다.

- client/server negotiation 성공
- server identity = `quant-autoresearch`
- public tool surface = exact 13
- legacy compatibility direct call = exact 5
- payload contract 유지
- `orders_enabled=false`

기존 2024-era client 호환성은 별도 regression으로 남긴다.

## Transport envelope와 payload 경계

SDK v2는 최신 protocol에서 결과 envelope에 server identity용 `_meta` 같은 additive metadata를
추가할 수 있다.

Phase 5에서 compatibility의 정본은 **application payload**다.

즉 다음은 보존한다.

- text content 내부 JSON payload
- public `_contract`
- legacy `_compatibility`
- `isError` 의미
- sanitization

반면 SDK가 표준 protocol envelope에 추가하는 비민감 표준 metadata는 허용할 수 있다.
단 credential, filesystem path, provider detail 같은 민감정보를 넣지 않는다.

## Error compatibility

현재 adapter는 Application Service 또는 argument validation에서 예외가 발생하면
원문 exception을 내보내지 않고 안전한 Tool error를 반환한다.

SDK adapter에서도 예외를 handler 밖으로 그대로 던져 SDK의 generic JSON-RPC 오류로
바꾸지 않는다. adapter 경계에서 잡아 기존과 동등한 sanitized `CallToolResult`로 변환한다.

보존 기준:

```text
isError = true
payload.status = ERROR
rejected path/url/credential/provider detail = not exposed
```

## 전환 방식: parallel adapter

한 번에 `codex_mcp_protocol.py`를 제거하지 않는다.

```text
existing Application Services
        |
existing MCP dispatch/schema definitions
        |
        +--> current manual STDIO adapter
        |
        +--> official SDK adapter (shadow)
                   |
              SDK STDIO
```

두 adapter가 같은 schema/dispatch source를 공유하도록 만들고 parity가 확인된 뒤에만
canonical entrypoint를 SDK 쪽으로 전환한다.

## 세부 단계

### Phase 5.2 — SDK dependency + adapter skeleton

- `mcp>=2.2,<3` 추가
- lockfile 갱신
- 저수준 `mcp.server.Server` adapter 모듈 추가
- 아직 canonical entrypoint는 수동 서버 유지
- import/startup와 Python 3.10~3.12 dependency contract 검증

### Phase 5.3 — Tool schema / dispatch parity

- existing Tool definitions를 SDK `Tool` object로 변환
- `tools/list` exact 13 검증
- 5 hidden legacy direct call 검증
- public `_contract` / legacy `_compatibility` / sanitized error parity 검증
- Application Service 호출 경로는 변경하지 않음

### Phase 5.4 — SDK STDIO shadow acceptance

- 공식 SDK 서버를 실제 subprocess STDIO로 실행
- 기존 수동 서버 acceptance와 동일한 public/legacy contract 비교
- old protocol client compatibility와 negotiated SDK protocol 검증
- production entrypoint는 아직 전환하지 않음

### Phase 5.5 — canonical cutover

- `python -m integrations.codex_mcp_server`를 SDK adapter로 전환
- Codex trusted MCP example과 운영 문서 갱신
- 기존 수동 protocol path는 rollback window 동안 명시적으로 격리
- full release gate 후에만 구 protocol 삭제 여부를 별도 결정

## Cutover gate

Phase 5.5 전환 전에 모두 통과해야 한다.

1. 공식 SDK dependency가 lockfile에서 재현 가능
2. public `tools/list` = exact 13
3. hidden legacy direct call = exact 5
4. input schema semantic parity
5. public contract v1 유지
6. RuntimeSnapshot v2 payload 유지
7. sanitized error parity
8. 실제 SDK STDIO subprocess acceptance PASS
9. CLI / Application Service 기능 보존
10. no order/live Tool
11. `orders_enabled=false`
12. ruff / strict mypy / full pytest PASS

하나라도 실패하면 수동 transport가 canonical entrypoint로 남는다.

## 안전 경계

Phase 5는 transport migration이다. 다음은 범위 밖이다.

- 주문 Tool 추가
- live account Tool 추가
- KIS permission 변경
- hidden legacy hard removal
- StrategyIR 변경
- 평가/금융 계산 변경
- Research loop 정책 변경
- Application Service 재설계

SDK 도입이 어떤 경우에도 `orders_enabled=false`를 완화하는 근거가 되어서는 안 된다.

## Phase 5.1 판정

현재 transport와 migration risk를 인벤토리했고, target을 공식 Python SDK v2
저수준 `mcp.server.Server` + STDIO로 확정했다.

Phase 5.2에서 SDK dependency와 parallel adapter skeleton을 추가했다.\n다음 작업은 **Phase 5.3 — Tool schema / dispatch parity**다.
