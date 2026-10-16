# T4 — 기본 MCP 실행 준비 점검·모델 호출 상한 (2026-10-16)

## 목적과 제품 경계

- 고정 작업: **T4/S4·S5 1단계 실행 연결 준비**. 대응 사용자 20문답 Q02/Q06/Q08/Q15/Q17/Q20. 목표는 자율 연구의 운영 안전장치와 연구 세션 연속성을 강화하는 것. 다음 작업은 기존 세션 35~100세대 T4 검증이다.
- 운영 기본 `authenticated_chatgpt_mcp_client` / 기존 URL·OAuth·32도구 / 100세대 세션 / S7·원본 가격 / 주문 OFF / 개발 NON-PIT·독립 OOS 비승인 **불변**.
- **중요한 미해결 의존성:** 현재 MCP 연결은 ChatGPT 클라이언트가 계획·진단을 제출하는 요청-응답 구조다. Moon 서버는 ChatGPT 대화를 능동적으로 시작하거나 대화 종료 후 이어서 호출할 권한·인터페이스가 없다. 이 작업만으로 *무인 GPT 실행기가 연결되었다고 주장할 수 없다*. 미승인 별도 유료 모델 API, 주기 작업, 백그라운드 데몬 자동 실행은 하지 않는다.

## 작업 내용

1. `scripts/run_academic_autopilot.py`의 기본 MCP 모드에 기존 `--session-id`를 지정하면, **read-only AcademicMonitorReader**로 기존 DB의 34/100, 체크포인트 단계, S7 누락 개수 및 다음 MCP 도구 이름을 조회한다. 토큰·모델 문맥·개별 거래/원본 시세·키를 출력하지 않는다. 서버 호출·신규 세션·모델 호출은 **0건**이다. DB 누락·불일치에는 `RESEARCH_STATE_UNAVAILABLE`(fail closed)로 표시한다. 기존 세션을 선택했을 때 새 `start_algorithm_research`를 실행하라는 잘못된 안내도 막는다.
2. `ResearchRunSupervisor`에 **전경 실행 1회당 외부 모델 제안 최대 횟수** `max_model_proposals`를 추가. 지정 한도(1~1000)를 넘기 직전 호출을 중지해 `PAUSED`/`MODEL_PROPOSAL_BUDGET_REACHED`로 반환한다. 이미 제출한 Plan과 완료 세대는 그대로 두며 별도 명시적 전경 호출에서 기존 `AWAITING_DIAGNOSIS`부터 이어간다. 디폴트도 한정 세대당 최대 5회(중복 재제안 포함)로 제한한다. 이 제한은 **모델 호출 횟수** 상한이며 달러 비용·입력 토큰 예산 승인/정산은 아니다.
3. 선택형 `--execution-mode openai-api`에는 명시 `--model`, `OPENAI_API_KEY`와 **`--max-model-proposals`**가 모두 필요하도록 강화. 기본 `mcp` 경로는 기존대로 키가 있더라도 API 호출/유료 모드 전환을 하지 않는다. 별도 API를 실제로 기동하지 않았다.
4. 단일 소유권 락, PAUSE/STOP/RESUME, heartbeat, 모델 응답 시점 중지 검사, 오류/중복 안전 복구 및 원장/S7 해시 검증을 종전 구현 그대로 유지한다.

## 수락 기준과 테스트 계획

- T0: 예산 한도 1회를 끝내면 PLAN만 staged, 진단은 전송되지 않고 연구원장 0세대를 유지. 두 번째 **명시적** 호출은 진단 단계에서 이어서 1세대 커밋한다. 잘못된 예산 값은 GPT 호출 전에 거부한다.
- T1: MCP 기본 모드에서 환경에 별도 API 키가 있어도 신규 모델/API 호출·새 DB가 생기지 않고, 불가한 세션 상태를 예측하지 않는다. 명시 API 모드의 예산 누락은 HTTP 요청 전에 거부한다. 기존 MCP 계약·T4 supervisor·autopilot·거버넌스 테스트와 Ruff/Mypy·diff 점검.
- T2/T3: 운영 재배포 전 전수 회귀·기존 URL/OAuth/세션 복구·실패 예산 리허설. 이 작업은 별도 운영 배포 없이 개발 브랜치에서만 수행.
- T4: **실제 연결 ChatGPT**로 남은 35~100 세대를 이어갈 실행 호스트/권한 승인·지속 구동을 별도로 확보한 뒤 100세대 원장 및 동예산 random 비교 확인. 그 전에는 `PROVIDER_REQUIRED`.
- T5/T6: 이후 공급자 PIT·독립 OOS, paper-only 및 GO/NO-GO 평가. 별도 승인 전 실거래·봉인 OOS 사용 금지.

## 운영 확인 및 남은 외부 조건

- 기존 실제 연구는 34/100 `AWAITING_PLAN`, S7 누락 0, 실거래 OFF. 읽기 전용 CLI가 같은 상태를 출력하는지 확인한다.
- 연결된 ChatGPT 클라이언트가 앱/대화 밖에서 계속 호출될 공식 승인된 실행 인터페이스가 **없다**. 이 제약은 프로세스 supervisor나 MCP 상태 점검만으로 해소되지 않는다. 다음 T4 실행 설계는 기존 MCP 연결을 유지하는 ChatGPT 측 실행 주체가 필요하며, 별도 API 모드 변경은 사용자 승인/비용 상한을 먼저 확인해야 한다.
