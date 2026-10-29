# Quant V3 A6 · 엘리엇 파동 계층 검증 및 진행 상태 연구 모듈

- 실측: 2026-10-29T12:54:10.637317+09:00
- 범위: core/features/elliott_structure.py 추가, **기존 447개 등록 지표 불변**.
- 1~4파 단계는 DEVELOPING, 5파 외곽 조건 통과는 CONFIRMED이나
  실제 5-3-5-3-5 세부파가 확인되지 않으면 structurally_verified=False.
- 매 파동의 known_at과 차트 스윙 확정 시각을 구분하고, 다음 관측
  가능한 봉 이전에는 신호/확인으로 사용하지 않음. 대안 카운트 최대 3개.
- 필수 규칙: 2파 시작점 침범, 3파 최단, 4파 1파 영역 교차 및
  5파 추세 정점 미갱신을 각각 INVALIDATED로 구분.
- 조정 ABC: 외곽 4 피벗만 존재하면 OUTER_ONLY, Zigzag는 5-3-5,
  Flat은 3-3-5 확인된 하위 피벗과 B 되돌림 범위가 함께 충족되어야 구분.
- W-X-Y 및 W-X-Y-X-Z: W/X/Y/(X/Z) 각 컴포넌트가 세 구간
  ABC 계열과 확인된 세부파로 나뉘어야 구조 검증.
- 다중 스케일의 세부 피벗이 시작/끝/시점에서 정렬되지 않으면
  억지로 보간하거나 완성 파동으로 확정하지 않음.
- 발행된 WaveHypothesisStream 기록은 불변이며 후속 가격으로
  과거 가설을 수정·삭제하지 않음.
- A3 기존 12개 차트 4,608회 전체 prefix 결과 변경
  0 / 확정시각 위반
  0 / 실행 예외
  0.
- A5 이전 지표용 동결 해시 비교 48개 유지. 신규 계산기는 기존
  StrategyIR 지표/실매매 경로로 연결하지 않았음.

## 현재 제한

- 이 결과는 세부파가 *명시적으로 확인된 경우*의 수학적 판정기.
  실제 모든 시장 파동을 자동으로 참값 라벨링하는 모델이 아님.
- Triangle, diagonal, ending truncated fifth, 복수 파동 차수의 대안
  탐색, OOS 수익성 및 실거래는 A8/A9 이후 별도 연구 대상.
- Source named above is reference only; copied third-party code 없음.
- A7 역헤드앤숄더 기존 오탐 1개는 여전히 예상 실패.
- 운영 main/OAuth/MCP URL/G원장/2026 sealed OOS/주문설정 변경 없음.
