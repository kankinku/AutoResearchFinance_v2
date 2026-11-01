# Quant V3 지표·차트 A18 — 전체 테스트 완료 및 실제 차단 원인 분리

2026-11-01 KST · 사용자 지시 "다음"을 따라 기존 Draft PR #5 `integration/v3-indicators-chart-20261101`에서 수행. **개발 코드·테스트만**, 인증/운영 프로세스/계보/봉인 OOS/실거래는 변경하지 않음.

## 1. 최초 전체 Pytest — **종료까지 실행, 실패도 보존**

- Python 3.12 `uv --locked --extra dev` 설치 환경, `.venv/bin/python -m pytest -q --durations=20`: **2,483건 수집 → 2,452 PASS / 13 FAIL / 18 SKIP**, 총 **770.36초**(12분 50초). 증거 로그는 해당 Moon 호스트 `/tmp/quant-chart-full-pytest-py312-20261101.log`이며 Git에 원문/개인 경로를 추가하지 않음.
- 위 수치는 **아래 수정 이전에 시작한 전체 검사**이고, 수정 후 전체 Pytest를 2,483건 재실행하여 PASS로 확정한 것은 아님.
- **4건의 오래된 기대값 테스트를 수정해 별도 PASS 재확인**: (i) MCP 기본 등록 수 과거 173 → 현재 실제 487, 차트 opt-in 44는 기본 노출되지 않음. (ii) SDK 공개 계약 32툴 `get_algorithm_research`의 `response_mode=full`은 어댑터가 처리하고 기본 compact는 체크포인트 부재 시 정상 거부. 32툴 호출 1회/주문 비활성 검증 유지, compact 부재 fail-closed 별도 테스트 추가. (iii) OAuth 런처는 기존 키가 없을 때 재생성하지 않고 중단하는 보안 정책이 현재 정상 동작이므로 해당 상태를 직접 검증. (iv) Supervisor 배포 템플릿이 운영의 고정 `AutoResearchFinance_v2-fresh-research-20261021`로 연결되는 것을 검증하고 연구 worktree로 교체 금지.
- **남은 9건의 원인:** 모두 2026-10-17 고정 **G33 학술 연구 스냅샷 부재**로 실패. 기대 원본 `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/research/audits/phase1-20261017-1950/snapshot-manifest.json` 없음. 전체 workspace 동일 규칙 경로의 manifest 검색 0건. 임의 합성/원본 해시 변경/우회/스킵으로 위장하지 않음. 원래 원본 DB와 매니페스트를 확보해 SHA 및 G29/G33 원본 증거와 대조한 뒤에만 재실행해야 함.
- 18 SKIP: 구형 별도 상시 Lab 서버 미기동 1건, 외부 historical Moon evidence 미설치 17건. 참고로 임시 격리 P9 실제 48실행/1,508봉 테스트는 별도로 통과해 실물 Lab 원장 전체가 없어졌다는 뜻은 아님.
- 신규 포함 관련 코어/차트/양식/보안·감사·scope 테스트 묶음 **131 PASS**, 전체 `uv run --locked --extra dev ruff check .` PASS. 테스트 파일 추가분까지 포함하는 전체 Pytest 새 총건수는 2,484건이며 전체 재실행 미실시.

## 2. Mypy 비완화 개선 (Python 3.10 동일 설정)

- 기존: **309 오류 / 35파일**. 변경 후 `mypy .` 실제 재실행: **283 오류 / 28파일**(26건 및 7파일 감소). 유형상 외부 벤더 `ta/*` 미타입 소스, 옛 스크립트/연구 계약, `pandas` 스텁 부재 등이 계속 남음.
- 인과형 차트 브리지 `PivotDecision`을 기존 ClassicalEvent 이름과 겹쳐 추론한 6 오류 수정(순수 변수명 변경, 파형·판정·시점 로직 그대로). A0/A9 감사 파일 변수명·정적 타입·결측치 검증 경로 보완. 82종 수식 중복 감사의 `overlap82`/source callable/480봉 수치 대조형 시그니처 강화, 이 파일의 남은 오류는 pandas 타입 스텁 의존성 하나.
- Python 3.10의 `tomllib` 수집 실패는 설치된 `tomli` 호환 import로 해결; Python 3.10에서 해당 3개 MCP SDK 테스트 PASS. 복구 연구 원장 및 주문 관련 소스 변경 없음.
- 전체 mypy 오류가 남아 있으므로 **공식 release 차단 해제 아님.** `uv run --locked --extra dev mypy .`는 별도의 Python3.12 numpy `.pyi` 구문/설정 불일치로 여전히 조기 FAIL. 전역 검사 ignore·타입 에러 숨기기·whole test 스킵 설정 변경 안 함.

## 3. 완료·미완료 판정

- 수정 범위의 회귀: PASS(131건) 및 3.10 SDK 호환 PASS. 전체 원본 suite: 13 FAIL/18 SKIP, 그중 4건만 별도 수정 재검증, 9건 원본 fixture BLOCKED. 완전한 Release/독립 CI/main 병합/배포: **NO-GO**.
- 다음 작업: 원본 G33 증거를 해시 검증해 합법적으로 복원 가능하면 9건 재실행. 나머지 283개 Mypy 에러의 타입 개선과 Python3.10/3.12 패키지 버전 호환 해결. 독립 QA 이후 보호된 main 통합·기존 대시보드 실제 브라우저 검증 여부 결정.
- 백테스트 연구 세대 0개 추가, 이전 공식 300세대 원장·부모 해시·Quant/Moon 고정 MCP URL·OAuth·실주문 OFF·sealed OOS·운영 main **그대로 유지**.
