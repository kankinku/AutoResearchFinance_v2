# Quant V3 A15 — 외부 백테스트 Lab 실제 P9 48개 읽기 전용 감사 검증

2026-10-29 KST · 연구 브랜치 `research/v3-chart-a15-hermetic-lab-preflight-20261029` · A14 기준 `4c75469`, A15 코드 `b66860f` GitHub origin Push 확인.

## 범위와 안전 경계

Q05/Q09/Q11/Q15/Q17/Q20. 기존 A14에서 `127.0.0.1:8096` 서비스 미기동으로 SKIP됐던 48개 실제 Lab 개발 원장의 증거를 재검증한다. 외부 Lab 저장소/원장 원본, G452 원장, 기 운영 supervisor/MCP URL/OAuth, 운영 main, 봉인 독립 OOS, 실주문 환경은 변경·재시작·열람하지 않는다. **신규 GPT 완결 세대 0, 실거래/봉인 OOS 접근 0**. 기존 제품 순서 V05→T4→V01~V04→V06→V07 유지.

## 원인 분석

1. 외부 Lab `Quant-Backtest-Lab-20261027`는 실제 소스 및 검증 아카이브를 보유한다. `8096` 포트에 서버가 떠 있지 않은 상태지만, **백업 원장이 없는 것은 아니다**. 운영 supervisor를 재가동하지 않음.
2. P8 `state/lab-p8-verified-original-generations-20261027` 원장은 저장된 **33 검증 실행/원본 131세대**이므로 이전 테스트 기대치 48/146을 충족하지 않는다.
3. P9 `state/lab-p9-original-G132-G146-20261027/preview`는 별도 저장된 **48 검증 실행/원본 146세대**. 원본 Lab `preview_app`을 `TestClient(base_url='http://127.0.0.1')`로 직접 읽어 상태 200과 위 건수 확인. 합성 데이터로 48을 만들어내지 않았음.

## 실제 구현과 종단 간 증거

- `tests/dashboard/test_v3_a15_hermetic_p9_lab.py` 추가. 정확한 기존 P9 원본 경로·필수 3파일·symlink 무결성 확인 후 외부 Lab에 이미 있는 `scripts.run_backtest_lab_preview`를 **테스트 수명에 한정된 임시 127.0.0.1 무작위 포트**에서 실행한다.
- 원본 Lab preview에는 GET-only, localhost-only, 승인된 개발 state 경로, 비인증 임의 운영 명령 접근 차단이 구현되어 있다. 신규 테스트는 원본 파일을 변경하지 않고 브리지 `LAB_SERVICE`를 pytest monkeypatch로 로컬 임시 포트에 연결하며, `finally`에서 프로세스를 종료한다.
- 실제 Lab 응답 48개와 원본 146세대/verified_count=48, G94 verification VERIFIED, QQQ 1,508개 candles, G94/G146 COMPARABLE, 자산 200 응답, POST 405와 경로 탈출 차단 확인. 원본 `8096` 상시 서버는 계속 미기동 상태 유지.
- 외부 Lab 경로 자체가 없는 다른 CI 호스트에서는 SKIP로 명시하며 **프로덕션 원장 업로드/합성 폴백 불허**. Lab 원본의 실제 검증 원장이 부분 누락되거나 33개만 제공되면 테스트는 FAIL.

## 실측 검증

- 신규 실제 P9 임시 로컬 서버 종단 간 테스트 **1 PASS**.
- `tests/contracts tests/dashboard` + A11/A12/A13 관련 검사 **135 PASS, 1 SKIP**. 이 1개 SKIP은 기존 상시 `8096` 직접 의존 통합 검사이며, 별도 새 P9 실제 종단 간 검증은 통과.
- 격리 `uv run --locked --extra dev ruff check .` 전체 PASS; 신규 파일 `mypy --follow-imports=skip` PASS.
- 공식 Moon `task_validate(profile=release)`는 **FAIL, exit127 (`uv: command not found`)**. 격리 도구의 정상 실행이 Moon 공식 release 통과를 대신할 수 없음.
- 전체 2,478개 Pytest 장기 실행은 **이번 A15 범위에서 재수행하지 않음**. 기존 whole-Mypy는 python3.10 대상/NumPy 타입 및 다수 기존 소스 타입 오류로 **미통과 상태 유지**, 임의 ignore/약화하지 않음.

## 연결형 Quant 상태의 별도 참고 사항

기존 연결된 Quant MCP의 읽기 전용 `get_workspace_status`는 `PARTIAL`(초기 상태 일부 미완성), `get_dashboard_status`는 `ONLINE`, `PAPER_ONLY`, live OFF를 반환. `get_research_batch_status`는 과거 2026-10-27 생성된 로컬 결정론적 작업 100/100 완료를 반환했지만, 이것은 **이번 A15에서 생성한 세대가 아니며, 매 세대 실제 LLM 진단이 입증된 T4 완료로 취급하지 않는다**. 연결형 실제 GPT 가설→백테스트→LLM 원인→다음 계획→증거 커밋의 독립 검증은 여전히 필요.

## 다음

V05/T4 실제 MCP 연결 10→100의 **매 세대 GPT 진단·원인 분석 증거와 원장 연속성**을 먼저 검증. 동시에 Native Moon 실행기의 `uv` 경로와 whole-Mypy(3.10 호환/스텁/기존 오류) 게이트를 운영 환경 담당 범위에서 해결하되, 권한/OAuth/PIT·OOS/공식 검사 완화 없이 진행. 운영 main 병합, 독립 투자 수익성 인정, 실거래 허가는 보류.
