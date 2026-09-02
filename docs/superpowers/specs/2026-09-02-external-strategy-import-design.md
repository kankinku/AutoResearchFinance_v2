# 외부 GitHub 전략 수집·정규화·중복 판정 설계

## 목표

외부 GitHub 저장소와 현재 보유한 KIS 전략을 안전하게 분석해 canonical Strategy IR로 변환하고, 중복 판정·백테스트 평가·수정 후보 생성·대시보드 표시까지 동일한 연구 파이프라인으로 연결한다.

## 범위

- GitHub URL을 임시 작업 디렉터리에 고정 커밋으로 clone
- 외부 Python/YAML/JSON/Pine 전략의 정적 구조 분석
- KIS `strategy_builder`의 `builder_state` 및 등록 메타데이터 변환
- KIS 백테스터 `StrategyDefinition` 빌더의 정적 설정 변환
- 정규화된 전략의 provenance, 의미 지문, 중복 그룹, 변환 상태 저장
- 기존 KIS 전략 10개를 동일한 변환·중복·평가 절차로 처리
- 백테스트 가능한 전략만 평가 파이프라인에 전달
- 표현 불가능한 전략도 원본 해시와 사유를 포함한 `REVIEW_REQUIRED`로 보존
- 전략 카탈로그 API와 대시보드 표시

## 제외 범위

- 외부 저장소 Python 코드의 import 또는 실행
- 실전 주문 및 모의투자 주문
- 외부 저장소의 API 키, 계좌정보, `.env`, 세션 로그 저장
- 자동으로 외부 전략을 Champion으로 승격

## 핵심 설계

### 입력 및 격리

`GitHubSource`는 URL, 브랜치 또는 커밋을 받고 임시 디렉터리에 clone한다. clone 후 실제 HEAD 커밋을 기록하고, 허용된 확장자만 읽는다. 분석기는 파일을 실행하지 않으며 Python은 AST와 제한된 리터럴 평가만 사용한다.

### 공통 분석 결과

모든 분석기는 다음 결과를 반환한다.

- source URL, commit, relative path, SHA-256
- detected format과 analyzer version
- `NORMALIZED`, `DUPLICATE`, `REVIEW_REQUIRED`, `UNSUPPORTED` 중 하나
- 변환된 `StrategyIR` 또는 안전하게 보존된 extracted profile
- 의미 지문과 중복 근거
- 평가 가능 여부와 사유

### KIS 변환

KIS 전략의 등록 이름, 패밀리, `builder_state`, 상수 파라미터, 지표·조건·위험 설정을 Strategy IR의 indicators, entry, exit, risk로 매핑한다. `get_custom_lean_code`처럼 정적 IR로 표현할 수 없는 동작은 원본을 실행하지 않고 `REVIEW_REQUIRED`로 보존한다.

### 중복 판정

원본 해시와 별도로 다음의 정렬·정규화된 의미 구조를 해싱한다.

```text
market scope + feature series + indicator type/period/timeframe
+ entry/exit normalized expression + risk + benchmark metadata
```

의미 지문이 같으면 완전 중복, 핵심 신호가 같고 위험 설정만 다르면 부분 중복, 둘 다 다르면 신규로 분류한다. 중복 결과는 카탈로그에 남기며 원본 파일을 삭제하지 않는다.

### 저장 및 평가 흐름

```text
clone/cache
  -> static analysis
  -> imported profile
  -> normalized Strategy IR
  -> duplicate classification
  -> backtest evaluation
  -> candidate/frontier record
  -> dashboard catalog
```

`import-strategy`는 더 이상 출력만 하지 않고 원자적으로 imported/normalized 기록을 저장한다. 단, 평가와 승격은 별도 명령으로 수행한다.

### 대시보드

기존 feature catalog와 분리된 `/api/strategies/catalog`를 제공한다. UI는 전략별 원본, 변환 상태, 중복 상태, 평가 상태, 수익률, Nasdaq 초과수익, 검토 사유를 표시한다.

## 오류 처리 및 안전성

- clone 실패: 저장소를 등록하지 않고 오류 코드와 sanitized reason 반환
- 허용되지 않은 파일: 건너뛰되 전체 가져오기 결과에 제외 사유와 개수 기록
- AST 해석 실패: `REVIEW_REQUIRED`로 원본 해시와 오류 유형만 저장
- IR 검증 실패: `UNSUPPORTED`가 아닌 변환 실패 상태로 보존
- 비밀정보 탐지: 값은 출력·저장하지 않고 파일 경로와 패턴 종류만 기록
- 외부 코드는 절대 실행하지 않음
- 현재 모드 설정과 관계없이 이 경로는 주문 API를 호출하지 않음

## 검증 기준

1. KIS builder preset 10개가 모두 같은 importer 경로를 통과한다.
2. KIS backtester preset은 지원 가능한 전략은 IR로 변환하고, 불가능한 custom 동작은 `REVIEW_REQUIRED`로 보존한다.
3. 동일 전략을 두 번 가져오면 원본 해시와 의미 중복이 구분된다.
4. 다른 원본 파일의 같은 SMA crossover는 완전 중복으로 판정된다.
5. 동적 Python 코드는 실행되지 않는다.
6. 가져오기 결과가 `strategies/imported`, `strategies/normalized` 및 전략 카탈로그에서 확인된다.
7. 대시보드 API가 정상·중복·검토필요 전략을 모두 반환한다.
8. 백테스트 결과가 없는 전략은 Champion으로 표시되지 않는다.
9. 기존 회귀 테스트와 lint/type checks를 통과한다.

