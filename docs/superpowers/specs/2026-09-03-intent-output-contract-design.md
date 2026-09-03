# ResearchIntent 출력 계약 고정 설계

## 목표

Codex가 반환하는 연구 의도를 Strategy IR에 안전하게 연결하고, JSON 문법은 맞지만
조건 위치에 `true`, `[true]`, 빈 객체가 들어가는 의미 오류와 반복 복구 지연을 차단한다.

## 범위

- `ResearchIntent`의 operation을 타입이 고정된 모델로 정의한다.
- 조건을 받는 operation은 `Condition` 객체만 허용한다.
- operation별 허용 대상과 값 타입을 Strategy IR 기준으로 검증한다.
- Codex 프롬프트와 JSON Schema를 canonical operation 계약에 맞춘다.
- 동일한 잘못된 복구 결과를 재호출하지 않고 오류 지식을 축적한다.
- 전략 아이디어의 선택 범위(인디케이터, 기간, 타임프레임, 외부 시계열, 위험 설정)는 제한하지 않는다.

## 설계

### 1. 계층별 책임

1. Codex는 전략 가설과 canonical operation을 반환한다.
2. Pydantic 모델은 필드·자료형·허용 operation을 검증한다.
3. Intent bridge는 부모 Strategy IR에서 대상 경로의 실제 타입과 등록 여부를 검증한다.
4. Mutation engine은 검증된 typed operation만 적용한다.
5. Research loop는 오류 코드와 payload signature를 기록하고 반복 복구를 차단한다.

### 2. Canonical operation

Codex 출력의 operation은 JSON Patch의 임의 `path/value` 조합이 아니라 다음 계약을 사용한다.

- `RETAIN`: 대상과 값 없음
- `SET_PARAMETER`: `path`와 scalar `value`
- `ADD_RULE`, `REPLACE_RULE`: `path`와 `condition`
- `ADD_REGIME_FILTER`: `condition`
- `REMOVE_RULE`, `REMOVE_FEATURE`, `REMOVE_INDICATOR`: `path`만 사용
- `CHANGE_AND_OR`: `path`와 `logic` 사용
- `ADD_FEATURE`: `path`와 typed `feature`

하위 호환을 위해 기존 JSON Patch 입력은 bridge에서 canonical operation으로 변환할 수
있지만, Codex에 제공하는 출력 schema는 canonical operation만 생성하도록 한다.

### 3. 타입·경로 검증

- `entry.conditions`, `exit.conditions`, `regime_filters`에 추가되는 값은 반드시 `Condition`이다.
- 조건 리스트의 인덱스는 정수이며, 리스트 전체 대상에 인덱스를 추가하지 않는다.
- indicator 기간은 양의 정수, risk parameter는 Strategy IR의 해당 필드 타입과 일치해야 한다.
- `ADD_FEATURE`는 등록된 feature와 유효한 `FeatureRef`만 허용한다.
- 오류는 안정적인 코드(`INTENT_VALUE_TYPE`, `INTENT_PATH_TARGET`,
  `INTENT_UNREGISTERED_FEATURE` 등)와 사람이 읽을 메시지를 함께 가진다.

### 4. 복구·기록

- 복구 agent에는 원본 payload 대신 오류 코드·허용 형태·필요한 대상 정보를 명시한다.
- 같은 오류 코드와 동일 payload signature가 반복되면 Codex를 다시 호출하지 않고 해당
  세대를 `FALLBACK` 처리한다.
- `state/system/repair-knowledge.jsonl`에 오류 signature, operation 위치, 해결 상태,
  소요 시간을 append-only로 기록한다.
- fallback은 부모 전략을 변경하지 않고 평가하며, 주문은 계속 비활성화한다.

## 검증

- malformed condition payload가 Pydantic/bridge 단계에서 거부되는 회귀 테스트
- 잘못된 `regime_filters.0` 경로가 거부되는 회귀 테스트
- canonical operation이 typed `MutationOperation`으로 변환되는 테스트
- 같은 복구 payload의 재호출 차단 테스트
- schema 파일과 모델 schema 일치 테스트
- 전체 pytest, Ruff, MyPy, diff 검사
