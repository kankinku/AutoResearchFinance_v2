# MCP 우선 연구 실행 — 세대별 S7 자동 피드백 및 도구 갱신 진단

날짜: 2026-10-15. 기본 LLM은 기존 ChatGPT ↔ Quant AutoResearch MCP 연결이다. 사용자가 지정한 **기존 `https://project-moon.taild689f9.ts.net/quant/mcp` URL과 OAuth 인증을 유지**하면서 연구 세대 반복의 단계를 줄였다.

## 핵심 변경

기존에는 ChatGPT가 (1) `submit_algorithm_plan`, (2) `submit_algorithm_diagnosis`, (3) `evaluate_algorithm_experiments`를 별도로 호출해야 다음 세대가 실제 S7 통제 실험 결과를 참고할 수 있었다. (3)을 빠뜨리면 다음 세대 연구 컨텍스트에 미검증 가설만 전달되는 위험이 있었다.

새 기본 동작:

1. ChatGPT가 지표·조건·분기·가중치를 포함한 `AlgorithmPlan`을 제출한다 (`submit_algorithm_plan`). 서버는 기존 DEVELOPMENT 자료로 백테스트·거래 감사와 진단 입력을 반환한다.
2. ChatGPT가 **실제 진단 컨텍스트의 관측 ID와 손실 원인 가설**을 포함한 `DiagnosticResponse`를 제출한다 (`submit_algorithm_diagnosis`). 서버는 기존 해시 체인에 해당 세대를 커밋한다.
3. 같은 요청의 **서버 측 후처리**가 그 세대의 통제 실험을 실행·저장한다. S7의 기존 `evaluate_experiments` 멱등 계약을 재사용한다. `latest_controlled_experiments`와 `controlled_experiments_automatically_evaluated=true`를 응답에 포함하고, 다음 `model_context.research_direction`에 관측 결과를 반영하여 반환한다.
4. ChatGPT는 해당 응답만으로 다음 세대 Plan을 설계할 수 있다. `evaluate_algorithm_experiments` 도구는 **기존 보고서 조회·독립 재검증·재개 복구용**으로 그대로 남는다. 완료 세대까지 응답에 마지막 보고서를 포함한다.

**LLM 판단을 서버에서 대신하지 않는다.** 알고리즘 Plan과 원인 분석은 여전히 연결된 ChatGPT가 작성한다. 자동화되는 것은 이미 제안된 가설에 대한 백테스트와 원장 저장뿐이다. 이 결과는 개발 데이터 측정이며 인과 입증, OOS 통과, 실거래 수익 보장 또는 주문 실행이 아니다.

## 연구 원장·장애 복구

- 증거 비교는 원본 개발 구간/비용 모델/전략 지문에 고정되고 저장 시 기존 S7 체크섬을 유지한다.
- 기존 세대 원장은 변경하지 않고, 새 세대가 제출되었을 때만 S7 자동 비교가 발생한다.
- `submit_algorithm_diagnosis`의 **체크포인트는 단일 사용**이다. 동일 요청을 재호출하면 재진단이 아니라 토큰 오류가 발생한다. 통신 단절 시 `get_algorithm_research`로 현재 상태를 확인하고, 해당 세대의 보고서가 없는 경우 `evaluate_algorithm_experiments`를 멱등 재실행한 뒤 진행한다.
- S7 처리 자체가 실패하면 세대 커밋은 이미 완료됐을 수 있다. *이때 진단 요청을 무조건 다시 보내지 말고* 조회·복구 절차를 사용한다. 이 변경은 세대/실험 저장을 하나의 SQLite 트랜잭션으로 합친 것이 아니다.
- `AcademicCheckpointAutopilot` 또는 새 유료 API 실행 경로는 여전히 선택 사항. `OPENAI_API_KEY`가 존재하더라도 기본 MCP 모드는 변경되지 않는다.

## 클라이언트 MCP 도구 목록 불일치

- 운영 서버가 제공하는 **32개 MCP 도구**와 이 ChatGPT 대화에서 노출되는 도구가 다를 수 있다. 이 작업 시점 대화에서는 **18개만 직접 보였고, 학술 `start_algorithm_research`/`submit_algorithm_plan`/`submit_algorithm_diagnosis`가 누락됐다.** 이는 서버 `tools/list`와 클라이언트에 고정된 도구 스키마 간 차이로, 서버 코드만으로 ChatGPT의 기존 대화 도구 목록을 강제로 교체할 수 없다.
- 기존에 접근 가능한 `get_research_brief.mcp_capabilities.required_client_tools`에 해당 다섯 가지 학술 연구 필수 도구를 포함하고, `stale_client_hint`에서 **기존 연결의 도구 목록 새로고침 또는 새 대화에서 이미 연결된 앱 사용**을 안내하도록 했다. **MCP URL 재등록·앱 재설치·OAuth 키 회전은 요구하거나 수행하지 않는다.**
- 도구 스키마 노출 문제를 해결하기 전에는 이 특정 ChatGPT 대화에서 10세대 실제 모델 연구를 성공했다고 주장할 수 없다.

## 수락 검증 및 한계

- `test_mcp_first_two_call_research.py`: 실제 ChatGPT-facing MCP SDK `tools/list`와 `tools/call`을 통해 **2세대 각 Plan→Diagnosis 2회 제출**, S7 자동 저장 및 S8 다음 세대 피드백 전달을 검증한다. 결정론적 `ScriptedResearcher`를 사용하는 *MCP 프로토콜 및 연구 엔진 수락 테스트*이며, 실제 ChatGPT 모델의 원인 분석력·실전 수익성 시험은 아니다.
- 기존 MCP 툴 목록은 **32개 그대로**, URL/키/연구 데이터/서버 설정 변경 없음.
- 10세대 실제 외부 ChatGPT 모델이 능동적으로 다른 알고리즘을 구성·실험하고 그 결과를 유의미하게 개선하는 연구 실증은 **아직 미완료**다. 클라이언트 도구 새로고침 후 작은 단위(예: 2~3세대)부터 검증하고, 동일 평가 예산의 랜덤 기준선과 비교해야 한다.
