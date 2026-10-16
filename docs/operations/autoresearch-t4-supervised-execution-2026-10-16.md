# T4 / 4단계 — 지속형 연구 실행 소유권·일시정지·Heartbeat (2026-10-16)

## 목적 및 보존 기준

초기 20문답 연구 범위, 기존 MCP URL/OAuth/32개 도구, 100세대 세션 `a84a100b15a242269b554282b01d91c9`, 이미 확정된 32세대/S7 증거, 실거래 주문 비활성, PIT/OOS 승인 절차는 불변.

현재 Moon 연구 MCP의 기본 모델은 **채팅에 연결된 ChatGPT**이다. 컨테이너에서 채팅 자체를 재호출할 수 없으며, 명시적인 API/모델/키 승인 없이 무인 연구를 시작하면 안 된다. 따라서 이번 단계는 **유효한 공급자가 명시적으로 주어진 경우에만 전경에서 실행 가능한 제어 계층**을 구현하고, MCP 기본 모드는 사용법 안내만 하도록 유지한다.

## 구현된 기능

- `research/llm/supervised_checkpoint_runner.py`의 `ResearchRunSupervisor`: 세션별 owner-only(0700) 제어 폴더, 잠금파일을 이용한 비차단 실행 소유권, 원자적(0600) 상태/제어 기록. 기존 `runtime.lifecycle_lock`을 재사용해 중복 전경 실행을 거부한다. 정상 프로세스 종료 시 OS가 락을 해제하므로 강제 종료에도 세션 원장은 보존된다.
- 상태: `RUNNING`, `PAUSED`, `STOPPED`, `AWAITING_PROVIDER`, `COMPLETED`, `REVIEW_REQUIRED`를 구분. **실제 연구 원장의 `AWAITING_PLAN`/진단 대기와 별도의 제어 상태**이다.
- Heartbeat는 실행 중에만 별도 스레드가 파일을 원자 갱신한다. 오래된 `RUNNING` 기록은 `STALE_OR_UNVERIFIED`로 표시하고 실행 중이라는 주장을 금지. 최신 기록도 `RECENT_UNVERIFIED`로 표현해 세대 전진이나 도구 승인 성공의 증거와 혼동하지 않는다.
- `scripts/control_academic_research.py`에서 요청: `status`, `pause`, `stop`, `resume`. **`resume`은 요청 상태를 RUN으로 바꾸는 것뿐**이며 GPT 호출/별도 daemon 시작 아님.
- 명시적인 전경 실행 `scripts/run_academic_autopilot.py --execution-mode openai-api --model <explicit> --session-id ... --max-generations-this-call ...`은 상위 Supervisor에 접속한 `run_resumable`을 사용하도록 연결. 기존 기본 MCP 모드에서는 모델 호출/세션 생성 없음. API 모드는 기존과 동일하게 `OPENAI_API_KEY`와 모델 ID가 명시적으로 필요한 opt-in.
- `GuardedProvider`: GPT 새 호출 **전후**에 pause/stop 요청 검사. 모델 호출 중 stop 발생 시 새 계획을 제출하지 않고 종료; 계획은 이미 저장됐지만 진단 전 stop이면 `AWAITING_DIAGNOSIS` 체크포인트를 보존해 별도 재개 시 진단만 수행. 이 요청은 일반 복구 오류와 구분하여 재시도하지 않는다.
- `SafeCheckpointRecoveryController`는 `OperatorPauseRequested`를 정책/해시 거부로 오판해 무한 재시도하지 않고 그대로 상위 실행기에 전달. 원래 retry allowlist 및 정책 HOLD 유지.

## 시험 시나리오

- 실제 MCP 서비스의 격리 테스트 데이터로 지정 세대만 완료하고 S7 원장 해시 일치 확인.
- 모델 응답 중 PAUSE 요청 → 아직 커밋되지 않은 계획은 전혀 제출하지 않음. 사용자 RESUME 요청만으로 새 실행기는 출범하지 않음.
- 계획 제출 후 진단 응답 중 STOP → 원래 checkpoint 유지, 다음 명시적 전경 실행에서 진단만 수행(완료 세대 중복 없음).
- 동시 실행 두 번째 소유권 거부, 첫 실행 중 heartbeat 갱신, 비정상 종료된 오래된 RUNNING 상태는 STALE 표기.
- 공급자가 없거나 경로가 불안전하고 제어 파일이 symlink면 실행 거부. 임의 문자열로 안전 정책 우회 불가.

## 현재 제한과 다음 작업

이 릴리스는 지속 GPT 무인 워커를 임의로 실행하지 않는다. **상태 파일이 실시간으로 갱신되어도 모델 호출 주체가 없다면 33세대로 자동 진행되지 않는다**. 사용자 승인된 모델 공급자 선택·비용 상한·운영 배포 후 기존 세션의 다음 33세대 연구를 개시할 수 있다. 기존 100세대 개발 수익률은 NON-PIT/비독립 OOS이며 투자 성과 입증이 아니다.

현재 증거: 마지막 API/모니터 기준 32/100, AWAITING_PLAN, S7 누락 0, orders_enabled=false. 개발판 검증 결과와 GitHub commit/배포 상태는 작업 종료 보고에서 따로 명시.
