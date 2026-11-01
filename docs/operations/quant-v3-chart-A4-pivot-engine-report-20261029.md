# Quant V3 A4 · 공통 인과형 피벗·스윙 엔진 개선 보고

- 실측일: 2026-10-29T12:17:33.198150+09:00
- 코드: `core/features/causal_pivots.py` 새 공통 tracker + 기존
  `chart_patterns.py`의 버전 호환 계산 어댑터.
- 동결한 기존 차트 결과 48개(12패턴×4합성경로) sha256 일치: **차이 0**
- A3 봉별 전길이 prefix 4608회:
  과거값 변경 0,
  확정 시점 위반 0,
  계산 오류 0.
- 새 tracker의 상태 이벤트: **APPEND/REPLACE/RESET**. 더 극단적인
  같은 방향 피벗이 나와도 이전에 보고된 관측 이벤트를 삭제하지 않음.
- DEVELOPING은 오른쪽 확인 봉이 부족한 임시 후보로 제공되며
  시장가 진입·확정 패턴으로 사용 금지.
- threshold mode: percent(기존 기본값), absolute, ATR(과거 봉만 사용).
  복수 스케일은 독립 tracker로 처리. 이벤트 로그는 증거 보존을 위해
  누적 저장하며 활성 관측 창은 2*c+1 이내로 유지.
- 모든 기존 지표/원장 보존: 447개 등록 유지. 신규 지표 수 증가 없음.

## 후속 작업

- A5 하모닉 BC/AB=CD/PRZ 원본 검증 및 4종 수식 보정
- A6 파동 내부 서브웨이브 검증과 진행/무효화 상태 모델
- A7 역헤드앤숄더 대칭 오탐·넥라인 확정 검증
- A8/A9: experimental threshold modes의 StrategyIR opt-in, 성능/실데이터 검증

## 제한

- 원본 기준 차트 알고리즘 자체의 판정 오류 2개는 A5/A7까지 미수정.
- Synthetic causal pass는 패턴의 금융적 예측력·거래 가능성 증명이 아님.
- Main/G 원장/2026 sealed OOS/OAuth/MCP URL/실주문 설정 변경 없음.
