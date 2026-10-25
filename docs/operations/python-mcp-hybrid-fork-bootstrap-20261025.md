# Python MCP Hybrid Quant — 독립 포크 부트스트랩

2026-10-25 KST / 작업 ID `T4-PY-MCP-FORK-01`.

## 저장소와 역할 분리

| 구성 요소 | 역할 | 여기서 변경 여부 |
|---|---|---|
| **Moon** (기존 MCP 플러그인/서버) | 원격 작업·파일·프로세스·Git | **변경 없음** |
| **기존 Quant AutoResearch** `kankinku/AutoResearchFinance_v2` | 원래 연구 엔진·실제 P5 원장 | **변경 없음** |
| **독립 Quant 실험 포크** `kankinku/AutoResearchFinance_PythonMCP` | Python→Quant MCP 직접 호출·추후 GPT 실행자의 연결 계층 | **이 저장소에서만 개발** |
| **GPT/Codex** | 연구 가설과 판단 작성 | 아직 신규 자동 호출/로그인 **없음** |

동일 소유자의 GitHub 저장소는 자기 자신을 GitHub 네이티브 Fork 관계로 생성할 수 없으므로, 원본 프로젝트의 Git 커밋 이력을 **독립 복사한 Git 기반 포크**다. `upstream=https://github.com/kankinku/AutoResearchFinance_v2.git`는 변경 확인용, `origin=https://github.com/kankinku/AutoResearchFinance_PythonMCP.git`만 쓰기 대상으로 한다.

**GitHub:** https://github.com/kankinku/AutoResearchFinance_PythonMCP (초기 private).

**Moon 코드 작업공간:** `/shared/moon-workspace/AutoResearchFinance_PythonMCP`.

**새 포크의 런타임 상태:** `<새 포크>/state/python-mcp/` (Git ignored). 기존 P5의 `/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024`를 이 클라이언트에 전달하면 경로 격리 정책이 거절한다.

## 실제 동작하는 P0 — GPT 없는 Python STDIO→Quant MCP

- `integrations/python_mcp_direct.py`: 공식 `mcp` Python SDK의 `ClientSession`, `stdio_client`로 **이 포크 코드** `integrations.codex_mcp_server`를 하위 프로세스로 실행한다.
- 외부 Moon 플러그인을 재등록하거나 원본 Quant의 OAuth/URL을 변경하지 않는다. Moon은 단지 Python 프로그램을 실행해주는 **호스트 환경**이다.
- `get_workspace_status`, `list_features`, 범위를 일치시킨 경우의 `get_algorithm_research` 등 읽기전용 도구만 허용한다. 백테스트 실행·모델 판단·연구 세대 제출·데이터 다운로드·실거래는 **아직 없음**.
- `state_dir`은 반드시 지정된 새 프로젝트 안의 `state/` 이하, 세션 ID는 정확한 32자리 소문자 hex일 때만 허용. 부모/P3/P4/S7 scope는 정확한 지정 세션에만 바인딩한다. 임의 OAuth/API 키/외부 연구 환경변수는 하위 프로세스에 전달하지 않는다.
- 서버가 주문 비활성 상태를 반환하지 않으면 상태 조회 실패. 요청한 MCP 변경 도구는 Python 측에서 거절한다. **서버 전반의 권한 체계를 대체하는 보안 경계라고 과장하지 않는다**.

### 실행

이 실행용 검증은 기존에 준비된 연구용 Python 환경의 MCP 라이브러리를 일시 활용한다. 코드·원장·하위 프로세스의 project-root/state는 새 포크로 독립되어 있지만 **가상환경은 아직 완전 독립 설치가 아니다**.

```bash
cd /shared/moon-workspace/AutoResearchFinance_PythonMCP
PYTHONPATH=. /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/.venv/bin/python scripts/python_mcp_probe.py
```

예상 필드: `transport:stdio`, `model_calls:0`, `orders_enabled:false`, `mcp_tool_count`, `quant_status`, `feature_count`, `research_session:UNSET_READ_ONLY`. 새 상태는 아직 연구를 시작하지 않아 `NOT_INITIALIZED`도 정상이다.

### 테스트

```bash
PYTHONPATH=. <검증 Python> -m pytest -q tests/integrations/test_python_mcp_direct.py
PYTHONPATH=. <검증 Python> -m pytest -q tests/governance/test_autoresearch_scope_lock.py
<검증 Python> -m ruff check integrations/python_mcp_direct.py scripts/python_mcp_probe.py tests/integrations/test_python_mcp_direct.py
```

격리 경로·다른 프로젝트 P5 경로 거절, 잘못된 세션 토큰 거절, 변경 도구 로컬 거절, 실제 MCP STDIO 상태+지표 조회를 테스트한다. 테스트 완료는 **GPT 연구 자동화** 성공이나 최종 수익성 증명을 의미하지 않는다.

## 다음 단계: GPT 판단 + Python 자동 실행의 완성

1. **P1:** 포크 전용 가상환경 재현 설치, 환경 의존성을 새 저장소에서 독립 고정. 파일·상태·세션·자격증명 접근 범위 검증.
2. **P2:** 이미 확인된 실제 GPT 응답을 입력으로 받는 타입드 연구 계획/진단 인터페이스, 비용후 백테스트/S7/원장 및 무거래·지표단위 게이트까지 명시적으로 체크하는 모델-비종속 Python 실행 드라이버를 추가. 미검증 자동 모델 콜백은 세대 계수 금지.
3. **P3:** 사용자 승인된 Codex 모델 호스트 인증 가능 여부 확인. 실제 모델 호출 식별자·입력/출력 해시·과금/쿼터·중단 재개·독립적인 공급자 검증 범위를 분리. 기존 인증/기본 플러그인은 무단 변경하지 않음.
4. **P4:** **새 포크의 독립 실험 원장**에서 실제 GPT 1세대→3세대→100세대 경로를 실행 검증. **원본 P5 G28을 새 1세대로 둔갑하거나, 데이터를 직접 복사·수정하지 않는다**. 원본 P5 28/100은 명시적 이관 승인 전 그대로 존치.

기존 합의 Q02/Q06/Q08/Q09/Q11/Q15/Q17/Q20 및 V05→T4→V01~04→V06→V07 목표·순서를 유지한다. 실주문과 OOS 봉인은 계속 비활성. 새로운 독립 모델 인증/요금은 승인받기 전 사용하지 않는다.
