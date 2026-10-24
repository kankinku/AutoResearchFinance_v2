# Quant AutoResearch — 기존 대시보드 API/연결 복구 (2026-10-24 KST)

## 요구·승인 범위
- T4 운영 지원 작업, 원본 인터뷰 **Q09/Q15/Q16/Q17/Q20** (실제 성과·연구 진행 확인 및 기존 원장 보존). 사용자 요청: "대시보드 문제 해결".
- 기존 GUI, 기본 지표, GPT/MCP 고정 OAuth/URL, G452·G552 보존 원장, T4 연구 세션 및 봉인 OOS·주문 금지 유지. 새 대시보드 제품·URL/모델 교체, 실거래, 성과 평가 규칙 변경 없음.
- 원래 범위 순서 V05 → T4 → V01~V04 → V06 → V07 불변. 독립 연구 엔진 자동화/알파 검증이 완료됐다는 주장 없음.

## 재현: 증상, 분리 진단, 원인
1. localhost `127.0.0.1:8081/`·`8082/` HTML은 각각 **200**였지만, `/api/status`, `/api/dashboard`, `/health` 요청에 **curl 52 / HTTP 000 / Empty reply from server**가 발생. 프런트엔드는 자동 폴링하지만 JSON을 받지 못해 정보가 비어 보임.
2. 운영 세션 `14626d55fb2b461faa485df911920071`, **68/100세대**, `proof_chain_ok=true`, 적격 최고 **G64**, 원장 DB는 정상. **G26의 Sharpe·Sortino·profit factor·승률은 값이 `null`** (미측정). 대시보드 구버전의 `float(m.get("sharpe", 0))` 등이 `float(None)` 예외를 발생시키고, 미처리 예외가 API 연결을 강제로 닫는 직접 원인.
3. 소스는 운영 서버가 시작한 이후 부분 수정됐으나 **Python 서버가 재시작되지 않아 구버전 함수가 메모리에 남음**. 8081/8082 프로세스는 처음 12:08부터 실행, 변경 파일은 13:49 수정. 메모리/디스크 배포 버전 불일치 확인.
4. nginx 2999 `/academic/` 및 `/quant-research/`가 비인증 **401**인 것은 보존할 Basic Auth 보안 정책. 내부 8081/8082의 200과 인증 보호 401은 모순되지 않음. 2999의 일반 `/api/status` 404도 라우팅 설계상 정상이며 인증된 접속점은 `/academic/api/status`.

## 개선과 실제 배포
- 개발 브랜치 `feat/quant-dashboard-recovery-20261024`, 커밋 **625035d**: 미측정 통계 값은 `null`로 표시하며 0으로 조작하지 않음. 통계 해석 `TypeError`/DB 오류 등이 발생하면 두 read-only 서버가 빈 HTTP 응답 대신 안전한 **503 JSON** 반환. 회귀 테스트에서 변경 전 두 endpoint `RemoteDisconnected` 재현, 변경 후 통과.
- 커밋 **1cd25cc**: 기존 성과 차트·5초 읽기 전용 자동 연결을 유지하면서 `AWAITING_PLAN`은 **GPT 전략 계획 대기**, `AWAITING_DIAGNOSIS`는 **GPT 진단 대기**로 표시. "연구 중단·확인 필요" 오인 감소. Node DOM 브라우저 스모크의 역사적 552세대 고정 전제(구 고정규칙 배치)도 현재 진짜 MCP 연구 목표 **100세대**에 맞게 수정.
- 기존 운영 worktree에는 `scripts/fresh_research_dashboard.py`, `tests/dashboard/test_fresh_research_dashboard.py`에 이미 미커밋 작업이 있었으므로 **삭제·초기화·강제 커밋하지 않음**. 동일 변경을 별도 Git worktree에서 검증·커밋·원격 Push, 동등한 런타임 코드만 현재 작업공간에 보존적으로 반영.
- 안전 조작 대상은 **8081 / 8082 표시 전용 Python 서버** 둘뿐. 새 프로세스에서 루프백 read-only API 재확인, **Quant MCP 8787·nginx 2999·OAuth·연구 세대 원장 재기동/변경 없음**.
- 운영 API 최종 결과: 8081과 8082 `/api/status` 모두 **HTTP 200, 68/100, 최고 G64, 증거 체인 정상**; 8082 `/api/dashboard`, `/api/backtest`, 성과 HTML/JS/CSS **HTTP 200**. 구 원장 `?cohort=historical` → 552/552 체인 정상, `?cohort=original` → 452/452 체인 정상.
- 권한 확인: 2999 `/academic/`·`/academic/api/status`·`/quant-research/`·`/quant/mcp`은 미인증 401 유지, `/health` 200. 인증을 우회하거나 Basic Auth 파일을 노출·재발급하지 않음.

## 테스트
- 변경 전 TDD RED: 오류를 일으키는 원자료 타입을 모사했을 때 8081/8082 모두 예상 503 대신 RemoteDisconnected, **2 FAIL**.
- 수정 후 격리 테스트 **11 PASS / 1 deselect** (`test_dashboard_recovery_errors.py`, `test_fresh_research_dashboard.py` 조건부); 제외 이유는 분리 작업공간에 무시된 과거 원장 fixture가 없음.
- 실제 운영 데이터로 통합 테스트 `test_fresh_research_dashboard.py`, `test_fresh_original_dashboard.py`, `test_autoresearch_scope_lock.py`: **16 PASS**.
- `node --check dashboard/static/fresh-performance.js` PASS; 수정한 `original_ui_browser_smoke.cjs`를 실제 운영 8082에 연결해 **app.js 정상 연결 68/100, backtest.js 정상 연결 68/100 PASS**.
- 변경 모듈 Mypy PASS; 소스·관련 테스트 Ruff PASS. **전체 Pytest·전체 Mypy NOT RUN**; 기존 저장소에 별도 오류가 기록돼 있으며 이를 전체 PASS라고 주장하지 않음.
- 단일 프런트엔드 UI 테스트/서버 API 확인은 권한 있는 사용자 브라우저의 Basic Auth 로그인 성공을 대신 입증하지 않음.

## 남은 작업
- 백엔드 연결은 복구됐으나 T4 실제 GPT 모델 출처의 독립 인증 `false` 및 **G69~G100 잔여 32세대**, 독립 PIT/OOS 검증 BLOCKED. 대시보드 복구만으로 해결되지 않음.
- Git 브랜치는 운영 기본 브랜치에 병합 전이며, 서비스는 위와 같은 수정된 표시 전용 코드를 사용 중. 이후 정상 배포 경로에서 병합/재배포해 코드와 배포의 지속성 보장 필요.
