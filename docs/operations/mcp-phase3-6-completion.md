# MCP Phase 3-6 — 운영 Tool surface 정리 완료

> **역사적 단계 문서:** 이 문서는 해당 Phase의 완료/설계 스냅샷이다. 현재 운영 정본은 `mcp-current-state.md`이며, 실행 방법과 현재 구조는 정본 문서를 우선한다.

## 완료 범위

Phase 3-6은 다음 세부 단계로 완료한다.

- 3-6.1 현재 MCP Tool 전수 분류
- 3-6.2 최종 Public MCP Surface 목표안 설계
- 3-6.3 submit_research_intent soft deprecation
- 3-6.4 public tools/list 13개 전환
- 3-6.5 workspace bootstrap/configuration contract
- 3-6.6 public response contract v1
- 3-6.7 compatibility/security/stdio acceptance

## 최종 공개 MCP surface

tools/list는 정확히 13개를 광고한다.

### Bootstrap / configuration

- initialize_research_state
- get_workspace_status

### Catalog / validation

- validate_strategy
- import_strategies
- list_strategies
- list_features

### Evidence / status

- get_research_evidence
- get_dashboard_status
- get_system_status

### Execution / lifecycle

- run_evaluation
- check_system
- start_system
- stop_system

## Status plane 구분

세 상태 계층은 서로 합치지 않는다.

- get_workspace_status = bootstrap/configuration
- get_system_status = managed runtime/control plane
- get_dashboard_status = research/performance data plane

get_workspace_status는 WorkspaceStatusSnapshot schema version 1을 사용하고
NOT_INITIALIZED / PARTIAL / READY를 구분한다.

get_system_status는 RuntimeSnapshot schema version 2를 유지한다.

## Public response contract

13개 공개 Tool의 성공 MCP 응답에는 기존 payload를 그대로 유지하면서
additive _contract metadata가 붙는다.

- schema_version = 1
- tool = 호출 Tool 이름
- plane = 네 public plane 중 하나
- orders_enabled = false

Application Service와 CLI payload에는 이 MCP adapter metadata를 강제하지 않는다.

## Legacy compatibility

다음 5개 이름은 tools/list에서 광고하지 않는다.

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

Phase 3-6.7 완료 시점에도 기존 caller migration을 위해 direct tools/call dispatch는
호환성 shim으로 남아 있다.

네 internalized Tool은 LEGACY_INTERNAL_TOOL metadata를 반환한다.

submit_research_intent는 DEPRECATED metadata를 반환하며 외부 intent를 실행하는
production consumer를 새로 만들지 않았다.

Hidden dispatch는 security boundary가 아니다. Hard dispatch removal은 Phase 3-6 범위 밖이며
별도 승인 없이는 수행하지 않는다.

## CLI / Application Service 보존

MCP public surface에서 숨긴 저수준 기능은 필요한 운영 경로를 보존한다.

CLI:

- set-mode
- rebuild-cache
- plan-generation
- research-intent

Application Service:

- WorkspaceService.set_mode
- WorkspaceService.validate_cache
- PlanningService.plan_generation
- ResearchService.context
- ResearchService.validate_and_record_intent

따라서 MCP UX를 단순화하면서 로컬 운영/진단 기능을 삭제하지 않았다.

## Real STDIO acceptance

scripts/verify_mcp_runtime.py는 실제 별도 Python subprocess로 MCP STDIO server를 실행한다.

검증 순서:

1. initialize
2. tools/list exact 13
3. get_system_status public response contract v1
4. set_research_mode legacy direct call
5. validate_research_cache legacy direct call
6. plan_generation legacy direct call
7. get_research_context legacy direct call
8. submit_research_intent deprecated direct call

acceptance에서는 평가 실행, managed research start, KIS 주문을 실행하지 않는다.

정상 요약은 다음 의미를 가져야 한다.

- status = PASS
- protocol_version = 2024-11-05
- server_name = quant-autoresearch
- tool_count = 13
- public_contract_schema_version = 1
- legacy_compatibility_count = 5
- system_status = STOPPED 또는 유효한 system status
- orders_enabled = false

## 안전 경계

Phase 3-6은 다음을 변경하지 않았다.

- MCP 주문 Tool 없음
- MCP live-account Tool 없음
- orders_enabled=false
- KIS permission boundary
- paper-order-smoke의 명시적 별도 승인 구조
- strategy import static-only 실행 경계
- sealed OOS promotion 경계
- RuntimeSnapshot의 민감정보 sanitization
- lifecycle ownership/recovery 정책

set_research_mode legacy direct call에서 live를 선택해도 orders_enabled는 false이며,
SystemController의 paper research preflight를 우회하지 않는다.

## 문서 정합성

현재 운영 문서는 public MCP 13개와 실제 managed orchestration 구조를 기준으로 갱신했다.

README는 더 이상 get_research_context나 set_research_mode를 public first-class Tool로
안내하지 않는다.

system-orchestrator 문서는 STDIO acceptance가 public surface와 legacy compatibility를
함께 검증한다는 점을 반영한다.

이전 phase 문서에 기록된 10개/18개 Tool 수는 해당 시점의 역사적 기준선이며,
현재 정본은 이 문서와 mcp-phase3-6-2-target-surface.json이다.

## 완료 판정

Phase 3-6의 목적이었던 MCP 운영 surface 정리는 완료로 판정한다.

최종 상태:

- advertised public surface = 13
- hidden legacy compatibility names = 5
- public response contract = v1
- workspace contract = v1
- runtime snapshot = v2
- CLI/Application Service maintenance paths preserved
- no MCP order/live capability
- real stdio subprocess acceptance available

다음 단계는 Phase 3-7 — 실제 Docker Host Acceptance다.

Phase 3-7에서는 MCP Tool surface를 다시 정리하지 않고,
Windows + Docker Desktop host에서 실제 docker_worker 경로를 검증한다.
