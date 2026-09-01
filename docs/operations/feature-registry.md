# Feature Registry 운영

## 원칙

Feature Registry는 LLM이 전략에서 선택할 수 있는 허용 후보 목록이다. 등록된 특성이 모든 전략에 자동으로 포함되거나 실전 주문에 사용되는 것은 아니다.

현재 기본 후보군에는 다음 계열이 있다.

- VIX 백분위
- 금·DXY 수익률
- QQQ·Nasdaq 수익률
- 미국·일본·한국 2년물·10년물 금리 변화
- MACD·ATR·ADX·Bollinger·거래량 돌파·52주 고점·변동성·국면

`python cli.py list-features`로 현재 등록된 후보와 입력 시계열, 계산기, lookback을 조회한다.

## 신규 특성 생명주기

```text
LLM FeatureProposal
  → FeatureSpec 검증
  → Codex Desktop 격리 구현
  → 단위·기준값·과거 데이터 테스트
  → 누수·정렬·결측·재현성·자원·보안 검사
  → implementation hash 부여
  → Registry REGISTERED
  → 전략 백테스트/Funnel/OOS 검증
```

다음 조건을 모두 통과하지 못한 특성은 등록하지 않는다.

- Schema
- 단위·기준값·과거 데이터 계산
- 미래 데이터 누수 방지
- 거래일·타임존·as-of 정렬
- 결측과 초기 lookback 처리
- 동일 입력 재현성
- 실행 시간·메모리 제한
- 임의 import·파일·네트워크·주문 API 차단

실패 제안은 격리 보관한다. 기존 Registry에 등록된 특성도 FeatureSpec 버전과 해시가 바뀌면 새로운 특성으로 취급한다.

## 금리와 외부 시계열

미국·일본·한국 2년물·10년물은 선택 가능한 후보다. 필수 입력은 없다. 데이터는 `SeriesObservation.available_at`이 신호 시각보다 늦지 않은 경우에만 as-of 정렬 결과에 포함한다. 발표·확정 시점이 불명확한 데이터는 사용하지 않고 명시적 결측으로 처리한다.

## 안전 경계

Registry 등록은 연구 허용 상태일 뿐이다. Champion 승격, 모의투자 승인, 실전 모드 선택, 실전 주문 승인은 각각 별도 단계다. 시스템 긴급 차단 장치는 FeatureSpec이나 LLM이 변경할 수 없다.
