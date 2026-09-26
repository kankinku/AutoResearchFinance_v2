# MCP 전환 Phase 0 기준선

## 목적

이 문서는 AutoResearchFinance_v2를 MCP 기반 시스템으로 확장하기 전에 보존해야 할 현재 외부 동작을 고정한다. Phase 0은 회귀 기준선과 검증 인프라만 추가하며 프로덕션 로직, 금융 계산, 연구 파이프라인, MCP 실행 로직은 변경하지 않는다.

## Git 기준선

- 기준 브랜치: `master`
- 기준 SHA: `5875af8aff375dfcfe6548b5a06eae9ae02cf08f`
- 구현 브랜치: `feat/mcp-phase0-baseline`

향후 Phase에서 서비스 계층 추출이나 MCP SDK 전환을 수행하더라도 아래 계약은 명시적 마이그레이션 결정 없이 사라져서는 안 된다.

## 보존 계약

### CLI

현재 공개 CLI 서브커맨드는 24개다.

`init`, `status`, `mode`, `set-mode`, `research-evidence`, `list-features`,
`research-intent`, `dashboard`, `dashboard-status`, `dashboard-refresh`,
`paper-order-smoke`, `import-strategy`, `validate-strategy`, `import-strategies`,
`plan-generation`, `run-generation`, `repeat-research`, `autoresearch`, `terminal`,
`resume`, `rebuild-cache`, `promote-paper`, `request-live-approval`, `audit`.

### MCP

기존 MCP Tool은 다음 10개다.

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

현재 MCP는 주문 또는 credential Tool을 노출하지 않는다. 이후 정식 MCP SDK로 전환할 때도 기존 Tool은 호환 계층을 유지하거나 명시적 버전 마이그레이션을 제공한다.

### Dashboard HTTP

사용자-facing 경로는 다음과 같다.

- `GET /`
- `GET /backtest`
- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/features/catalog`
- `GET /api/strategies/catalog`
- `GET /api/research-evidence`
- `GET /api/backtest`
- `GET /api/backtest/runs/{run_id}`
- `POST /api/refresh`

### Strategy IR / Research

`StrategyIR`의 현재 필드 이름, `strategy_id -> id` alias, 필수/선택 필드 구분과 `CANONICAL_STAGES` 20단계 이름을 regression contract로 고정한다.

## 자동 검증

`tests/contracts/test_phase0_public_contracts.py`에서 위 외부 표면을 직접 검증한다.

또한 `moon.config.json`에 검증 프로필을 추가한다.

- `fast`: Ruff
- `normal`: Ruff + strict mypy + 계약/MCP/Dashboard 집중 테스트
- `release`: Ruff + strict mypy + 전체 pytest

현재 코드가 런타임에서 `pyarrow`를 사용하지만 아직 `pyproject.toml` 직접 의존성에는 포함하지 않았기 때문에 Phase 0 검증 명령은 `uv --with pyarrow`를 사용한다. 실제 의존성 선언 정리는 후속 Phase에서 별도 변경한다. 검증 환경을 재현할 수 있도록 이 시점의 `uv.lock`도 기준선에 포함한다.

패키징 과정에서 생성될 수 있는 `build/`는 생성 산출물이므로 Git 추적 대상에서 제외한다.

## 플랫폼 테스트 기준선

기존 기준선에서 Linux 실행 시 실패하던 다음 테스트가 있었다.

`tests/research/test_codex_exec.py::test_codex_subprocess_timeout_kills_the_spawned_process_tree`

원인은 Linux Python 런타임에서 테스트가 `sys.platform`만 `win32`로 바꾸면서 `shutil.which()`가 Windows 전용 `_winapi`를 호출한 것이었다. Phase 0에서는 프로덕션 코드가 아니라 테스트에서 executable resolution만 모킹하여, 원래 의도인 Windows `taskkill /T /F` 호출 검증을 플랫폼 독립적으로 유지한다.

## Phase 0 검증 결과

2026-09-26 Moon 작업 환경에서 다음 검증을 통과했다.

- Ruff: 전체 통과
- strict mypy: 136개 소스 파일, 오류 0
- pytest: 578 passed
- 비차단 경고: FastAPI/Starlette TestClient의 httpx deprecation warning 1건
- 프로덕션 Python 모듈 변경: 없음

## 완료 조건

Phase 0은 다음 조건을 모두 만족해야 한다.

1. 새 공개 계약 테스트가 통과한다.
2. Ruff와 strict mypy가 통과한다.
3. 전체 pytest가 추가 실패 없이 통과한다.
4. 변경 파일이 테스트, 문서, Moon 검증 설정, Git ignore 규칙에 한정된다.
5. `core/`, `evaluation/`, `orchestration/`, `runtime/`, `integrations/`, `research/`의 프로덕션 로직에는 변경이 없다.
