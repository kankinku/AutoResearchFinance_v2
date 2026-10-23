# Quant MCP — 기존 OAuth 보존 복구 전용 읽기 사전 점검 (2026-10-23 KST)

## 결과: BLOCKED_PRESERVE_OAUTH — MCP 재시작·재등록·GPT 10세대 미실행

현재 장애는 단순 Quant 후보 중복이나 백테스트 실패가 아니라 **원래 Quant MCP HTTP 서비스 구성 및 OAuth 상태가 현 실행 컨테이너에서 제공되지 않음**으로 확인됐다. 기존 연구 증거 보존이 우선이므로 *임의 OAuth 재발급/새 클라이언트 등록/고정 URL 변경/운영 서비스 재시작을 수행하지 않았다*.

### 실제 Moon 컨테이너 점검 (비밀값/개별 고객 ID 출력 없음)

- 사용 중인 supervisord: `/etc/supervisor/conf.d/workmachine.conf`. 이 파일의 포함 대상은 `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/deployment/moon/quant-mcp.supervisor.conf`.
- 해당 **활성 포함 파일은 존재한다**. 그러나 현재 내용은 주석으로 `Current original Quant source/OAuth absent; startup hook is dashboard-only`를 명시하며 프로그램 `fresh-quant-dashboard`·`fresh-quant-original-ui`만 구성한다. **Quant MCP `[program:quant-mcp]` 자체가 없다.**
- nginx 실제 `nginx -T` 결과: 기존 Moon의 `/mcp`와 새 독립 `/quant-research/`는 있지만 **`/quant/mcp` 라우트가 없다**. `127.0.0.1:8081` 대시보드와 `2999`의 HTTP 응답은 정상이지만 **Quant MCP `127.0.0.1:8787` 수신 프로세스가 없다**.
- 현재 연구 worktree `AutoResearchFinance_v2-fresh-research-20261021`의 `state/moon-http/oauth/approval-key`, `oauth/public-base-url`, `research/oauth/quant-oauth.sqlite` 세 파일이 모두 부재. 현재 점검 가능한 `state/moon-http/backups`는 학술 Gx 사이클/게이트웨이 백업만 보유하며 인증 정보는 포함하지 않는다. 접근 가능한 이전 원본 디렉터리에도 Quant 원본 실행 스크립트가 남아 있지 않다.
- **따라서 해당 파일이 없는 현재 작업공간에서 기존 `scripts/run_quant_moon_http.sh`를 실행하면 새 OAuth key 또는 공개 URL pin을 *bootstrap*할 수 있어, 기존 승인 identity를 보존한다는 사용자 고정 조건을 위반할 위험이 크다. 실행 금지.**
- 연결된 `Qaunt_Autoresearch` MCP 상태 조회는 이전 턴에서 도구 내부 오류를 반환했다. 이번 턴에서도 *운영 인증 RPC 성공 증거가 없으므로 연결 복구/새 GPT 10세대 완료를 주장하지 않는다.*

### 실제 수행한 소스 변경

1. 신규 `scripts/quant_mcp_recovery_preflight.py` — 완전 **읽기 전용**. 활성 supervisord include 파일의 Quant 프로그램 존재·실제 명령 경로·디렉터리 일치, 현재 nginx **loaded** Quant MCP reverse-proxy 경로, 8787 loopback 리스너, 기존 OAuth key·고정 URL pin 형식·SQLite client 테이블 및 integrity를 점검. 인증 파일 내용을 출력하거나 생성·수정하지 않는다. 실행 결과는 안정적 상태 코드만 반환.
2. `deployment/moon/quant-mcp.supervisor.conf` **Git 내부 설치 템플릿만 수정**: 삭제된 `phase3-5-1-inventory` 실행 경로 대신 실제 소스가 존재하는 `AutoResearchFinance_v2-fresh-research-20261021`을 명시하고, **기존 승인키/pin/DB 확인 전에 이 템플릿을 가동하지 말라**는 명시적 주석 추가. 현 운영 `/etc/supervisor`, `/shared/nginx/routes.d`, running supervisord/nginx는 바꾸지 않았다.
3. `tests/operations/test_quant_mcp_recovery_preflight.py` — 기존 승인 정보가 있을 때만 사전 점검 성공(실제 인증 연결을 증명하는 것은 아님), 키/URL/DB가 누락되면 **자동 복구 생성 없이 실패**, 과거 프로젝트 경로·nginx route·서비스 프로그램 부재 시 실패, SQLite 손상 감지, 체크인 템플릿 경로 보증.

읽기 전용 실제 점검:
```bash
.venv/bin/python scripts/quant_mcp_recovery_preflight.py
```
현재 **BLOCKED_PRESERVE_OAUTH**:
`SUPERVISOR_QUANT_PROGRAM_MISSING`, `MCP_LISTENER_DOWN`,
`NGINX_QUANT_MCP_ROUTE_MISSING`,
`OAUTH_APPROVAL_KEY_MISSING`, `OAUTH_PUBLIC_URL_PIN_MISSING`,
`OAUTH_DATABASE_MISSING`.

**안전 판단:** 점검 결과가 사전 조건 PASS로 바뀌더라도 실제 ChatGPT 연결을 통한 인증된 MCP 호출 성공은 별도 검증 필요. 사전 조건 검사만으로 기존 클라이언트의 토큰 유효성·발급자 일치를 증명하지 않는다.

### 검증

- 관련 Pytest **44 PASS**, 전체 Ruff PASS, 신규 스크립트 Mypy PASS. 전체 Pytest/전체 Mypy는 수행하지 않았다.
- 보호된 G452/452 SHA `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`, 기존 격리 G552/552 SHA `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`, 현재 T4 별도 준비 G452/462 SHA 전부 기존 값, 세 DB의 `PRAGMA integrity_check = ok`.
- Quant MCP OAuth 등록/로컬 Key/DB/고정 URL 생성·변경 **0**, 운영 supervisor/nginx reload/restart **0**, MCP 배포 **0**, 주문 **0**, sealed OOS 사용 **0**, 인증된 신규 GPT 세대 **0/10**. `state/logs` 사용자 기존 비추적 항목은 건드리지 않음.

### 보존 조건 충족 후의 복구 게이트 (실행하지 않은 항목)

1. **원본 Quant OAuth 승인지원 DB, approval-key, pin URL** 세 자산의 보존본이 실제로 존재하는 원래 볼륨/백업 위치 확인. 이때 승인된 OAuth issuer/resource URL이 기존 등록과 같음을 외부 기준으로 검증. *새 값 생성하거나 다른 URL로 이관 금지.*
2. 보호된 학술 연구 원장 및 OAuth 원본을 백업/무결성 비교하고, 기존 리소스/인증 정보를 현재 작업공간에서 **원래 승인된 저장 위치/권한으로 읽을 수 있게 복원**. 보존본 확인 전 현재 템플릿을 활성화하지 말 것.
3. 인증·원본 소스가 복구된 뒤, nginx 원래 `/quant/mcp` 라우트와 Quant MCP supervisor 구성 복원을 **별도 승인된 운영 변경 절차**로 수행. 기존 `/mcp` 또는 `/quant-research`를 대체하지 않는다.
4. read-only preflight에서 **모든 blocker가 없어지고**, 실제 연결된 `Qaunt_Autoresearch` 상태 조회 및 하나의 개발 세대 Plan/diagnosis/S7 인증 영수증이 확인될 때에만 T4 GPT 10세대 진행 가능.
5. 원래 승인된 단계 순서: **V05 → T4 실제 GPT 10→100 → V01~V04 외부 PIT/OOS → V06 non-order paper → V07 GO/NO-GO**. 본 점검은 T4 복구 의존성에만 해당하며 변경하지 않는다.
