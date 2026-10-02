# MCP Phase 5.2 — 공식 SDK dependency + parallel adapter skeleton

> **역사적 단계 문서:** 이 문서는 당시 전환 단계의 설계·검증 기록이다. 현재 운영 정본은 `mcp-current-state.md`이며, 이 문서의 Tool 수·transport 상태·shadow/canonical 표현을 현재 설정으로 해석하지 않는다.

## 목적

Phase 5.2는 공식 Python MCP SDK v2를 프로젝트 dependency에 추가하고,
기존 수동 JSON-RPC/STDIO 서버와 분리된 **shadow SDK adapter**를 만든다.

이 단계에서는 public Tool schema나 `tools/call` dispatch를 SDK에 연결하지 않는다.
따라서 production/canonical entrypoint는 계속 다음 경로다.

```text
python -m integrations.codex_mcp_server
  -> integrations.codex_mcp_protocol
  -> current manual STDIO/JSON-RPC transport
```

새 SDK 경로는 별도 shadow entrypoint다.

```text
python -m integrations.codex_mcp_sdk_server
  -> mcp.server.Server
  -> mcp.server.stdio.stdio_server
```

## Dependency

`pyproject.toml`:

```text
mcp>=2.2,<3
```

현재 lockfile resolution:

```text
mcp = 2.2.0
mcp-types = 2.2.0
```

`uv lock --check`로 현재 `requires-python = ">=3.10,<3.13"` 범위에 대한
lockfile 일관성을 확인한다.

SDK dependency가 추가되면서 `httpx2`, `httpcore2`, `cryptography` 등 SDK의
transitive dependencies가 lockfile에 추가된다. 기존 direct `httpx>=0.27` dependency를
제거하거나 교체하지 않는다.

## Shadow adapter

새 모듈:

```text
integrations/codex_mcp_sdk_server.py
```

현재 역할:

- `mcp.server.Server` 생성
- server name = `quant-autoresearch`
- server version = `0.1.0`
- `stdio_server()` transport bootstrap
- 기존 canonical 서버와 별도 CLI entrypoint 제공
- project/state path normalization

현재 상태 marker:

```text
SDK_ADAPTER_STATUS = SHADOW_SKELETON
```

## 의도적으로 아직 없는 기능

Phase 5.2 shadow server는 아직 Tool capability를 광고하지 않는다.

```text
server.create_initialization_options().capabilities.tools = None
```

이는 결함이 아니라 cutover 전 안전 장치다.

다음 기능은 Phase 5.3에서 parity test를 먼저 추가한 뒤 연결한다.

- public 13 Tool schema
- public Tool dispatch
- hidden legacy 5 direct dispatch
- `_contract` metadata
- `_compatibility` metadata
- sanitized `isError=true` Tool result

이 기능들이 모두 검증되기 전에는 shadow SDK entrypoint를 production MCP 설정에 사용하지 않는다.

## Canonical entrypoint 보존

Phase 5.2에서 다음 파일의 transport import는 변경하지 않았다.

```text
integrations/codex_mcp_server.py
  -> integrations.codex_mcp_protocol.serve_lines
```

따라서 기존:

```text
python -m integrations.codex_mcp_server
```

동작은 Phase 5.2 이전과 동일하다.

`integrations.codex_mcp_sdk_server`는 병렬 migration seam일 뿐이다.

## 테스트 계약

`tests/integrations/test_codex_mcp_sdk_server.py`는 다음을 검증한다.

1. `pyproject.toml`에 `mcp>=2.2,<3`가 존재
2. 실제 installed SDK가 2.2 이상 3 미만
3. shadow adapter 생성 가능
4. server identity = `quant-autoresearch / 0.1.0`
5. Phase 5.2에서 tools capability가 아직 비활성
6. shadow CLI가 독립적으로 import/startup 가능한 상태
7. 기존 manual CLI entrypoint가 계속 존재

## 안전 경계

Phase 5.2에서 변경하지 않는 항목:

- advertised public MCP surface = 13
- hidden legacy compatibility = 5
- public response contract = v1
- RuntimeSnapshot = v2
- Application Service
- StrategyIR
- evaluation / finance logic
- KIS permission
- live account gate
- Docker execution
- order capability

`orders_enabled=false` 계약도 그대로 유지한다.

## Rollback

아직 canonical cutover가 없으므로 rollback은 단순하다.

1. `integrations/codex_mcp_sdk_server.py` 제거
2. `mcp>=2.2,<3` dependency 제거
3. lockfile 재생성

기존 `integrations/codex_mcp_server.py`와 `codex_mcp_protocol.py`는 Phase 5.2에서
변경하지 않았으므로 기존 MCP 실행 경로로 별도 복구 작업 없이 돌아갈 수 있다.

## Phase 5.2 판정

완료 조건:

```text
official SDK dependency = LOCKED
shadow SDK adapter = AVAILABLE
canonical manual adapter = UNCHANGED
SDK tool parity = NOT_YET_ENABLED
orders_enabled=false
```

Phase 5.3에서 Tool schema / dispatch parity를 완료했다. 현재 상태는
`docs/operations/mcp-phase5-3-tool-dispatch-parity.md`를 따른다.
