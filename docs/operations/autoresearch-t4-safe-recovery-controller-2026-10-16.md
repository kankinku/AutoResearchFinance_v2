# Quant Autoresearch — T4 안전한 오류 분류·자동 복구 제어기 (2026-10-16)

원본 20문답 확정 문서: [Scope Lock v1](../decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md). 대응 Q02/Q06/Q08/Q15/Q17/Q20, 현재 동일 T4 단계. 초기 인터뷰와 연구 목표·순서는 변경하지 않았다.

## 1. 12세대 차단 실증과 확인 가능한 원인

- 인증된 Quant MCP에서 기존 세션 `a84a100b15a242269b554282b01d91c9`은 **11/100 완료**, 제12세대 `t4_100_g012_risk_persistence`는 **AWAITING_DIAGNOSIS**. 계획 백테스트 결과 존재, 진단/S7 커밋 미완료, 주문 비활성.
- 당시 `submit_algorithm_diagnosis` 호출이 OpenAI 호스트의 안전 검사에서 거부됐다. 서버 gateway에 열두 번째 진단 완료 receipt가 없고, staged plan/context 해시가 그대로이므로 **해당 도구 호출이 Moon 서비스 코드까지 전달됐다는 증거가 없다**.
- 동일 턴에 무해한 Git 브랜치 생성 명령 또한 유사 검사로 거부된 적이 있으므로, 특정 투자 알고리즘·가설 문구 때문에 거부됐다고 단정할 수 없다. **OpenAI 측 내부 거부 규칙/정확한 근본 트리거는 확인 불가**. Moon 서버의 StrategyIR·진단 형식 오류로 단정하거나 안전 검사를 우회하지 않는다.
- 운영 Quant 서버 코드 `b50b4c7`, 기존 MCP 주소 `https://project-moon.taild689f9.ts.net/quant/mcp`, OAuth·원장·봉인 OOS·실주문 disabled는 이번 개선에서 변경하지 않는다.

## 2. 구현한 범위 제한 복구 제어기

- 신규 `research/llm/safe_checkpoint_recovery.py`:
  - **명시적 타입 분류만**: `TransientProviderFailure` = 일시적 송수신 실패, `pydantic.ValidationError` = typed 모델 출력 수리, `ProviderPolicyRefusal` 및 `PermissionError` = 정책 거부, 기타 알 수 없는 예외 = fail-closed, checkpoint/integrity 예외 = fail-closed.
  - **복구 상한**: transient 최대 2회(최초 시도 외), 모델 입력/schema 수정은 최대 1회(최초 외). 모든 재시도 전에 canonical `get_algorithm_research`에 준하는 서비스 상태 재조회: session·데이터 해시·완료 세대·과거 evidence prefix·주문 OFF·개봉 OOS 거부·기존 stage 확인. 서버가 이미 세대를 커밋했는데 응답만 끊기면 세대를 **중복 실행하지 않고** 다음 checkpoint에서 재개한다.
  - 후속 생성/진단은 기존 `AcademicCheckpointAutopilot`과 `AlgorithmPlan`/`DiagnosticResponse`/MCP DB CAS 및 S7 증빙 경계를 그대로 따른다. 다른 endpoint, 비승인 HTTP, 외부 모델 API, 허위 GPT 가설/대체 모델 사용·실거래/호가 제출 금지.
  - 오류를 발생시킨 요청의 원문, OAuth secret, checkpoint token을 기록하지 않고 분류 코드·단계·완료 세대 수·해시 식별자/시각만 **권한 0600의 로컬 JSONL 로그**로 기록한다. 로그는 기록용(보호 데이터의 공식 hash chain 또는 서명된 감사원장이라고 주장하지 않음).
  - 안전 정책 거부·무결성 불일치·오류 종류 불명은 `ResearchReviewRequired` 발생, **자동 승인/자동 재전송 하지 않음**. 로그 기록과 상태 진단 후 독립적으로 허용된 요청이 있을 때만 원래 세션에서 재개 가능.
- 기존 `research/llm/checkpoint_autopilot.py`에 **명시적으로 호출하는** `run_resumable(session_id, max_generations, audit_path)` 진입점을 추가. 비동기 백그라운드 프로세스·상시 재시도·MCP 자동 등록/재등록은 없다. 이미 존재하는 explicit foreground loop를 재사용한다.
- **호스트 측 정책 거부의 기술적 한계**: ChatGPT가 MCP 요청을 전달하기 *전에* 거부한 호출은 Moon 프로세스에 예외 이벤트조차 전달되지 않는다. 위 controller는 그런 요청을 스스로 감지하여 무조건 재시작하는 daemon이 아니다. 허용된 상위 계층이 정책/승인 상태를 확인해 호출할 경우에만 이 기능을 활용할 수 있다. 정책 거부를 재시도로 무력화하는 기능은 구현하지 않았다.

## 3. 실제 검증과 한계

- 타입별 오류 주입 시나리오: 첫 계획 전 일시적 오류·계획 보존 후 첫 진단 오류·정책/권한 거부·정의 불명 오류·재시도 상한·pydantic schema 수정·의도치 않은 입력 문자열로 분류 변경 불가·이미 3세대 커밋한 뒤 통신 오류·응답 유실(서버는 이미 커밋)·외부 `run_resumable` 진입점.
- 중복 알고리즘에 대한 본래 엔진의 보안/품질 게이트는 완화하지 않았다. 회귀 테스트의 mock 계획 생성기 자체가 중복 전략을 낸 오류를 발견하여 **서로 다른 계획을 생성하는 기존 테스트 전용 provider**로 교체했다.
- 이번 검사: 새 컨트롤러 단위/통합 12 PASS, 관련 실제 MCP/Autopilot/복구/범위잠금 포함 **53 PASS**(추가 entrypoint 검사 재실행 결과별도 확인); Ruff·Mypy(변경 두 소스) PASS. 전체 저장소 T3=1655는 이전 배포 당시 결과이며 이 변경 뒤 **미재실행**.
- 서버의 외부 호스트 안전 판단 이유를 알아냈다고 주장하지 않으며, 정책 거부 후 실제 연결된 12세대 진단을 우회해 커밋하는 실험은 하지 않았다. 따라서 **100세대 11/100 / G012 AWAITING_DIAGNOSIS 유지**, 실제 GPT 100세대 완료/PIT/OOS/순수익/승인되지 않은 주문 실행과 무관.

## 4. 적용과 다음 순서

이 코드는 **개발 브랜치 한정**. 기존 Quant MCP 운영 32개 도구·URL/OAuth에 임의 새 엔드포인트를 추가하지 않았다. 실제 GPT MCP 호스트 호출을 가로채는 기능은 아니며, 이미 제공된 checkpointed foreground-loop를 이용할 수 있는 승인된 모델 transport의 호출자로 연결해야 자동 복구가 작동한다.

다음은 **T4 동일 단계**에서 이 controller의 배포 승인·운영 측 연계 지원 여부 확인, 호스트 정책 거부 원인에 대한 정상 검토 경로 확보, 기존 동일 세션의 G012 진단을 허용되는 정상 도구에서 커밋/S7 검증한 뒤 13~100 계속. 차단 시에는 기존 checkpoint를 보존하고 실패를 숨기지 않는다.
