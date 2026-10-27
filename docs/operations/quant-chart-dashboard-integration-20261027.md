# D1–D3 기존 Quant 대시보드 · 검증 매매 차트 통합

기준: 2026-10-27, 대시보드 전용 변경.

## D1: 기존 인증 대시보드 연결
- 원본 대시보드 127.0.0.1:8082, 독립 Lab 차트 증거 127.0.0.1:8096.
- 기존 인증 경로 /academic/chart 및 /quant-research/chart, 읽기 전용 API /api/chart/backtest 하위.
- 기존 연구 화면/연구 원장 /api/dashboard /api/backtest는 유지. HTML 연구 화면에서 차트 메뉴로 이동 가능.
- 원본 차트 정적 JS/CSS/Lightweight Charts 리소스는 chart-assets 엄격한 allowlist만 허용. 모든 fetch URL은 기존 대시보드 동일 origin 상대경로로 재작성.
- 인증 및 쿠키 정보를 차트 백엔드로 포워딩하지 않음. API는 127.0.0.1:8096 고정, GET-only, 허용된 증거 경로로 제한, 응답 크기 상한.
- 기존 nginx Basic Auth 및 GET-only 제한은 변함없음. Tailscale Funnel /quant/mcp /OAuth/실거래 기능은 변경하지 않음.
- P9 고정 캡처 146/150 원본, 원본 감사 증거 재현 완료 48개 (G94, G100~G146). G147~G150 미포함.

## D2: 실제 브라우저 검증
- 데스크톱 Chromium 1440x900, 모바일 390x844: 기존 홈 -> 차트 메뉴 -> G146 148개 체결 -> G94 비교 COMPARABLE 확인.
- 146개 원본 세대 표시, 48개 감사 검증 전략 선택, JS 오류 0, HTTP 실패 0, 양쪽 가로 넘침 0.
- 스크린샷 및 기계 판정: Lab/state/d123-integration-browser-20261027.
- 원본 개발 QQQ 데이터 재현일 뿐 독립 OOS 또는 실거래 성과 아님.

## D3: 회귀·운영·접근 검증
- 기존/신규 dashboard 통합 테스트 26개 PASS. Ruff, Mypy 통과.
- 차트 백엔드가 끊어지면 차트는 503, 기존 연구 API는 200 유지.
- 공개 도메인 HTTPS /academic/ /quant-research/ 은 인증 없는 요청에 Basic 401을 반환.
- 실제 사용자 비밀번호나 쿠키를 도구로 취득하지 않으므로 인증을 통과한 사용자 브라우저 세션 검증은 미수행. nginx 인증 구성은 변경하지 않음.
- 서비스를 실제 재기동한 이후 운영 HTTP 프로브를 검증할 것.
- 로컬 Lab 8096 서비스는 기존 별도 프로세스이며 supervisors에 등록된 상태가 아니어서 재기동 시 가용성 관리 보강이 향후 권장됨.

## 롤백
- Git 대시보드 커밋 이전 버전으로 대시보드 프로세스(8082)만 교체. 연구 8787과 nginx 불변.


## 실제 배포 및 사후 검증

- 실제 배포 소스 커밋 12d1f71, 기존 Quant 소스 브랜치 fix/quant-g100-to-g150-continuation-20261027.
- 기존 8082 원본 대시보드 프로세스만 재시작, 새 PID 191471. 8081 연구 화면 PID 93996, Quant MCP 8787 PID 167970, Lab 8096 PID 151839는 재시작하지 않음.
- 운영 내부 GET /, /backtest, /chart, /api/dashboard, /api/backtest, /api/chart/backtest, /api/chart/backtest/original-lineage, G146 verification, chart-assets JS 모두 HTTP 200.
- 실제 운영 8082 Chromium 데스크톱(1440x900)·모바일(390x844)에서 기존 홈→차트 메뉴→G146 체결 148건→G94 비교 COMPARABLE, 검증 차트 48개/원본 146세대 확인. JS/HTTP 오류 0, 가로 넘침 0.
- 브라우저 증거: 독립 Lab의 state/d123-integration-browser-20261027/production_dashboard_d123_browser.json 및 production_8082_desktop.png, production_8082_mobile.png.
- 공개 HTTPS /academic/, /academic/chart, /academic/api/chart/backtest, /academic/chart-assets/backtest-chart.js, /quant-research/chart는 인증 없는 접근에 HTTP 401 Basic 반환. 기존 인증 계정을 유지하며 비밀번호를 조회하거나 교체하지 않음.
- nginx -t 정상. Quant MCP 8787 /mcp 응답 401(기존 OAuth 독립), URL/비밀키/실주문 설정 변경 없음. PythonMCP Git HEAD d0c0862 불변.
- 실제 사용자 자격증명으로 Basic 인증을 통과한 브라우저 검사는 계정 정보를 사용하지 않아 미수행. 내부 Chromium 렌더링 및 외부 무인증 차단은 각각 검증.
- 8082와 8096은 독립 장기 실행 프로세스. 현재 정상이나 재부팅 자동 복구 체계는 별도 운영 개선 사항.
