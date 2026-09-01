# Feature Registry 운영

## 원칙

Feature Registry는 LLM이 전략에서 선택할 수 있는 허용 후보 목록이다. 등록된 특성이 모든 전략에 자동으로 포함되거나 실전 주문에 사용되는 것은 아니다.

현재 기본 후보군에는 다음 계열이 있다.

- VIX 백분위
- 금·DXY 수익률
- QQQ·Nasdaq 수익률
- 미국·일본·한국 2년물·10년물·20년물 금리 변화
- MACD·ATR·ADX·Bollinger·거래량 돌파·52주 고점·변동성·국면

`python cli.py list-features`로 현재 등록된 후보와 입력 시계열, 계산기, lookback을 조회한다.
외부 저장소 전체 인벤토리는 대시보드의 `인디케이터 카탈로그`에서 확인한다. 상태가
`REGISTERED`인 항목만 전략 계산에 사용할 수 있으며, `PROPOSED`는 출처와 이름은
확인됐지만 기준값·누수·결측·자원 검증이 끝나지 않은 항목이다.

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

미국·일본·한국의 2년물·10년물·20년물은 선택 가능한 후보이다. 필수 입력은 없다. 모든 시계열은 동일한 변환 경로를 사용하므로 `US20Y.close@1w:rsi(period=14)`처럼 주봉 RSI도 구성할 수 있다. 지원 시간봉은 `1m`, `5m`, `15m`, `1h`, `1d`, `1w`, `1mo`이다.

데이터는 `SeriesObservation.available_at`이 신호 시각보다 늦지 않은 경우에만 as-of 정렬 결과에 포함한다. 발표·확정 시점이 불명확한 데이터는 사용하지 않고 명시적 결측으로 처리한다.

## 외부 저장소 통합과 중복

`pyindicators`, `srl-python-indicators`, `CentaurTechnicalIndicators-Python`, `pythonpine`의 지표는 함수명이 아니라 입력·계산식·파라미터·출력·워밍업·결측 정책으로 중복을 판정한다. 같은 계산식은 하나의 canonical FeatureSpec과 여러 alias로 관리하고, Wilder/EMA처럼 계산 방식이 다른 경우에는 별도 variant로 남긴다.

저장소의 시각화·다운로더·계좌·주문·네트워크 함수는 Feature Registry에 등록하지 않는다. 프로파일·TPO·틱 오더플로우는 해당 데이터 계약을 제공한 경우에만 계산한다. `pythonpine`은 저장소 LICENSE 기준 AGPL-3.0으로 취급하며 원본 코드를 제품에 복사하지 않고 독립 재구현한다.

## 안전 경계

Registry 등록은 연구 허용 상태일 뿐이다. Champion 승격, 모의투자 승인, 실전 모드 선택, 실전 주문 승인은 각각 별도 단계다. 시스템 긴급 차단 장치는 FeatureSpec이나 LLM이 변경할 수 없다.
