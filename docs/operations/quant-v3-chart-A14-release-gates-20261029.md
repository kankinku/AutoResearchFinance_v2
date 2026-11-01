# Quant V3 A14 — 차트·대시보드 계약 복구 및 릴리스 잔여 게이트

2026-10-29 KST · 연구 브랜치 `research/v3-chart-a14-release-gates-20261029` · 기준 A13 `b01fcc2`, 코드 변경 `2a8b170` GitHub origin Push 확인.

범위: 20문답 Q05/Q09/Q11/Q15/Q17/Q20을 위해 기존 승인된 Quant V3 연구 차트 read-only 계약을 회복하고 T4 실사용의 테스트 장애를 줄임. **실거래 0·새로운 GPT 완결 세대 0·원본 G452 원장/봉인 OOS 접근 0·MCP URL/OAuth/main 변경 0**. 상위 제품 순서 V05→T4 실연결 10→100→V01~V04→V06→V07 불변.

## 실제 변경

1. Phase0 dashboard의 **원래 고정 API 경로 목록은 유지**하고 승인된 V3 chart 연구 전용 GET 경로 3개만 명시적 별도 allowlist로 수용. 이외 GET/POST 추가 경로는 정확 일치 테스트에서 실패하며 API 권한을 확대하지 않음.
2. 기존 Chart Lab 연구 서비스의 `/static/styles.css?v=d7` 및 `backtest-chart.js?v=d7`에 맞게 read-only HTML 브릿지 검증과 스타일 주입을 고침(종전 hardcode `d5`). 외부 Lab 원본 파일 수정 없음. 기존 `/`, `/chart`에서 자산 불일치로 발생한 HTTP503 차단 해소.
3. 차트 연구 HTML에 필요한 공식 SVG DOM namespace `http://www.w3.org/2000/svg` **정확히 1개만 예외적으로 인정**하여 네트워크 자산 URL(CDN, http/https) 차단 검증은 유지.
4. 별도 48개 원장 Lab은 이 호스트에서 `127.0.0.1:8096` 연결 거부. 실제 48개 이력 검사는 서버가 없으면 **명시적 SKIP** 처리하고 결과를 PASS처럼 위장하지 않음. 서버가 연결되면 기존 48개 원장·가격 봉·체결·감사 API 검증을 전부 수행. 서비스 실패 시 기존 대시보드의 200 및 차트 503 경계 테스트는 계속 수행/통과.

## 실측

- 기존 A10 기준 브랜치에서 **5 FAIL**이 그대로 재현된 것 확인.
- A14 수정된 다섯 테스트: **4 PASS / 1 SKIP** (미연결 Lab 48개 원장).
- Chart Lab 장애 격리 테스트를 더해 **5 PASS / 1 SKIP**.
- Contracts+dashboard+관련 A11~A13 회귀 **134 PASS / 1 SKIP** (26.21초).
- `UV_PROJECT_ENVIRONMENT=/tmp/moon-a11-a10-release-venv /tmp/moon-a11-uv-tool/site/bin/uv run --locked --extra dev ruff check .` **전체 PASS**.
- 변경한 프로덕션/계약 소스 등 스코프 3파일 `mypy --follow-imports=skip` PASS. 기존 chart integration fixture를 mypy에 포함하면 기존 untyped decorator 오류 1건.
- 공식 `mypy .` **미통과**: 개발 도구의 Python target 3.10과 설치된 NumPy 2.5.3의 Python 3.12 PEP 695 타입 정의 불일치, pandas 3.0.6의 추가 타입 스텁 부재. 진단용 `mypy --python-version 3.12`만으로도 기존 소스 **306 errors / 33 files / 369 checked**; 미지정 경로의 package-only 검사도 **217 errors / 10 files**. 스텁 무시나 프로젝트 Python 지원 버전 삭제로 거짓 통과시키지 않음.
- Moon 공식 `task_validate(profile=release)` **FAIL exit127**, native PATH에 uv 부재. 격리 `uv` 통한 Ruff PASS는 공식 릴리스 통과 대체 아님.
- 전체 2,478 테스트 완주는 **이 단계 미수행**. 134개의 명시된 관련 테스트만 PASS, 외부 48-run 연결 검증은 별도 차단.

## 남은 작업 및 승인 게이트

- **A15 (연결성/타입 별도):** 백테스트 Lab 8096 시작·검증은 별도 소유 프로젝트 상태/서비스 인증·read-only 원장 적합성 조사 후 승인된 운영 절차에서만 수행. 원장 48개 강제 합성·임의 가동 금지. 실제 원장이 연결되어야 독립 통합 테스트 SKIP 해제.
- Mypy는 기존 py3.10 지원과 NumPy/외부 지표 스텁을 함께 만족하는 재현 가능한 버전 행렬 및 *기존 전체* 217+ typing errors 분류 후 수정; `--ignore-missing-imports`나 full-gate 축소 금지.
- Native Moon `uv` 탐지/보장 방식은 운영 관리자/실행기 환경 문제로 계속 BLOCKED; 호스트 PATH/OAuth/공식 정책을 임의 변경하지 않음. 전체 Pytest, 공식 릴리스, 독립 OOS, 수익성 증명, 운영 main 병합은 **불허**.
- 상위 T4 실제 GPT/MCP OAuth 보존/실연결 연구 10→100 계승은 본 부가 A14 테스트 수정 때문에 뒤로 밀지 않음.

이 문서는 실제 실험 코드 변경 및 검증 결과를 설명하는 기록이다. GPT 유전 세대나 유효 투자 알파 입증이 아니다.
