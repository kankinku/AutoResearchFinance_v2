# Quant V3 A2 수식 정밀검토 · A3 봉 단위 미래참조 검사

- 검사 시각: 2026-10-29T11:34:47.023094+09:00
- A2: 기존 패턴 12종의 원본 규칙/현재 구현 편차, 미구현 18종 보류를 구별.
- 4종 하모닉: 주요 XA/AB/BC/CD 비율 누락 확인. 원본 공개 페이지에서
  확인한 비율은 법적 사용권 또는 구현 수치 일치 증명이 아니므로 별도
  상업적 이용 검토 전 승인된 제품 기능으로 승격하지 않는다.
- 버터플라이는 X 기준 0.27 XA 초과(=A 기준 1.27 XA)라는
  구현 표현과 공식 표현의 기준점 차이를 해소했다. 실제 결함은
  CD/BC 하한이 너무 완화되고 상한/AB=CD/PRZ 합치기를 미검사하는 점.
- 가틀리는 CD/BC 1.13~1.618과 AB=CD 누락이 확인된 오탐 위험.
- 배트/크랩도 정의를 구성하는 BC 확장을 판정하지 않아 오탐 위험.
- 엘리엇 5파는 바깥 6개 피벗만 검사하여 5-3-5-3-5 내부파 미검증.
- ABC/WXY는 Zigzag와 Flat, 복합 조정 구분이 되지 않음.

## A3 스트리밍 전체 길이별 재연산 실측

- 합성 시나리오: 3개, 각 128봉
- 차트 계산기: 12개, 전체 접두부 평가 4608회
- 과거 신호 불일치: 0건
- 피벗 확정 시점 이전의 신호: 0건
- 계산 예외·비정상 출력: 0건
- 패턴·레짐 조합 중 이벤트 0: 22 / 36
- 총 이벤트 수: 40

## 범위 한계 및 후속

- A3은 bar-close 접두부·피벗 우측 확정 시간의 누수 부재를 확인했을 뿐,
  캔들 자체에서 같은 봉 종가를 읽어 미래로 앞당긴 주문 실행이 없다는
  사실까지 독립 테스트한 것은 아니다. StrategyIR next-open 실행은 추가 확인 필요.
- 원본 비율 결함과 역헤드앤숄더 동률 오탐 2건은 기존 XFAIL 보존.
- A2 하모닉 IP/상표·허가 및 추가 후보 18개 수식 오라클은 계속 미완료.
- 다음 실행: A3 개발용 StrategyIR 실제 재생·희귀 양성 종합경로,
  A4 공통 피벗 메타데이터, A5/A7 오류 수정(테스트 선행).

## 신뢰 가능한 원본 링크

- https://harmonictrader.com/harmonic-patterns/bat-pattern/
- https://harmonictrader.com/harmonic-patterns/butterfly-pattern/
- https://harmonictrader.com/harmonic-patterns/crab-pattern/
- https://harmonictrader.com/harmonic-patterns/gartley-pattern/
- https://harmonictrader.com/harmonicpatternorigin/
- https://www.elliottwave.com/waveopedia/corrective-waves/
- https://www.elliottwave.com/waveopedia/flats/
- https://www.elliottwave.com/waveopedia/impulse/
- https://www.elliottwave.com/waveopedia/zigzags/
