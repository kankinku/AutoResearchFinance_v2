# Quant V3 A13 — CI 의존성 격리·35봉 지연 합성 증거

- 연구 브랜치: `research/v3-chart-a12-lag-provenance-20261029`, 기준 `2286f99` (A12 연구 코드), 신규 코드 `4875693` (GitHub origin Push 확인). 대응 Q05/Q07/Q09/Q11/Q12/Q15/Q17/Q20.
- **새로운 완결 GPT 세대 0 / 실거래 0 / 봉인 OOS 접근 0 / 운영 main·OAuth·MCP 변경 0.** 개발 검증 한정. 상위 승인 순서 V05→T4→V01~V04→V06→V07 불변.

## 수정

1. `scripts/run_academic_cohort.py`가 모듈 import 시 `fresh_development_cohort_controller_20261021`을 import하면서 실제 `state/.../session-id.txt`를 읽는 문제를 해결. 기존 run() 입력/원장/권한/백업 검사 후 실제로 연구 세대 실행 직전에만 지연 import. 고정 권한/검증 우회 없음.
2. `tests/research/test_v3_a13_ci_isolation.py`: 새 프로세스에서 모든 `session-id.txt` 읽기를 금지한 상태로 operator import 성공 확인; 실제 G452 원장이 없어도 75개 합성 봉·35봉 지연·결정 다음 봉 시가 체결·두 체결·원장/백테스트 equity hash 일치 확인.

## 검증

- 수정 전 신규 테스트 2개 중 세션 파일 import 테스트 1개 의도대로 실패, 35봉 합성 체결 테스트 1개 통과. 수정 후 신규/운영자 테스트 **6/6 통과**, 이전 A9~A12 관련 포함 **46/46 통과**.
- `uv run --locked --extra dev ruff check .` : 별도 격리 `uv` 경로/venv 사용 **전체 PASS**.
- 변경 파일 Mypy `--follow-imports=skip`: **2개 PASS**.
- `uv run --locked --extra dev mypy .`: **FAIL**. 기존 `pandas` 스텁 미등록 및 NumPy 타입 정의가 프로젝트 `python_version=3.10` 설정과 충돌. 임의로 mypy 범위/설정 완화하지 않음.
- 전체 `pytest`: 2,478개 테스트 수집 PASS; 3분 제한 내 약 40%까지 진행하고 **timeout 중단**. 관측 dashboard/public API 5개 실패를 이전 A10 기준 브랜치에서 **동일한 5개 실패**로 재현(원래 API의 `/chart-research` 경로와 동결 목록 충돌, 별도 HTTP 503, chart JS 자산 이름/정적 SVG URL 검사 충돌). 관련 A13 수정으로 새로 생긴 실패 증거 없음. 전체 Suite PASS 주장 금지.
- Moon native `task_validate(release)`: **FAIL(exit127)**. 서비스 PATH에서 `uv` 미탐지. 승인 없이 호스트 전역 PATH, 인증 서비스 또는 `moon.config.json` 변경하지 않음.
- 백테스트 엔진 `core/backtest`, `core/data`, `core/costs`, `core/evaluator`, `core/integrity`, `core/validation` 불변; 원본 A11/B4 사전등록·보완 A12 수익률 불변.

## 다음 검토

1. A10 기준 브랜치부터 기존 대시보드 경로 계약/정적 파일/HTTP 503 5건을 별도 근거 기반으로 수정하고 회귀 확인.
2. `mypy` Python target/의존성 스텁의 개발 도구 호환성을 기술 검증한 뒤 기존 계약 범위에서 수리(기준 완화 금지).
3. Moon 공식 릴리스 실행기의 격리 `uv` 탐지 방법 검토. 전역 재등록/환경 수정 승인·검증 전까지 **RELEASE BLOCKED**, main 머지/운영 배포 금지.
4. 기존 OAuth identity를 안전하게 복원한 후 T4 실제 연결형 GPT 10→100 완결 연구를 최우선 재개.
