# Quant V3 A5 · 하모닉 4종 정밀 수정 및 인과성 검증

- 실측 시각: 2026-10-29T12:42:43.679528+09:00
- 대상: 가틀리·버터플라이·배트·크랩 기존 등록 4종, 지표 수 증설 없음(447개 유지).
- 공통 파동 계산: XABCD 가격 방향, AB/XA, BC/AB, CD/BC, CD/AB, AD/XA;
  XA와 BC의 독립 목표 가격 구간 교집합(PRZ) 및 AB=CD 보조 조건.
- 가틀리: B/XA .618±3%, XA .786 되돌림, CD/BC 1.13–1.618.
- 버터플라이: B/XA .786 근접, A 기준 XA 1.27 확장, CD/BC 1.618–2.618.
- 배트: B/XA .382–.50 부근, XA .886 되돌림, CD/BC 1.618–2.618.
- 크랩: B/XA .382–.618 부근, XA 1.618 확장, CD/BC 2.24–3.618.
- 네 패턴 모두 원문 근거로 게이트를 강화했으나 ±허용 범위는 독립 휴리스틱.
- 이전 Gartley CD/BC 1.70588 과대 확장, Crab CD/BC 5.472 오탐 제거.
- 검증: 유효 4×상승·하락=8개 경로 D 확인봉 index26에서 각 1신호;
  무효 4개 경로 신호 0, D 확인 이전 신호 0.
- A3 전체 bar-by-bar 4608회: 과거값 변경
  0 / 피벗 확정 지연 위반
  0 / 계산 예외
  0.
- A4 기존 기준 48개 합성 출력 SHA 일치. 이 합성 경로에서 하모닉 이벤트
  발생 건수가 0이었으므로 수치 수정의 실효성은 새 유효/무효 fixture로 검증.
- 기존 역헤드앤숄더 XFAIL은 A7까지 유지.

## 주의·미완료

- 공개 원본의 피보나치 가격 비율을 비교한 연구용 독립 구현이며
  원저작자·상표권자의 상업적 사용 허가를 받은 구현이 아니다.
- 실제 시장의 신호 분포, 복합 PRZ가 수익에 미치는 효과, 원본 프로프라이어터리
  코드와 모든 수치가 동치인지 여부, 독립 봉인 OOS 및 거래가능성은 미검증.
- A5 변경은 별도 research 브랜치에서만 유지. 운영 main/기존 +40 및
  Quant 주문·인증·G원장·sealed OOS는 변경하지 않음.

## 수식 참고
- https://harmonictrader.com/harmonicpatternorigin/
- https://harmonictrader.com/harmonic-patterns/butterfly-pattern/
- https://harmonictrader.com/harmonic-patterns/bat-pattern/
- https://harmonictrader.com/harmonic-patterns/crab-pattern/
