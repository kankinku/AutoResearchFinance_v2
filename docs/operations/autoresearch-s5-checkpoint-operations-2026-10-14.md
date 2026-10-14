# S5 1차 — 기존 Quant MCP의 중단·재개·최종 요약·체크포인트 복구

작성일: 2026-10-14. 20문답 15~17·20번 요구 중 **명령형 세대 실행 중단·복구 및 완료 후 요약 보고**를 먼저 구현한다. [전체 로드맵](autoresearch-implementation-roadmap-2026-10-14.md) 및 [S4 기존 URL 보존](autoresearch-s4-mcp-bridge-stable-url-2026-10-14.md)을 준수한다.

## 추가 구현

- `AcademicCycleService.cancel`: `AWAITING_PROVIDER` 또는 `INTERRUPTED` 상태에서만 취소한다. 완료된 세대와 감사 해시·성과를 그대로 보존하고 세션을 `CANCELLED`로 고정한다. 실행 중인 세대를 임의로 강제 종료하는 방식이 아니므로 동시 실행·원장 무결성을 훼손하지 않는다.
- `AcademicCycleService._final_report`: `COMPLETED` 또는 `CANCELLED` 상태에서만 짧은 결과 요약 생성. 완료/요청 세대, 최초/마지막/개발 구간 최고 누적 수익률, 마지막 MDD, 관측 체결과 제안 가설 수 등 **실측된 값**을 출력한다. 가설 **실험·인과 검증 건수는 아직 0**, 독립 수익 검증/실제 모델 자율성 검증은 `false`로 표시한다.
- `AcademicCycleService.interrupt_stale`: 강제 종료 후 남은 `EXECUTING` 체크포인트에 대해 명시적 운영자 호출로 `INTERRUPTED` 전환. 이전 완료 세대는 보존, 구 토큰으로 뒤늦게 도착한 실행은 커밋하지 못한다. **실제 실행 중인 작업에서 호출하면 작업을 선점하므로, 이전 실행 프로세스의 종료를 확인한 후 사용해야 한다.**
- `AcademicMCPCheckpointService.cancel`: 계획 작성 대기/진단 대기/중단 상태에서 현재 단계의 32자리 토큰 검증 후 취소한다. 대기 중인 미검증 Plan은 폐기하고 새 토큰으로 교체한다.
- `AcademicMCPCheckpointService.reconcile`: 서버의 단계가 `RUNNING`으로 고정된 경우만 명시적으로 조회. 연구 원장이 이미 1세대를 커밋했으면 **재계산 없이** MCP 단계를 완료/다음 계획 상태로 복구한다. 연구 실행이 시작 전이라면 새 Plan 토큰을 발급한다. 실제 실행 중 중단됐다면 위 `interrupt_stale`을 통해 명시적 `INTERRUPTED` 처리한다.
- `resume`: MCP 단계만 중단된 상태에서 엔진은 정상 대기 중인 경우도 복구할 수 있게 보완했다. 기존 정상 연구·완료 세대 중복 실행을 방지한다.
- **추가 공개 MCP 도구:** `cancel_algorithm_research(session_id,checkpoint_token)`과 `reconcile_algorithm_research(session_id)`. 기존 공개 **29개 도구 유지**, 추가 2개로 총 **31개 도구**. 기존 endpoint, OAuth issuer, 승인 DB·키 및 등록은 변경하지 않는 설계다.

## 명시적 미완료 항목

- **지속형 무기한 실행과 백그라운드 스케줄링:** 미구현. ChatGPT MCP 클라이언트가 세대별 LLM 판단을 제공하므로 서버 단독으로 모델 연구를 지속할 수 없다. 시작 시 요청한 최대 100세대는 **용량 제한**이지 100세대 실제 통합 수락 테스트 성공을 뜻하지 않는다.
- **실제 연결 앱에서 신규 2개 도구 노출·호출:** 개발 브랜치에서 도구 계약과 디스패처를 테스트한 후 **기존 URL 배포 및 앱 직접 조회가 별도로 필요**. 등록/URL 변경은 절대로 하지 않는다.
- **연구 효율 개선·원인 입증:** 제안된 가설을 실제 반증 실험으로 자동 평가(S7)하거나 LLM이 랜덤 대비 개선된다고 검증한 것은 아니다.
- **독립 OOS·실거래:** 접근·권한 변경 없음. DEVELOPMENT 데이터의 성과를 검증된 현금 수익으로 표현하지 않는다.

## 수락 검사

- 취소: 세대 1/3 완료 후 중단하면 `CANCELLED`, history 1개, 완료 보고 이유 `CANCELLED_AT_CHECKPOINT`, 추가 실행 불가.
- 오류/재개: 실패했던 원장 기록 그대로, `INTERRUPTED` 상태를 명시적으로 재개하여 다음 계획만 실행.
- 강제종료 복구: gateway가 `RUNNING`으로 남았으나 core가 세대 커밋을 끝냈으면 중복 평가 없이 다음 세대 진행; core가 아직 대기 중이면 다음 계획 컨텍스트·토큰을 안전하게 재발급.
- 기존 OAuth 테스트·동일 공개 URL·기존 MCP 도구 ABI 회귀 테스트 필수.

## 배포 경계

소스 작업 브랜치: `feat/p0-indicator-research-engine-v1`. 운영 서버는 이전 `17fddd5` 고정 실행 디렉터리의 **동일 Quant MCP URL**을 유지하며, 배포 시에는 검증한 커밋을 고정 worktree로 교체하고 기존 OAuth·nginx·state dir의 경로를 건드리지 않는다. 오류가 발생하면 기존 고정 커밋으로 되돌린다.

## 1차 검증 확정

- 집중: 중단/보고/복구 핵심 및 MCP 연구 세션 테스트 통과.
- 전체 `pytest -q -p no:cacheprovider`: **1,345 passed, 0 failed (410.12 s)**.
- 전체 Ruff 통과, Mypy 223개 소스 파일 통과.
- `CANCELLED` 세션은 완료 세대 수와 과거 원장을 유지하며, 연구 실행이 시작되기 전에 남은 RUNNING 체크포인트는 안전한 새 계획 단계로 복구한다.
- 이는 10/100세대 또는 무기한 백그라운드 자동 연구의 수락 테스트가 아니다.
