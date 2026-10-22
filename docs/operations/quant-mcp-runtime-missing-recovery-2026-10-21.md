# Quant MCP 운영 서비스/영속상태 경로 누락 — 안전 복구 진단 (2026-10-21 KST)

## 목적과 판정

기존 **공식 G500 목표의 첫 100세대** 재개를 위한 운영 복구. 기준 소스 [다음 세션 인수인계](autoresearch-quant-mcp-recovery-session-handoff-2026-10-21.md), [마스터 원장](autoresearch-master-progress.md), [G500 승인](../decisions/2026-10-21-quant-500-generation-target.md). 이번 단계는 **READ_ONLY_DIAGNOSIS / BLOCKED_MISSING_ORIGINAL_RUNTIME**이며 **신규 정식 세대 0/100, 배치/세션 ID 없음**. GitHub 과거 완료 이력상 G350이 마지막으로 알려졌으나, 운영 최신 세대와 원본 부모 SHA 및 저장 데이터 SHA는 **미검증**.

## 현재 직접 재현된 사실

- 기존 Qaunt_Autoresearch MCP 5종 `get_workspace_status`, `get_dashboard_status`, `get_research_batch_status`, `get_research_brief`, `list_market_data` 각각 `The tool failed internally.` (이번 복구 요청에서 다시 동일 재현).
- 현재 Moon `127.0.0.1:2999/health`, `127.0.0.1:3000/health` → HTTP 200, `project-moon`; **Quant 서버 건강의 증거가 아님**.
- 기존 문서에 등록된 (변경/재등록하지 않은) `https://project-moon.taild689f9.ts.net/quant/mcp` → HTTP 404; 로컬 `127.0.0.1:2999/quant/mcp` → HTTP 404. 기존 OAuth protected-resource metadata → HTTP 404. 별도 로컬 Quant `127.0.0.1:8787/mcp` → 연결 거부.
- `/shared/nginx/routes.d` 는 **빈 디렉터리**. 현재 Nginx 유효 설정에는 `/quant/` 경로가 없어, 이는 공개 404를 설명한다. `nginx -t`는 PASS이며 Moon 자체 라우트는 정상.
- `/shared/moon-services` 없음. 과거 배포에 쓰인 `quant-mcp.supervisor.conf` 설치본도 현재 호스트 공유 경로에는 없음. `deployment/moon/quant-mcp.supervisor.conf` 소스는 Git에 있으나 런타임 경로가 맞지 않으며 그대로 실행하면 안 됨.
- 과거 기준 운영 데이터 경로 `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http` 없음. 그 상위 폴더에는 현 시점 `.venv`만 존재. 공식 G350 당시 사용했다는 `/shared/moon-workspace/AutoResearchFinance_v2-same-session-350-20261019`, `/quant`, 과거 고정 Quant runtime worktree도 이 호스트에 없음.
- 개발 사본 `/shared/moon-workspace/AutoResearchFinance_v2-pine-internalization-20261020`에 있는 `state/champion.json` 등은 Git 추적된 **초기 템플릿**이며 공식 G350 운영 스냅샷이 아님. 이를 운영 원장으로 승격하면 안 됨.
- Moon 환경은 Docker 컨테이너이며 `/shared`가 지속 호스트 마운트. 현재 Moon 도구에서 Docker CLI를 사용할 수 없고, **Windows Docker Desktop의 별도 볼륨/이전 컨테이너가 남았는지는 확인되지 않음**.
- `AGENTS.md` 및 ScopeLock/원본 Q01-Q20/G500 결정 확인. `tests/governance/test_autoresearch_scope_lock.py` **4 PASS**, `git diff --check` **PASS** (이전 동일 소스 HEAD에서). 본 운영 장애 원인과 런타임 복구를 증명하는 테스트는 아님.

## 원인 가설 구분

1. **확인됨 — 활성 배포 구성이 사라짐:** 원 Quant nginx route 및 백엔드 리스너가 현재 컨테이너에 존재하지 않음. 이것만으로 404와 전용 MCP 호출 실패를 설명한다.
2. **미확인 — 영속 볼륨/호스트 폴더 누락:** 이전 상태가 다른 Windows 경로, Docker 볼륨, 백업에 남았지만 현재 마운트에 나타나지 않을 수 있음.
3. **미확인 — 컨테이너 교체 또는 공유 마운트/워크스페이스 이동:** 원본 작업 경로가 더 이상 현 환경과 동일하지 않을 수 있음.
4. OAuth 만료·개별 도구 버그만으로 볼 이유는 약함: 요청이 라우트 자체에서 404고 서버 포트도 닫혀 있어 서비스 배포 계층 문제를 먼저 복구해야 함.

## 안전 복구 순서 및 차단 조건

1. **Windows Docker 호스트에서 원본 경로와 백업을 먼저 확인:** 현재/과거 컨테이너와 Mount Source/Destination, 명명된 Docker Volume 목록, 원본 `state/moon-http/research`, `state/moon-http/oauth`, `state/moon-http/research/oauth/quant-oauth.sqlite`, `state/moon-http/oauth/public-base-url`, `state/moon-http/oauth/approval-key`, 실제 G350 이후 세대 SQLite/Evidence/Parquet/checkpoint 위치를 **존재·크기·SHA로만** 확인. 토큰/키·DB 본문 외부 노출 금지. 호스트 볼륨 및 백업 없으면 자동 복구 불가능함을 인정.
2. 원본 운영 데이터의 읽기 전용 백업/스냅샷을 별도 안전한 위치에 확보하고 그 SHA·권한·마운트를 확인. 임시 새 DB 생성이나 소스 상태 JSON으로 원래 데이터 대체 **절대 금지**.
3. 인증 DB, URL 핀, 승인 키, 시장데이터, 기존 세대 원장과 함께 **원래 승인된 고정 런타임 SHA**가 식별될 때만 기존 launcher/proxy/Supervisor 복원 검토. `deployment/moon/20-quant-autoresearch.conf`가 과거의 정확한 라우트 원본. 단, 백엔드가 실제 준비되기 전 공개 route만 복구해 502를 만드는 것은 의미 없고, 기존 Moon 원래 `/mcp`·포트·Tailscale 변경 금지.
4. 배포 시 `nginx -t` 통과 후 최소 변경 reload, 로컬 `8787/mcp`와 외부 `/quant/mcp` 미인증 401 및 OAuth metadata 200, **이미 연결된** Quant MCP의 읽기 5종 정상 응답 검증. OAuth 새 등록/키 회전 금지.
5. 운영 공식 마지막 G, running batch/session/checkpoint, parent lineage, dataset bytes SHA, costs, live-orders OFF, sealed OOS 미접근 확인. **최종이 G350이면** G351~G450 preflight; 더 최신이면 중복 세대 생성 금지. GPT 실계획→체결 원인 진단→통제 실험→다음 계획→부모 계승의 immutable evidence까지가 1세대.
6. 본 기록 시점에는 운영 소스/라운터/컨테이너/OAuth/시장/세대 상태를 **변경하지 않았음**. 새 배치와 재시작, recovery/reconcile도 실행하지 않음.

## 사용자 또는 호스트 관리자에게 필요한 안전한 식별 결과

호스트 PowerShell에서 비밀값 없이 **목록·마운트 경로만** 확인: `docker ps -a`, `docker inspect project-moon-local --format '{{json .Mounts}}'`, `docker volume ls` 및 이전 Quant 폴더/백업의 존재. 데이터가 보관된 원본 Source가 발견되면, 그 위치를 함부로 move/copy/삭제하지 말고 원래 동일 경로로 연결 가능한지 평가할 것. **Docker image rebuild, docker volume prune, compose down -v, state initialize는 금지.**

**운영 상태:** BLOCKED_MISSING_ORIGINAL_RUNTIME / 공식 신규 완료 **0/100** / 리스크: 잘못된 신규 연구 상태 생성·OAuth 재등록·기존 계보 상실. **다음 작업:** 호스트 원본 데이터 위치 확보 후 읽기 검증부터 복구.

## 추가 Docker 호스트 마운트 증거 (2026-10-21 KST)

사용자가 Windows PowerShell에서 `docker volume ls`, `docker inspect project-moon-local`, `docker ps -a` 결과를 직접 제공. 현재 Docker named volume은 **`tunneling_project-moon-local-state`**, **`tunneling_project-moon-auditor-state`** 두 개. Quant 전용 volume 없음. `project-moon-local`의 `/shared`는 Windows host의 `project-moon/shared` 서브디렉터리를 바인드 마운트하고, 첫 번째 volume은 `/var/lib/project-moon`에 연결된다. Windows username 등 개인식별 정보가 들어간 원본 Source 절대경로는 공개 원장에 반복 기록하지 않음. Moon 자체 state 볼륨을 Quant state로 간주하지 않는다.

현재 같은 `/shared` 추가 검색에서 Git worktree 하나(개발 checkout)만 확인. `.venv`·cache·`.git`를 제외한 원본 `*.sqlite`, `*.parquet`, `*.db`, `*.zip`, `*.tar` 0건. `/shared/nginx/routes.d` 설치 라우트 0개, `127.0.0.1:8787` 연결 거부 재확인. 이는 **현재 마운트에 원본 Quant 운영 데이터가 없다는 뜻**일 뿐 원래 Windows 드라이브 다른 경로나 백업/이전 Docker 환경에 데이터가 존재하지 않는다는 증명은 아님.

다음 비파괴적 단계: Windows 이전 연구 checkout 또는 백업에서 `quant-oauth.sqlite`, `public-base-url`, `state/moon-http/research`, `*.parquet` 및 G350 이후 checkpoint를 **파일 위치·크기만** 찾아 진위/계보 교차 검증. 비밀·토큰 출력 금지. 원본 이전 상태/공식 최신 세대 확인 전 server init, OAuth 재등록, 빈 배치/전략 계보 생성 및 Docker volume 정리는 금지. 현재 상태 **BLOCKED_MISSING_ORIGINAL_RUNTIME**, 신규 공식 **0/100**.

## 2026-10-22 KST — T4 실제 10세대 재개 전 재검증

**결과: BLOCKED_SAME_OPERATIONAL_RUNTIME; 신규 정식 GPT–MCP 0/10, 기존 OAuth/세대·배포 변경 0.** 사용자 요청에 따라 P3 `next_intent` 구현 커밋 `2810b74` 이후 실제 연결로 전환하려 했으나, 등록된 `Qaunt_Autoresearch` 읽기 도구 `get_workspace_status`, `get_research_brief`, `list_market_data`에서 다시 `The tool failed internally.` 확인. 운영 세션 ID·원본 최신 세대·Parquet 해시를 읽을 수 없으므로 실연구 시작 불가.

- 현재 Moon nginx 2999 `/health`는 HTTP 200이나 `/quant/mcp`, `/quant/health`, `/quant/.well-known/oauth-protected-resource`는 HTTP 404. `127.0.0.1:8787/health` 연결 실패. `/etc/nginx/routes.d`에는 Moon 라우트만 있고 Quant 운영 라우트 0개. 현재 supervisor에는 Moon/nginx만 있고 Quant 서버가 실행되지 않음. 개발 저장소의 `deployment/moon/20-quant-autoresearch.conf`와 `quant-mcp.supervisor.conf`는 설치본이 아님.
- 원본 런처 `run_quant_moon_http.sh`는 기존 key/URL pin/OAuth DB에 의존하며, 세 관련 작업 저장소에서 기대 경로 `state/moon-http/oauth/approval-key`, `state/moon-http/oauth/public-base-url`, `state/moon-http/research/oauth/quant-oauth.sqlite`가 전부 없음. `/shared/moon-workspace`에서 `quant-oauth.sqlite`, approval-key, public-base-url 원본을 못 찾았으나 **Windows 다른 경로·볼륨의 존재 여부는 미확인**. 원본 없는 상태에서 런처 구동 시 새 승인키 또는 새 원장이 만들어질 수 있으므로 **시작하지 않음**.
- 별도의 개발 학술 G452 원장 확인: `state/moon-http/fresh-20261021/research/academic-gpt-checkpoints/cycles.sqlite`, `generations` **452건**, 각 세대 증거 해시 목록의 SHA-256 **`e27c586ccda974438ca7d3ae7c0c2471e935bdaef1aa8dcf446eab1103a8fdf9`**. 이는 *목록 집계 해시*이지 G452 개별 evidence hash나 공식 운영 원장 증거가 아니다. 개발 G452를 공식 G350→G500 후속으로 지정하지 않음.
- Moon/Quant 앱의 OAuth 주소 변경, 등록·재인증, state initialize, 배포 nginx 경로 설치, Supervisor 수정/재시작, API 과금, 실주문/봉인 OOS, 새 세대 생성 **일절 미실행**. 저장소 연구 코드 미수정.

**필수 외부 복구 조건:** 기존 승인키·고정 public-base-url·Quant OAuth DB·정식 운영 연구 원장과 Parquet 원본, 기존 런타임 SHA를 동일 출처로 확인하고 크기/해시만 검증. 그 뒤 비파괴 원본 백업→원본 프로세스만 재연결→무인증 `/quant/mcp` 기대 401, 메타데이터 정상, **연결된 기존** Quant 읽기 도구 응답 → 실제 최신 세대·부모·데이터 해시·주문 OFF 검증. 조건 충족 시에만 T4 GPT 계획→검증→진단→S7→계승 **10세대**부터 시작하고 이후 100세대; V05→T4→V01~V04→V06→V07 순서 유지. 단순 문서상의 404 해결만으로 연결 정상이라고 주장 금지.

## 2026-10-22 KST — 앞선 기록 보충·정정: Supervisor 원인 확인

초기 기록에서 원 `quant-mcp.supervisor.conf` 설치본이 없다고 표현했으나, 이번 정밀 조사에서 **PID1의 실제 include 대상 파일은 존재**함을 확인했다. 다만 파일의 실제 내용은 2026-10-21 14:27 수정된 **대시보드 전용 두 프로그램**으로, **`[program:quant-mcp]`는 없음**. 설치된 파일 존재 여부와 **원 Quant 서버 프로그램 존재 여부는 달라서** 이전 상태 판정은 보다 정확히 `INSTALLED_SUPERVISOR_FILE_REPURPOSED_DASHBOARD_ONLY`로 정정한다. 이와 별개로 원 서버 소스·OAuth 원장 누락, 설치 Nginx Quant 경로 부재, Quant 8787 리스너 부재라는 판정은 유지한다. 10월 21일 오전 최초 장애가 오후 설정 변경보다 선행하므로 대시보드 설정 변경은 최초 운영 파일 누락의 원인으로 볼 수 없고, **Quant 서비스 부재를 지속시킨 직접 설정 상태**로 분리한다. [종합 전수조사](quant-mcp-root-cause-audit-20261022.md) 참조. 운영 상태 및 OAuth 변경 없음.
