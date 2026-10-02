# MCP Phase 5.5 — Canonical SDK Cutover

> **역사적 단계 문서:** 이 문서는 당시 전환 단계의 설계·검증 기록이다. 현재 운영 정본은 `mcp-current-state.md`이며, 이 문서의 Tool 수·transport 상태·shadow/canonical 표현을 현재 설정으로 해석하지 않는다.

## 목적

Phase 5.5는 `python -m integrations.codex_mcp_server`의 production STDIO transport를
공식 Python MCP SDK로 전환하는 단계다.

Phase 5.1~5.4에서 schema/dispatch parity와 실제 subprocess acceptance를 먼저 확보했기
때문에 이번 단계에서는 business/application logic을 다시 작성하지 않고 transport ownership만
전환한다.

## 최종 모듈 구조

현재 구조:

```text
integrations/codex_mcp_core.py
  ├─ CodexMCPServer dispatch/application adapter
  ├─ 13 public + 5 compatibility tool definitions
  ├─ public _contract / legacy _compatibility
  └─ legacy handle() compatibility path

integrations/codex_mcp_sdk_server.py
  ├─ official mcp.server.Server
  ├─ official stdio_server()
  ├─ SDK Tool model conversion
  └─ shared codex_mcp_core dispatch

integrations/codex_mcp_server.py
  ├─ compatibility Python imports re-export
  └─ canonical CLI -> official SDK adapter

integrations/codex_mcp_manual_server.py
  └─ emergency rollback -> codex_mcp_protocol.serve_lines

integrations/codex_mcp_protocol.py
  └─ legacy newline JSON-RPC helpers retained for rollback only
```

## Canonical entrypoint

Production/trusted MCP 설정은 계속 같은 command를 사용한다.

```text
python -m integrations.codex_mcp_server --state-dir state --project-root .
```

명령 문자열은 바뀌지 않았지만 내부 transport는 이제 공식 SDK다.

module marker:

```text
MCP_TRANSPORT = official_sdk
SDK_ADAPTER_STATUS = CANONICAL_SDK
```

따라서 기존 Codex Desktop 설정은 command 변경 없이 SDK transport로 전환된다.

## Python import compatibility

기존 테스트/내부 코드가 다음 이름을 계속 import할 수 있도록
`integrations.codex_mcp_server`는 compatibility façade 역할을 유지한다.

- `CodexMCPServer`
- `create_mcp_server`
- `_all_tools`
- `_tools`
- `_PUBLIC_TOOL_PLANES`
- `_TARGET_PUBLIC_TOOL_NAMES`
- `_with_public_contract`
- `_with_legacy_compatibility`
- system schema/config helpers

실제 정의는 `codex_mcp_core.py`에 있다.

이 때문에 transport cutover가 기존 application-level unit test나 import consumer를 깨뜨리지 않는다.

## Manual rollback

비상시 수동 transport는 다음 명령으로 명시적으로 실행할 수 있다.

```text
python -m integrations.codex_mcp_manual_server --state-dir state --project-root .
```

marker:

```text
MCP_TRANSPORT = manual_rollback
protocol = 2024-11-05
```

rollback transport는 production default가 아니다.

다음 상황에서만 사용한다.

- official SDK bootstrap regression 확인
- SDK dependency/runtime 문제 격리
- 이전 2024 transport와 behavior 비교

rollback도 동일한 application dispatch와 13 public + 5 hidden compatibility surface를 사용하므로
연구/평가 business logic은 갈라지지 않는다.

## Release gate

Canonical SDK acceptance:

```powershell
uv run --locked --extra dev python scripts/verify_mcp_sdk_runtime.py `
  --project-root . `
  --state-dir state/mcp-sdk-cutover-acceptance
```

실제 Phase 5.5 결과:

```json
{
  "canonical_entrypoint": "sdk",
  "legacy_compatibility_count": 5,
  "legacy_protocol_version": "2024-11-05",
  "orders_enabled": false,
  "public_contract_schema_version": 1,
  "sdk_protocol_version": "2025-11-25",
  "server_name": "quant-autoresearch",
  "status": "PASS",
  "system_status": "STOPPED",
  "tool_count": 13
}
```

Manual rollback acceptance:

```powershell
uv run --locked --extra dev python scripts/verify_mcp_runtime.py `
  --project-root . `
  --state-dir state/mcp-manual-rollback-acceptance
```

실제 결과:

```json
{
  "legacy_compatibility_count": 5,
  "orders_enabled": false,
  "protocol_version": "2024-11-05",
  "public_contract_schema_version": 1,
  "server_name": "quant-autoresearch",
  "status": "PASS",
  "system_status": "STOPPED",
  "tool_count": 13,
  "transport": "manual_rollback"
}
```

두 process 모두 exit code 0이며 stderr는 비어 있었다.

전체 repository release gate:

```text
ruff = PASS
mypy = PASS (163 source files)
pytest = PASS (769 tests)
```

## Cutover regression

`tests/integrations/test_codex_mcp_cutover.py`는 실제 subprocess에서 다음을 검증한다.

1. canonical module이 SDK handshake `2025-11-25`를 협상
2. manual rollback module은 `2024-11-05` 유지
3. server identity 유지
4. canonical Tool capability 존재
5. 기존 Python import contract 유지

기존 Phase 5.3/5.4 tests도 계속 유지한다.

## Trusted Codex 설정

`.codex/config.toml.example`의 canonical command는 그대로다.

```toml
[mcp_servers.quant_autoresearch]
command = "uv"
args = ["run", "--locked", "python", "-m", "integrations.codex_mcp_server", "--state-dir", "state", "--project-root", "."]
```

이 command는 이제 공식 SDK transport를 사용한다.

manual rollback으로 전환하려면 module 이름을
`integrations.codex_mcp_manual_server`로 명시적으로 바꿔야 한다.

## 안전 경계

Phase 5.5에서 변경하지 않은 항목:

- public Tool = 13
- hidden compatibility = 5
- public contract = v1
- RuntimeSnapshot = v2
- Application Services
- StrategyIR
- evaluation / finance logic
- Docker execution backend
- KIS credential handling
- live account gate
- sealed OOS policy
- order permission

공식 SDK cutover는 권한 확대가 아니다.

```text
orders_enabled=false
```

를 계속 유지한다.

## Rollback 방법

SDK transport regression이 확인되면 Git rollback 없이도 trusted MCP command의 module만
임시 변경할 수 있다.

```text
integrations.codex_mcp_server
        ↓
integrations.codex_mcp_manual_server
```

문제 해결 후 canonical module로 되돌린다.

`codex_mcp_protocol.py` 삭제는 이번 Phase 범위가 아니다. rollback window가 끝난 뒤
별도 승인으로 제거 여부를 결정한다.

## Phase 5.5 판정

```text
canonical transport = OFFICIAL_SDK
canonical sdk acceptance = PASS
manual rollback transport = AVAILABLE
manual rollback acceptance = PASS
public tools = 13
hidden compatibility = 5
public contract = v1
orders_enabled=false
```

이로써 **Phase 5 공식 MCP SDK 전환 개발 범위는 완료**다.
