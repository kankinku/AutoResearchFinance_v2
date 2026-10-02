# MCP 전환 Phase 1 — Application Service 계층

## 목적

Phase 1은 CLI, 기존 MCP 서버, Dashboard/read model이 각자 핵심 유스케이스를 직접 조합하던 구조를 공통 Application Service 계층으로 정리한다. 금융 계산식, 연구 알고리즘, KIS 권한, MCP transport는 변경하지 않는다.

## 추가된 계층

`application/` 아래에 다음 서비스가 추가된다.

- `FeatureCatalogService`: 연구용 feature projection
- `ResearchService`: sanitized research context, research evidence, validated ResearchIntent persistence
- `EvaluationService`: 기존 `run_local_evaluation`의 application entry point
- `SystemService`: 기존 `SystemController`의 preflight/start/status/stop entry point
- `ApplicationServices`: 동일 state/project context를 공유하는 composition root

## 호출 구조

기존:

`CLI/MCP -> core/runtime/orchestration functions`

Phase 1 이후:

`CLI/MCP -> application services -> existing core/runtime/orchestration functions`

Dashboard HTTP는 기존 `DashboardService`를 유지한다. `ApplicationServices`도 동일 DashboardService 인스턴스를 ResearchService와 공유하므로 read model을 중복 생성하지 않는다.

## 기능 보존

기존 MCP Tool 10개 이름과 JSON schema는 변경하지 않는다. 기존 CLI 24개 서브커맨드도 변경하지 않는다.

공통 서비스로 전환하는 CLI 경로는 다음과 같다.

- `research-evidence`
- `list-features`
- `research-intent`의 validated intent 기록
- `run-generation`

MCP는 research context, feature catalog, evidence, intent persistence, evaluation, system control을 모두 ApplicationServices를 통해 호출한다.

## 후속 Phase와의 관계

Phase 2에서 금융 평가 로직을 수정하면 `EvaluationService` 아래 구현 한 곳만 변경하면 된다. Phase 3에서 ResearchIntent와 worker queue를 연결할 때도 `ResearchService/SystemService` 경계 안에서 변경할 수 있다. Phase 5의 공식 MCP SDK 전환은 application 계층을 그대로 호출하므로 transport 교체가 연구 엔진 변경과 분리된다.
