# T4 — 32세대 대기와 31세대 중복 신호 오류 분석 및 사전 검증 개선

점검일: 2026-10-16 KST, 기존 20문답·확정 순서 불변. 기존 100세대 연구 세션 `a84a100b15a242269b554282b01d91c9`.

## 현 상태 및 대시보드 진위
- Quant MCP 직접 상태 `32/100, status=AWAITING_PROVIDER, checkpoint_phase=AWAITING_PLAN, error_type=null, orders_enabled=false`.
- 운영 대시보드 `127.0.0.1:8081/api/academic/overview` HTTP 200, 실제 32/100, `AWAITING_PLAN`, S7 미측정 0. Nginx Windows 연결 포트 2999 유지.
- 백엔드 서버와 대시보드가 고장 난 것은 아니다. **현재는 모델이 다음 33세대 계획을 제출하지 않아 대기 중**이다. 운영 `authenticated_chatgpt_mcp_client`에는 실제 사용자 채팅 종료 후 모델을 스스로 재호출할 수 있는 독립 상주 provider/worker가 없어, 계획 대기를 오류 복구만으로 자동 진행할 수 없다.

## 31세대 과거 CycleStateError 사후 원인 재현
- 당시 첫 제출 계획 `t4_100_g031_sma_regime_confirm_breakout`은 모델·데이터 원장에 새 세대로 커밋되지 않았고, 진단 제출 직후 `CycleStateError`로 실제 `INTERRUPTED`에 빠졌던 기록이 있다.
- 동일 계획을 과거 원본 데이터·S6 카탈로그의 **임시 복제본**에서 재컴파일하고, 기존 연구 원장 32개 세대의 semantic/effective hash와 대조함. 결과:
  - `algorithm_semantic_hash = fdd9da71bfa442dac7b972e3ffff2ad882df1f157338ebd3e8045e6d0f573384` → 기존 세대 **일치 없음**.
  - `effective_signal_hash = bd707a4ccd066294cd168c5bc6d4099b99e5ead09a5af82f13a66bc05748daa1` → **11세대 `t4_100_g011_sma_regime_low_churn`과 동일**. 즉 구조/라벨이 다르더라도 개발 데이터의 진입/레짐 시계열이 동일해 본래 보안·품질 게이트가 중복을 검출한 사례다.
- 코드 경로: `AcademicMCPCheckpointService.submit_plan`은 계획 검증/백테스트 후 `AWAITING_DIAGNOSIS`로 stage를 이동하지만 기존 `AcademicCycleService._execute_claimed`는 **진단 제출 뒤**에서야 세대 중복 검사를 시행. 이때 `CycleStateError`가 gateway와 cycle 상태를 `INTERRUPTED`로 만든다. 이는 새로운 LLM 제안을 다시 받으면 해결되는 데이터 품질 오류이므로 **전체 연구 중단 시점이 늦은 것**이다.

## 구현된 수정 (개발 브랜치)
- `application/academic_checkpoint_service.py`: **기존과 동일한 semantic hash/effective entry+regime hash**를 `submit_plan`에서 계산, 원본 S6 개발 데이터와 이미 검증한 전체 history의 해시와 비교. 중복시 `ValueError:DUPLICATE_SEMANTIC_PLAN` 또는 `DUPLICATE_EFFECTIVE_SIGNALS`로 구체적인 기존 세대 번호를 반환하면서 **같은 `AWAITING_PLAN` 및 checkpoint token 유지**, 새 모델 계획 제출 가능. 시간 순 중복 검사는 기존 `cycle.advance`에도 그대로 유지(이중 방어).
- 만일 무결성 파손·권한 위반·실행 중 중복 접근이라면 기존 안전 차단 정책은 완화하지 않음. OpenAI 호스트 도구 안전 검사 거부도 재제출로 우회하지 않음.
- 신규 `tests/integrations/test_academic_mcp_duplicate_preflight.py`: 실제 MCP typed Plan/diagnosis/S7 경로를 통해 중복 구조·중복 실질 신호 사전 거부→세션/토큰/기존 증거 불변→같은 토큰으로 다른 알고리즘 2세대 정상 완료를 검증.
- **Red/Green 회귀**: 수정 전 신규 첫 테스트 FAIL(중복이 사전 거부되지 않음), 수정 후 신규 2 PASS, MCP 통합·replay·recovery·autopilot·범위 잠금 총 **43 PASS**, Ruff·Mypy PASS.
- 코드 커밋 `58cd079`; 브랜치 `feat/t4-preflight-duplicate-no-interrupt-20261016`. 운영 runtime 고정 소스 `b50b4c7`과 신규 변경 파일 차이는 정확히 사전 검증 27줄.

## 문제를 완전히 해결하려면
1. T4 운영에 이 사전 검증 버전만 안전하게 배포하고 원래 도구 32개·MCP 주소/OAuth·주문 OFF 및 32세대 증거를 확인해야 실제 서비스의 중복 전략 오류가 `INTERRUPTED`를 야기하지 않게 된다.
2. **지속 연구 실행기**는 별도 결손: 사용자 승인된 LLM 호출 주체/비용·세대 예산, 세대별 GPT Plan→진단→S7, 실패 타입 분류, heartbeat, DB 체크포인트 보존, 모델 호출 및 정책 거부 처리, 실행/중지 제어를 설계·운영 배포해야 한다. 단순 모니터 폴링/일시 통신 재시도만으로는 자동으로 새로운 GPT 계획을 만들 수 없다.
3. 재개 정책: `AWAITING_PLAN` 정상 대기는 모델 입력을 기다리기. 중복/스키마 후보는 token 유지한 채 LLM 재생성(회수 제한), transient 네트워크 오류는 상태 재조회 후 제한 재시도, API 안전 거부/해시 불일치/인증 실패는 승인·수동 점검 전 재개 금지, 실제 `INTERRUPTED` 시 evidence/recovery receipt 확인 후 공식 resume.
4. 실거래 주문 비활성, 독립 PIT/OOS 미승인, 과거 QQQ 개발 백테스트를 실제 순수익 검증이라고 주장하지 않음.

## 운영 배포 검증 — T4 중복 후보 사전검사 적용됨

- 운영 런타임 원본 `b50b4c7`에서 **사전검사 코드 27줄/회귀 테스트 2개만** cherry-pick한 최소 배포 브랜치 `deploy/quant-t4-duplicate-preflight-20261016`, 고정 commit **`2622f14`**. 런타임 경로 `/shared/moon-workspace/AutoResearchFinance_v2-quant-mcp-runtime-t4-preflight`. 기존 런타임 `b50b4c7`은 삭제하지 않아 롤백 가능.
- 배포 고정 워크트리 기준 회귀 39 PASS, Ruff PASS, Mypy PASS. 원 개발 브랜치 회귀 43 PASS.
- 운영 전 안전 점검: 기존 연구 세션 정확히 **32/100, AWAITING_PLAN**, 다른 실행 세션 EXECUTING 0, 기존 MCP 익명 401, Moon /health 200, 구 프로세스/경로/배포 인자 확인.
- 동일 MCP 주소/URL, OAuth 승인키 파일, project-root/state-dir/포트 8787을 유지한 채 기존 프로세스 정상 종료→변경된 고정 소스로 재시작. 백엔드 익명 /mcp 401 및 Nginx Quant /quant/mcp 401·Moon /health 200 확인. 운영 PID 9958.
- **재시작 후 실제 연결된 Qaunt Autoresearch MCP 32개 도구 그대로 접근 가능, `get_workspace_status` READY, orders_enabled=false**, `get_algorithm_research` 32/100, AWAITING_PLAN, 기존 마지막 원장 SHA 유지. 연구 모니터 8081과 8082 기존 프로세스 모두 HTTP 200/32세대/S7 미측정0/주문OFF.
- **한계:** 실제 운영 세션에 고의 중복 전략을 제출해 중단 위험을 발생시키지는 않았다. 운영과 동일 소스/검증 정책을 가진 격리 테스트에서 중복후 체크포인트/이력/토큰 보존을 확인했다. 설치로 입력 대기 상태 자체가 없어지지는 않으며, ChatGPT MCP의 외부 모델 호출이 제공되지 않으면 33~100세대는 자동 진행하지 않는다. 정책 거부/원장 해시 실패 역시 자동 재실행 금지.
