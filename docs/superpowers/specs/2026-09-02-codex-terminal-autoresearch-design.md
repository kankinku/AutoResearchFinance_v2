# Codex 전용 터미널·Autoresearch 설계

## 목표

저장소 루트에서 별도 터미널을 실행해 일반 Codex 질의응답과 전략 탐색·백테스트를
하나의 인터페이스로 사용한다. LLM 실행은 로컬 `codex exec`로 통일하고, 반복
연구는 Karpathy autoresearch의 “제안 → 고정 평가 → 개선 시 유지 → 실패 시 폐기”
흐름을 Quant Autoresearch Harness의 Strategy IR·불변 평가·Paper-only 경계에 맞춰
적용한다.

참조 원칙은 [karpathy/autoresearch](https://github.com/karpathy/autoresearch)의
`program.md` 기반 연구 지침, 단일 실험 예산, 결과 비교, 개선 후보 유지 흐름이다.
원본의 에이전트 직접 코드 수정과 무한 `NEVER STOP` 지시는 그대로 복사하지 않는다.

## 사용 모드

### 대화 모드

터미널은 일반 질문을 받아 `codex exec`를 호출하고 응답을 출력한다. 실행별
프롬프트·응답·상태는 민감정보를 제거한 로컬 세션 기록으로 보존한다. 한 회차의
실행은 타임아웃과 출력 크기 제한을 갖고, Codex 인증은 Codex CLI 자체 로그인만
사용한다.

### IR Autoresearch 모드

각 세대는 다음 순서로 실행한다.

1. 현재 Strategy IR, 최근 원장, Knowledge Memory, 평가 정책을 읽는다.
2. `codex exec`는 다음 연구 의도와 파라미터 탐색 방향만 제안한다.
3. 로컬 Mutation Engine이 검증된 Strategy IR 후보를 생성한다.
4. Docker 백테스트와 동일한 데이터·비용·워크포워드·위험·QQQ 비교를 실행한다.
5. 연도별 거래수가 30회 이하인 완료 연도가 하나라도 있으면 탈락시킨다.
6. 개선 여부를 독립 로컬 평가기가 판정하고 모든 후보를 원장에 기록한다.
7. 개선 후보는 Frontier 후보로 보존하고, 실패 후보는 폐기 또는 Rescue Pool로 보낸다.
8. Champion 승격과 실전·모의 주문은 이 터미널의 자동 동작에서 제외한다.

LLM은 Python·Lean·평가기·데이터·비용 모듈을 직접 생성하거나 수정하지 않는다.
Strategy IR이 유일한 전략 원천이며 생성 코드는 실행 산출물이다.

## 직접 수정 게이트

기본 모드는 IR Autoresearch이며 직접 파일 수정은 차단한다. 사용자가 명시적으로
직접 수정 모드를 선택할 때만 다음 이중 게이트를 통과한다.

```text
terminal --mode direct-edit --confirm-direct-edit --worktree <disposable-worktree>
```

직접 수정 모드의 규칙은 다음과 같다.

- 일회성 명령 플래그와 전용 disposable worktree가 모두 필요하다.
- 현재 checkout과 `main` 브랜치는 직접 수정하지 않는다.
- `core/data`, `core/backtest`, `core/evaluator`, `core/validation`,
  `core/costs`, `core/integrity`는 보호 경로로 차단한다.
- `.env`, 토큰, API 키, 계좌번호, KIS 주문·실전투자 모듈은 읽기·쓰기·프롬프트
  전달 대상에서 제외한다.
- 실행 전후 Git diff와 대상 경로를 기록하고, 보호 경로·민감 파일·심볼릭 링크
  탈출이 발견되면 전체 후보를 폐기한다.
- 수정 결과는 반드시 Strategy IR 정규화·검증과 동일 백테스트 게이트를 통과해야
  유지한다.
- 개선되지 않은 수정은 disposable worktree에서 폐기하며, 자동 Champion 승격은
  하지 않는다.

직접 수정 게이트는 “LLM이 평가기를 바꾸어 점수를 올리는” 경로를 열지 않는다.
허용 목적은 전략 작업 파일의 실험적 수정이며, 독립 평가기와 경로 검사가 최종
판정을 담당한다.

## 터미널 명령 인터페이스

실행 명령은 다음과 같다.

```powershell
python cli.py terminal
```

REPL 명령:

```text
/mode chat                    일반 질의응답
/mode autoresearch            IR 기반 자동 연구
/repeat 5 <질문>              일반 질의 5회 반복
/research 20                  자동 연구 20세대 실행
/backtest                     현재 승인 입력의 단일 백테스트
/status                       세션·반복·워커·Paper 상태 확인
/stop                         현재 회차 중지 및 안전한 상태 저장
/help                         사용법 표시
/exit                         터미널 종료
```

대화형 터미널 외에도 배치 실행을 제공한다.

```powershell
python cli.py terminal --mode autoresearch --iterations 20 --prompt "QQQ 안정성 전략 탐색"
python cli.py terminal --mode chat --iterations 5 --prompt "현재 원장 요약"
```

실제 무한 루프 옵션은 제공하지 않는다. 모든 자동 연구는 양의 세대 수, 회차별
타임아웃, 출력·자원 예산을 가져야 하며, `/stop`과 프로세스 중단으로 재개 가능한
상태를 남긴다. 장시간 실행은 사용자가 큰 유한 세대 수를 명시하는 방식으로
대체한다.

## 상태·기록

- `state/system/terminal.json`: 현재 모드, 실행 회차, 중지·실패 상태
- `state/system/autoresearch.json`: 세대별 연구 의도·후보·개선 판정 요약
- `state/test-records.jsonl`: 기존 상세 백테스트 원장과 연도별 지표
- `state/llm/status.json`: Codex CLI 호출 상태
- `state/llm/terminal-sessions.jsonl`: 민감정보 제거 대화 기록

모든 기록은 JSON/JSONL 원자·추가 방식으로 저장하며 API 키, APP Secret, 토큰,
계좌 식별자, 원시 시장 데이터는 기록하지 않는다.

## 오류와 중지

- Codex 실행 실패: 현재 회차를 `FAILED`로 기록하고 다음 회차로 자동 진행하지
  않으며 사용자의 재개 명령을 기다린다.
- 백테스트·평가 실패: 후보를 유효 성과로 취급하지 않고 `BLOCKED` 또는 `REJECT`로
  원장에 남긴다.
- 예산 초과·타임아웃: 워커를 중지하고 마지막 완료 세대까지 재개 가능하게 한다.
- 직접 수정 게이트 위반: 수정 결과를 폐기하고 위반 경로와 이유만 기록한다.
- 중지 요청: 현재 외부 주문은 없으므로 즉시 로컬 회차를 중지하되, 부분 결과는
  불완전 상태로 분리한다.

## 테스트와 수용 기준

- REPL 명령 파서가 chat/autoresearch/repeat/backtest/status/stop을 구분한다.
- `codex exec` 호출이 인증정보를 자식 환경과 프롬프트에 전달하지 않는다.
- 반복 횟수·타임아웃·출력 예산을 초과한 실행은 중지되고 재개 상태가 남는다.
- IR 모드가 LLM 제안을 로컬 Strategy IR 변이로만 연결한다.
- 직접 수정 모드가 명시적 이중 게이트 없이는 시작되지 않는다.
- 보호 경로·민감 파일·심볼릭 링크 탈출 diff는 차단된다.
- 결과 악화·평가 실패·연간 거래수 기준 미달 후보는 유지되지 않는다.
- 기존 전체 품질 검사와 Paper-only·MCP·백테스트 회귀 테스트가 모두 통과한다.
