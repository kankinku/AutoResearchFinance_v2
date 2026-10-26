# Python MCP 개선 포크 — D1/D2 구현 및 검증 보고서

- 날짜: **2026-10-25 KST**
- 기준: `docs/architecture/python-mcp-predevelopment-source-map-v1-20261025.md`; 원래 Q02/Q06/Q08/Q09/Q11/Q15/Q17/Q20; 기존 **V05→T4→V01~V04→V06→V07** 단계·인증/실주문/OOS 경계 변경 없음
- 작업 ID: **T4-PY-MCP-D1D2-01**
- 결론: **D1 독립 Python 실행환경 구축 및 읽기 전용 D2 ChatGPT/Codex MCP 계약 선택 검증 PASS. 학술 계획/진단 제출 및 인증된 GPT 무인 세대는 아직 NOT IMPLEMENTED.**

## D1 — 진짜 별도 Python 환경

코드 경로: `/shared/moon-workspace/AutoResearchFinance_PythonMCP`.

1. 새 포크 내부 `.venv/`를 Python 3.12의 `python3 -m venv --copies .venv`로 생성함. Git에서는 이미 무시됨.
2. 전체 `pip install -e '.[dev]'`는 저장소/호스트 파일 쓰기 시간이 길어 설정한 실행 제한에서 두 번 중단. 이 두 시도는 **실패/부분 설치**로 표시하고 PASS로 미화하지 않음.
3. 로컬에 설치된 패키지 목록과 pip의 누락 진단을 토대로 같은 **새 .venv 내부에서만** 분할 설치 진행: `mcp`, `httpx`, `jsonschema`, `fastapi`, `anyio`, `httpcore`, `httpcore2`, `jsonschema-specifications`, `httpx2`, `mcp-types`, `sse-starlette`, `starlette`, `cryptography`, `streamlit`, `altair`, `pydeck`, `jinja2` 및 원본 2회 명령에서 이전에 정상 설치된 의존성, 마지막 `quant-autoresearch` editable 설치.
4. **새 포크 `.venv/bin/python -m pip check` → No broken requirements found.** 이 검증은 현재 설치된 버전의 의존성 일관성 검증이다. `uv.lock`과 완전히 같은 빌드라는 주장이나 다른 운영체제에서 동일하게 재현된다는 주장은 아님. `pyproject.toml` 기본 `mcp>=2.2,<3` 조건 유지.
5. 모든 임시 설치·테스트 로그는 `/state/python-mcp-*.log` 로컬 gitignore. 기존 연구 Python 가상환경은 설치 대상도 수정 대상도 아님.

독립 환경 검증 명령:
```bash
cd /shared/moon-workspace/AutoResearchFinance_PythonMCP
.venv/bin/python -m pip check
PYTHONPATH=. .venv/bin/python scripts/python_mcp_probe.py --surface codex
PYTHONPATH=. .venv/bin/python scripts/python_mcp_probe.py --surface chatgpt_academic
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/integrations/test_python_mcp_direct.py \
  tests/integrations/test_python_mcp_surface_parity.py \
  tests/governance/test_autoresearch_scope_lock.py
```

## D2 — 기존 서버 재사용 (새 MCP 서버 구현 금지)

이전 공개 도구 불일치:
- `integrations.codex_mcp_server`: **13개** 공식 Codex MCP 도구.
- `integrations.chatgpt_mcp_stdio`: **32개** 기존 ChatGPT Quant MCP 도구, 그중 Academic `get_algorithm_research` 및 `submit_algorithm_plan` 등 이미 포함.
- `application/academic_checkpoint_service.py`의 `require_trade_activity=True`: 실제 서비스는 옵션을 이해하지만 `integrations/chatgpt_mcp_sdk.py::chatgpt_tools` 공개 plan 제출 schema에서 빠져 있었음.

이번 fork-only 수정:
1. `integrations/python_mcp_direct.py::QuantMCPSettings.surface`: 기본 `codex` 13개 vs 명시 `chatgpt_academic` 32개; 같은 fork-local Quant child를 다른 기존 공식 STDIO 엔트리포인트로 실행. **기본 Moon 또는 기존 Quant 원격 OAuth/MCP URL 설정 불변**.
2. `scripts/python_mcp_probe.py --surface {codex,chatgpt_academic}`: 격리된 동일 CLI로 두 공개 계약 실측.
3. `QuantMCPDirectClient.require_read_only_tool`: `get_algorithm_research`는 **ChatGPT Academic 표면 + 정확한 세션 ID가 모두 있을 때만** 허용. Codex 도구 허용목록에 이름만 추가해 우회하는 버그 제거.
4. `QuantMCPDirectClient.read_academic_checkpoint`: 정확한 세션 확인 후 **읽기만 실행**, 주문 OFF·봉인 OOS·해시/세대 수 안전 체크, 존재하지 않는 세션의 안전 거절. SDK가 반환하는 중첩 예외는 **동일 MCP 오류만 좁혀 정규화**, 다른 시스템 예외는 다시 전파.
5. `integrations/chatgpt_mcp_sdk.py`의 `submit_algorithm_plan` 공개 도구 입력 schema에 `require_trade_activity: boolean default false` 선택 인자 추가. 기존 필수 세션/토큰/plan, 운영 기본값, 백테스트/사용자 20문답 변경 없음.
6. `tests/integrations/test_python_mcp_surface_parity.py` 및 기존 `test_python_mcp_direct.py` 수정: 실제 공식 SDK STDIO subprocess를 사용해 도구 개수/단위/정확한 scope/잘못된 session 조회/기존 token 보존에 관한 테스트 추가.

## 실측 결과

두 CLI (새 `.venv`) 모두 종료코드 **0**:

| 표면 | 실제 발견 도구 | 실제 등록 지표 | 포크 상태 | GPT 호출 | 주문 |
|---|---:|---:|---|---:|---|
| `codex` | **13개** | **173개** | NOT_INITIALIZED | 0 | OFF |
| `chatgpt_academic` | **32개** | **173개** | NOT_INITIALIZED | 0 | OFF |

여기서 GPT 0회는 **CLI가 GPT API를 호출하지 않았음**을 뜻하며 별도의 제공자 사용량 영수증이 아님. 새 포크의 진짜 연구 세대도 **0**이고, 원본 P5 28/100세대 증거는 옮기지 않았다.

**독립 가상환경에서** 거버넌스 + 신규 실제 STDIO/계약 테스트 **18 PASS**. 기존 연구 환경에서도 동일 범위 **18 PASS**. 관련 공개 MCP SDK/오래된 서버 parity 회귀는 별도 검증 결과를 기록. Ruff 저장소 전수 및 선택적 mypy, 전체 pytest 등 실제 수행 여부만 표시한다.

## 해결된 중복과 아직 남은 경계

- **해결:** Codex용 학술 서버/32도구를 새로 만들 필요 없음. 기존 ChatGPT STDIO 공식 서버 재사용, 도구 schema와 Python 클라이언트의 정확한 역할 선택이 이득.
- **해결:** `require_trade_activity`의 서비스 vs 공개 schema 불일치 (fork-only).
- **해결:** 원본 다른 가상환경을 실제 서비스 runtime으로 쓰는 불완전한 격리. 새 포크 자체 `.venv`에서 기능 확인.
- **미구현:** `submit_algorithm_plan`·`submit_algorithm_diagnosis` 등의 쓰기/승인/증거 provenance 경로, 실제 GPT 모델 세대 계수. 현재 `QuantMCPDirectClient`는 **읽기 전용**. ChatGPT MCP child가 32개 도구를 목록으로 노출한다는 사실 자체는 OS권한/서버 자체 보안 격리를 뜻하지 않음. 신뢰할 수 없는 모델에게 이 상태로 child raw session을 제공 금지.
- **미구현:** Codex Python SDK 모델 호출/로그인·사용량·독립 P4-2 공급자 서명. 별도 과금/재인증 자동 진행 금지.
- **미검증:** 실제로 시작한 새로운 연구 session의 성공적 읽기와 resume, 실제 GPT 1·3세대의 complete evidence hash. 없는 세션 조회의 비변경 안전 거절만 테스트.
- **변경 불가:** 기본 Moon MCP 38개 도구/원본 Quant MCP 32개/원본 P5 state/OAuth/기존 대시보드 URL, 실거래 기능 OFF, OOS 봉인, 원래 사용자 20문답·기존 연구 순서.

## 다음 결정 단계

**D3**는 이 포크에서 실제 사용자 승인된 GPT 모델 호스트를 얻기 전까지 **모델 없는 쓰기/계수 자동화로 둔갑하지 않도록** 해야 한다. 첫 번째로 fork-local **사용자 승인된** 테스트 세션 1개를 생성하고, 기존 `AcademicMCPCheckpointService` 계획/진단 계약을 명시적으로 검증한 후에만 허용된 기록 경로를 추가한다. 실제 GPT 출처 검증과 checkpoint replay, STOP/quota 처리의 안정성을 확보한 뒤 GPT 1→3→100 세대 연구로 확대. 먼저 10/100의 기존 T4 수락 기준과 봉인 검증 순서는 유지한다.
