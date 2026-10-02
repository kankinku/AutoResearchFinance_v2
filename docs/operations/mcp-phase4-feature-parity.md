# MCP 전환 Phase 4 — 기능 보존 및 안전한 기능 확장

> **역사적 단계 문서:** 이 문서는 당시 전환 단계의 설계·검증 기록이다. 현재 운영 정본은 `mcp-current-state.md`이며, 이 문서의 Tool 수·transport 상태·shadow/canonical 표현을 현재 설정으로 해석하지 않는다.

> **역사적 문서:** 이 문서는 당시 10 → 18 Tool 확장 시점의 설계 기록이다.
> 현재 운영 정본은 Phase 3-6의 **13 public Tool + 5 hidden legacy compatibility name** 구조이며,
> 이 문서의 18 Tool surface로 되돌리지 않는다. 공식 SDK 전환 기준은
> `mcp-phase5-1-sdk-migration-design.md`를 따른다.

## 목적

Phase 4는 Phase 0에서 고정한 CLI 24개 기능과 Dashboard/MCP 기능을 다시 대조하고,
연구 MCP에서 안전하게 제공할 수 있는 기능만 Application Service를 통해 추가한다.

기존 MCP 10개 Tool의 이름과 입력 schema는 변경하지 않는다. Phase 4는 additive 확장이다.

## Phase 4 MCP Tool

기존 10개에 다음 8개를 추가한다.

- `initialize_research_state`
- `get_workspace_status`
- `set_research_mode`
- `validate_research_cache`
- `validate_strategy`
- `import_strategies`
- `list_strategies`
- `plan_generation`

총 MCP Tool 수는 18개다.

## Application Service

Phase 4에서 추가한 서비스:

- `WorkspaceService`
  - 누락된 연구 state 초기화
  - champion/frontier/mode/audit/manifest 상태 요약
  - paper/live 선택 상태 기록
  - manifest 유효성 개수 확인
- `StrategyService`
  - 프로젝트 내부 전략 파일 정적 검증
  - 프로젝트 내부 소스 또는 HTTPS GitHub 전략 저장소 정적 import
  - sanitized strategy catalog 조회
- `PlanningService`
  - 실행 없이 deterministic experiment plan 생성

모든 MCP 추가 기능은 이 Application Service를 통해 호출한다.

## CLI 기능 대응표

| 기존 CLI | MCP 대응 | 정책 |
| --- | --- | --- |
| `init` | `initialize_research_state` | MCP에서는 누락 파일만 생성, 기존 state는 덮어쓰지 않음 |
| `status` | `get_workspace_status` | sanitized 상태 |
| `mode` | `get_workspace_status` | 선택 mode 확인 |
| `set-mode` | `set_research_mode` | paper/live 선택만 변경, `orders_enabled=false` 강제 |
| `research-evidence` | `get_research_evidence` | 기존 Tool |
| `list-features` | `list_features` | 기존 Tool |
| `research-intent` | `submit_research_intent` / `start_system` | 입력 intent 검증 또는 managed autoresearch |
| `dashboard` | `start_system` | managed system이 Dashboard를 함께 시작 |
| `dashboard-status` | `get_dashboard_status` | 기존 Tool |
| `dashboard-refresh` | CLI 유지 | credential-bound 외부 read refresh는 MCP 자동 호출에서 제외 |
| `paper-order-smoke` | 노출하지 않음 | 실제 paper 주문 발생 |
| `import-strategy` | `validate_strategy` | 정적 normalize/검증 |
| `validate-strategy` | `validate_strategy` | 정적 normalize/검증 |
| `import-strategies` | `import_strategies` | 외부 코드 실행 금지, 기본 `dry_run=true` |
| `plan-generation` | `plan_generation` | 순수 local plan |
| `run-generation` | `run_evaluation` | 기존 Tool |
| `repeat-research` | `start_system.repeat_generations` | managed loop |
| `autoresearch` | `start_system` | managed Codex-directed loop |
| `terminal` | 노출하지 않음 | chat/direct-edit는 host interactive trust boundary |
| `resume` | `get_workspace_status` + `get_system_status` | 상태 복구/확인은 Phase 3 lifecycle 사용 |
| `rebuild-cache` | `validate_research_cache` | 기존 CLI 구현의 실제 의미인 manifest 검증을 명확히 표현 |
| `promote-paper` | 노출하지 않음 | deployment 권한 경계 |
| `request-live-approval` | 노출하지 않음 | human-controlled deployment 경계 |
| `audit` | `get_workspace_status.audit_records` | 원문 대신 record count만 제공 |

## 전략 import 안전 경계

`validate_strategy`와 local `import_strategies`의 모든 경로는 `project_root` 내부로 제한한다.

GitHub import는 다음 조건을 유지한다.

- HTTPS
- github.com
- credential이 포함되지 않은 URL
- 제한된 ref 문자열
- private temporary clone
- source code 실행 금지
- AST/YAML/JSON 정적 분석만 수행
- 기본 `dry_run=true`
- 실제 import destination도 `project_root` 내부로 제한

`list_strategies`는 조회 과정에서 디렉터리나 catalog를 새로 만들지 않는 read-only 경로다.

## mode와 주문 권한

`set_research_mode(mode="live")`는 live trading을 활성화하지 않는다.

기록되는 mode state는 항상:

    orders_enabled=false

이다. 따라서 기존 KIS order permission, live gate, human approval 경계는 변경되지 않는다.
실제 주문 Tool, credential Tool, live-account Tool은 MCP에 존재하지 않는다.

## 기존 Tool 호환성

Phase 0의 기존 10개 Tool은 그대로 유지한다.

- `get_research_context`
- `list_features`
- `get_dashboard_status`
- `get_research_evidence`
- `submit_research_intent`
- `run_evaluation`
- `check_system`
- `start_system`
- `get_system_status`
- `stop_system`

contract test는 기존 Tool이 모두 존재하는지와 기존 evaluation/system schema를 계속 검사하며,
Phase 4 Tool은 별도의 additive set으로 검증한다.

## 검증 기준

- 새 Application Service 단위 테스트
- 프로젝트 경로 escape 거부
- unsafe repository URL 거부
- strategy source 미실행 확인
- import 기본 dry-run 확인
- mode 변경 후에도 `orders_enabled=false`
- cache 경로 project-root 제한
- MCP error payload에 거부된 경로/URL 세부정보 미노출
- 실제 STDIO subprocess에서 18개 Tool surface 확인
- 전체 Ruff / strict mypy / pytest release gate
