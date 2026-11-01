# Quant V3 A8 · 선택형 StrategyIR FeatureRef · 차트 연구 화면 1차 연결

- 검증: 2026-10-29T13:53:27.711181+09:00
- 기본 카탈로그 447 지표 유지. chart_research_opt_in=True 에서만
  **연구용 scalar 44개(총 491개 출력)** 추가.
- 구성: 4개 고전 × 6개 채널(탐지·단계·품질·넥라인 거리·
  무효화 거리·확정 경과봉), 하모닉 4개×3개 채널(탐지·단계·PRZ 거리),
  엘리엇 4개×2개 채널(외부 형태 탐지·외부 단계).
- 모든 스칼라 출력에 버전·원본 소스 SHA·timeframe/inputs·canonical ID
  보존. 기본 false / explicit DEVELOPMENT opt-in 시에만 FeatureRef 재생.
- 44개 개별 named feature의 calculator·직접 계산·
  FeatureRef 벡터 완전 동일; 기본 설정에서 전체 접근 거부.
- A7 고전 4종 136개 잘린 시계열의 이벤트와 피벗 불변.
- A3 전체 차트 4,608회 인과 검사 및 A7 4개 수정 승인 유지.
- 읽기 전용 대시보드 '/chart-research'와 API 2개 연결.
- UI에는 종가·피벗 발생봉과 실제 확인봉·후보/확정 상태 및
  세대/기간/패턴 선택, 체결 기록 미가용 표시.
- DEMO 스위치는 분명하게 합성 사례임을 표시하며 절대 시장 가격이나
  실제 거래, 특정 G세대 성과로 사칭하지 않음.
- 현 프로젝트는 실제 개발 데이터 오버레이를 state에 게시하지 않았음.

## 현장 적용 전 필수

- A8는 FeatureRef의 연구 입력 변환과 UI 시연까지 검증했고
  **실제 G세대 StrategyIR replay 및 체결/equity 검증까지 완료한 것은 아님**.
- A9 라벨이 있는 실 데이터 및 다양한 레짐 오탐률 검사.
- A10 +40 미커밋 지표의 안전한 통합·동일성 검증 이후 전체 CI.
- Moon 공식 release uv 미설치로 차단, 운영 main·실거래 변경 없음.
