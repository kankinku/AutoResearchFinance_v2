# T4 / 5단계 — 연구 실행 관리자 읽기 전용 대시보드 연동

점검일: 2026-10-16. 초기 20문답 잠금 범위, 기존 연구 32/100, S7, 인증 및 실거래 OFF 불변.

## 요구 문제
- 기존 학술 모니터 32/100 + `AWAITING_PLAN` 표시는 실제 서버가 중지되었는지, GPT가 다음 계획을 제출하지 않았는지 구별하지 못했다.
- 기존 foreground `ResearchRunSupervisor`는 `academic-supervisor-control` 디렉터리에 owner-only 상태/요청 파일을 저장하지만, 대시보드는 원장 SQLite만 조회했다.
- **모델 호출 주체가 없는 채팅 기반 MCP를 자동 연구 엔진으로 표시하면 안 된다**. Heartbeat는 프로세스가 과거에 살아 있었다는 표시일 뿐, 연구 지속 가능·비용 승인·실제 GPT 연결 증거가 아니다.

## 이번 개발
- `dashboard/academic_worker_status.py`: 기본 foreground supervisor의 읽기 전용, 화이트리스트 상태 요약. `academic-gpt-checkpoints`의 형제 `academic-supervisor-control` 조회.
- 상태 디렉터리/파일을 **생성하지 않음**, 0700/0600 소유자 전용 권한 및 symlink/파일 용량·JSON 검증. 상태 파일이 누락된 경우 연구 원장 단계에 맞게 `PROVIDER_REQUIRED` 또는 terminal 상태를 보여줌.
- `RUNNING` heartbeat도 `RECENT_UNVERIFIED` 또는 `STALE_OR_UNVERIFIED`만 노출해 프로세스가 현재 살아 있거나 모델이 실제 호출 중이라고 주장하지 않음. 중지·일시정지·검토 필요·제어 파일 손상을 독립 표시.
- owner nonce/PID, checkpoint token, 모델 문맥, 원본 제어 JSON·키 등 반환 금지. URL은 기존 `/api/academic/overview` 및 `/api/academic/sessions/{id}`의 sanitized `supervisor` 객체로만 읽기 제공.
- `dashboard/static/academic.html`, JS, CSS: 3초 폴링 화면에 'GPT 연구 실행 상태', 최근 heartbeat, 명시적 모델 입력 필요 안내. **어떤 새로운 쓰기 API, start/stop 제어 버튼, 외부 GPT 호출도 추가하지 않음**.
- 기존 Buy & Hold QQQ, 최고 수익률/Sharpe, S7 실험, 비PIT 주의·거래 OFF 상태 기존대로 유지.

## 검증
- tests/dashboard/test_academic_supervisor_status.py 새 5개: 기본 모델 공급자 미연결, PAUSE/STOP 요청 읽기, 오래된/최근 heartbeat 거짓 실행 주장 차단, 무결성 손상/파일 권한 실패 시 비밀값 미노출, symlink 거부.
- 기존 학술 모니터 테스트 7개와 합쳐 **12 PASS**, Ruff·Mypy·JS 구문 검사 통과. 나머지 운영 검증/배포 상태는 작업 종료 보고에 기록.
- 개별 연구 DB는 수정하지 않으며 32/100에서 33/100으로 허위 전진시키지 않음. 지금의 모델 실행 자동화 기능은 `PROVIDER_REQUIRED` 상태임.

## 후속
- 실제 무인 GPT 모델 공급자는 비용/호출 권한 및 정책 검토 후 명시적으로 연결해야 한다. 현재 MCP ChatGPT 방식만으로 채팅 밖에서 자동 생성 불가능.
- 해당 단계가 승인되면 중지·재개·단일 owner 상태를 보여주고 모델별 호출 예산·실행시간 및 실제 33~100세대 생성/진단·S7 검증으로 진행. OOS/실거래 비승인 유지.

## 읽기 전용 모니터 운영 반영 완료

- 개발 커밋 `5372449`를 detached worktree `/shared/moon-workspace/AutoResearchFinance_v2-academic-monitor-5372449`에 고정. 기존 모니터 포트 8081/8082 및 Quant MCP 운영 백엔드·인증은 그대로 유지.
- 새 read-only FastAPI 프로세스 PID 22318, loopback 127.0.0.1:8083. 정확한 연구 원장 경로 `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/research/academic-gpt-checkpoints`에서 S7/QQQ 원장과 supervisor control 형제 경로만 READ-ONLY 조회.
- 직접 URL `http://127.0.0.1:8083/api/academic/overview` : HTTP 200; 32/100, `AWAITING_PLAN`, S7 누락 0, orders OFF, 별도 상주 provider 없음 `PROVIDER_REQUIRED`; 페이지·JS·CSS 각각 HTTP 200.
- Windows Docker 포트 127.0.0.1:2999 기존 Nginx 보호 경로 `/academic`, `/api/academic/`, `/static/academic.js`, `/static/academic.css`만 내부 8082→8083 변경. Nginx -t 및 무중단 reload 통과, 원본 설정 백업 `/tmp/quant-academic-nginx-backup-before-5372449.conf`. 기존 8082 프로세스 미중단으로 rollback 가능.
- 운영 인증: 해당 4경로 익명 401, 임시 일회성 기본 인증 사용자로 각각 HTTP 200, HTML에 새 worker 영역 확인, API 모델 상태 실제 `PROVIDER_REQUIRED`, 동일 세대 32/100. 기존 비밀번호 파일 원본 바이트 확인·임시 계정 삭제. 기존 Moon /health 200, Quant 익명 /quant/mcp 401 유지. Windows Firefox 직접 로그인 성공 여부는 사용자 측 확인이 필요.
- 실험 원장·MCP URL·OAuth·실주문 설정·20문답 scope 미변경. 운영 대시보드 변경은 정적인 읽기 전용 UI/조회 로직만 적용, 모델 무인 GPT 실행기 자동 배포 아님.
- 제한: 새 별도 대시보드 프로세스는 이 단계에서 수동 loopback 실행되며 **Docker 컨테이너 재시작 후 자동 기동을 보장하지 않음**. 지속성/헬스체크·시스템 구동 시 복구는 별도 운영 작업으로 다룸.
