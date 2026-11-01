# Quant V3 지표 확장·차트 통합 A16 — 개발 기능 통합 및 실제 P9 미리보기 검증

**커밋/원격:** `5d5adb6ff6071856620f5fb09f9c0b8e1b4ae309` / `origin/integration/v3-indicators-chart-20261101` push PASS. 운영 main 병합/배포 안 함.

**기준일:** 2026-11-01 KST. 사용자 우선순위 승인: [ADR](../decisions/2026-11-01-v3-indicator-chart-priority.md). **상태: INTEGRATION_DEVELOPMENT_VERIFIED / FORMAL_RELEASE_BLOCKED / NOT_DEPLOYED.**

## 무엇을 실제로 완료했는가

- 출처 `3a75a43`(A15) 기준 별도 `integration/v3-indicators-chart-20261101` 작업트리 생성. 작업 전 A15 작업트리는 clean; 기존 Track1 작업트리의 변경 중인 4파일은 그대로 둠. A15 자체가 Track1 335/435, 차트 +12/+44 및 안전 +40 통합 커밋의 자손이므로 **추가 2중 병합 없이 코드 등록 기준 487개, explicit chart opt-in 44개, 총 531개**를 실제 `research_feature_specs` 호출로 확인. 한 지표의 보조선과 파생출력은 독립 투자 수식으로 간주하지 않음.
- `/api/chart-research/catalog`에 등록 숫자의 출처/합산, 원장 발행 여부, 수익성 검증 여부를 읽기 전용으로 노출. 기존 `/api/features/catalog` 487개 응답 및 기본 opt-in 해제 유지.
- `/chart-research` 화면에서 통합 등록 지표 검색/선택/정보 조회 및 발행 상태 표시. **미검증 지표 값을 실제 가격 차트에 생성하여 그리지 않음.** 실제 차트 이벤트 표시의 명시적 opt-in 및 패턴 선택/기간 기능은 기존 동작 유지.
- 고정된 로컬 `127.0.0.1` P9 연구 Lab `/api/backtest/runs/LAB_REPLAY_14626d55_G094`에 대해서만 원본 `VERIFIED`, `zone=development`, 개발 데이터 SHA, QQQ 1,508 OHLCV 일봉, 주문 OFF를 정확히 확인. API 4개 페이지를 읽고 표준 `MarketDataSet` 유효성 검사 후 인과형 패턴 오버레이 생성. 원본 G94 **매매 신호가 아닌 개발 QQQ 가격에 대한 패턴 이벤트**로 라벨링. 기존 연구 원장, 실제 주문, 독립 OOS 접근 없음.
- 실제 임시 Lab 서버에서 1,508봉, 확정 피벗 **337건**, 고전/엘리엇 등 패턴 이벤트 **349건**을 얻어 통합 작업트리 전용 `state/integration-chart-p9-preview/chart-research-overlay-a8.json`에 202,748바이트 private preview 생성. 해시 정합성 + 대시보드 읽기 API 재확인. 시험이 끝나면 임시 Lab 프로세스 종료. 해당 시장 원본 파생 파일은 Git 추가 및 운영 대시보드 게시 **금지**.

## 실제 검사 결과

- 전용 신규/기존 차트 연동 묶음: **9 PASS** (임시 P9 서버 포함). 지표 335·차트 A8/A10 및 대시보드 초기 부분 회귀: **99 PASS**.
- Quant 의존성을 갖춘 개발 Python 가상환경으로 `tests/contracts tests/dashboard`와 335·A8·A10 선택 검사 **195 PASS / 1 SKIP**. 스킵은 상시 `127.0.0.1:8096` 서버 미가동으로 인한 레거시 검사; 임시 호스트 기반 P9 48건 실물 감사 연결은 별도 PASS. 48개 원장을 합성하여 건수를 채우지 않음.
- `ruff check .` 전체 **PASS**; 변경 Python 파일에 대해 `mypy --follow-imports=skip` **PASS**; 인라인 JS `node` 구문 검사 **PASS**; `git diff --check` **PASS**.
- Moon 정식 `task_validate(profile=release)`는 **FAIL(exit 127: uv command not found)**. 개발용 별도 Python 검사 통과를 공식 Moon 릴리스 승인으로 대체하지 않음. 전체 프로젝트 Mypy와 전체 2,478+ Pytest, PR/CI 독립검토는 **NOT RUN/PASS 아님**. 원래 whole-Mypy Python 3.10 / NumPy 타입·스텁 문제 등 기존 장애도 별도로 남음.

## 잔여 게이트와 우선순위

1. Native Moon `uv --locked` 환경·잠금 고정, 전체 Ruff/Mypy/Pytest 및 플랫폼별 CI 수락 **BLOCKED**. 오류 완화·테스트 삭제·잠금 파일 무단 갱신 금지.
2. 내부 검토 완료 뒤에만 보호된 `main` 통합 및 기존 인증 대시보드의 실제 사용자 브라우저 검증·배포 결정. 현재 **별도 브랜치 개발**, 운영 main과 기존 Moon/Quant MCP/OAuth/서비스는 미변경.
3. 기본 등록 487/opt-in 44 및 531 총 출력은 개별 전체 데이터 계약·수식 parity·수익성 합격 수가 아니다. 외부 PIT/특수 어댑터 26개, 82개 수식 중복 감사의 파생 출력 구분, 전략별 실경제 성과는 기존 별도 증거 게이트가 필요.
4. 사용자 지정 이번 순서에서는 지표/차트 통합 회귀와 독립 QA 이후에 V05/T4 실모델 진화 효과 검증을 재개. V01~V04와 sealed OOS, 실주문 V06/V07은 별도 승인이 없으면 접근/실행 금지.

**범위 지표:** Q05/Q09/Q10/Q11/Q12/Q16/Q18/Q20. 신규 연구 세대 0, 실매매 0, sealed OOS 접근 0. 생성된 미리보기는 코드 아티팩트 커밋과 분리하여 로컬 비공개 상태로만 유지.
