# D4 — 차트 우선 메인 레이아웃 · 연구 운영 테마

기준일: 2026-10-27 KST
기존 접속 경로: /academic/chart 또는 /quant-research/chart, 기존 Basic 인증 유지.

## 화면 변경
- 차트 페이지의 첫 번째 핵심 패널을 원본 감사 검증 캔들/실제 엔진 체결 차트로 변경.
- 이전에 차트보다 먼저 표시되던 연구 진행률, 8개 성과 KPI, 원본 계보 안내는 차트 아래로 이동.
- 연구 KPI는 한 개의 접근성 있는 접기/펼치기 영역으로 묶음. DOM ID와 업데이트 JS는 그대로라 기존 기능 보존.
- 원본 연구 계보(146세대, 검증 차트 48개)의 상태 요약 및 표는 차트 바로 아래에 유지.
- 캔들 가격 영역 높이: 데스크톱 실제 확인 576px(1440px 뷰포트, CSS 최대 680px), 모바일 380px.
- 차트 페이지 전체 너비: 최대 1520px, 가로 공간을 가격·체결 시각화에 우선 배분.
- UI 테마: 기존 연구 운영 dashboard/static/styles.css의 라이트 팔레트와 동일 (#f5f7fb 바탕, #fff 패널, #e4e8ef 테두리, #2563eb 강조), 공통 폰트 및 배지 스타일 사용.
- 변화는 인증된 기존 Dashboard GET /chart HTML/스타일에만 적용. Lab P0~P10 원본 차트/원본 연구 코드/원장/체결·비용·차트 API 내용 변경 없음.

## 검증
- 기존 테스트 8건 통과 (테마·DOM 주요 패널 위치·허용 정적 자산 규칙 포함).
- Chromium 원래 Quant 대시보드의 메뉴/차트: 데스크톱 1440x900, 모바일 390x844 실제 렌더링.
- 차트가 원본 성과 요약 및 연구 KPI 위에 위치하고, 연구 KPI 접힘, 테마 토큰과 추가 CSS 로드 확인.
- G146 총 148 체결, G94 A/B COMPARABLE. JS/HTTP 오류 0, 모바일 가로 넘침 0.
- Lab 브라우저 증거 state/d4-chart-first-theme-20261027/d4_browser_results.json 및 chart_main_research_theme_desktop.png / mobile.png.
- 외부 Basic 인증, nginx, Quant MCP/OAuth/실거래 설정은 그대로 유지.

## 적용·롤백
- 배포 범위는 소스 scripts/quant_chart_lab_bridge.py, scripts/quant-chart-primary.css, tests/dashboard/test_quant_chart_lab_integration.py 및 본 보고서에 한정.
- 기존 8082 프로세스만 재시작하면 적용. 문제가 있으면 직전 대시보드 커밋으로 소스 롤백 후 8082만 재시작.


## 실제 운영 배포 확인

- D4 소스 커밋: bef7611. 8082 대시보드만 PID 203515로 재기동.
- 변경 후 /, /backtest, /chart, /api/dashboard, /api/backtest, /api/chart/backtest, /api/chart/backtest/original-lineage, /chart-assets/quant-chart-primary.css 모두 HTTP 200.
- 실제 운영 8082의 Chromium 데스크톱(1440×900), 모바일(390×844) 최종 확인: **차트 첫 패널**, 원본 연구 영역은 아래 접힘, 감사 원본 요약은 아래, 가격 차트 높이 각각 576px·380px.
- 연구 운영 배경 #f5f7fb, 브랜드 강조 #2563eb 정확히 일치.
- G146 체결 148건 및 G94 비교 COMPARABLE. JavaScript 오류 0, HTTP 오류 0, 문서 가로 넘침 0.
- 실브라우저 검증 로그: Lab/state/d4-chart-first-theme-20261027/deployed_d4_browser_results.json 및 deployed_d4_chart_main_desktop.png, deployed_d4_chart_main_mobile.png.
- 외부 /academic/chart 및 /quant-research/chart은 기존 인증 없이는 401 Basic 유지. nginx·OAuth·MCP·개발 원본·트레이스 변경 없음.
- 연구 상태 카드 등 기존 DOM ID를 모두 유지했으므로 닫힌 상태에서도 기존 데이터 로딩/상호작용 보존. 실제 로그인 후 사용자 UI 확인은 별도.
