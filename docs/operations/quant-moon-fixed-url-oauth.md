# Quant MCP — Moon 고정 URL + 승인 키 기반 OAuth 인증

**작성 및 로컬/공개 URL 확인: 2026-10-09**

## 운영 중인 공개 주소

`https://project-moon.taild689f9.ts.net/quant/mcp`

Moon 기존 `https://project-moon.taild689f9.ts.net/mcp`를 그대로 유지하고, 같은 Tailscale Funnel HTTPS 호스트에서 **`/quant/` 경로만** Quant용 서비스로 프록시한다. Nginx의 기본 리스너는 호스트 `127.0.0.1:2999`, Quant MCP 서버는 컨테이너 내부 `127.0.0.1:8787`에만 바인딩한다. 추가 Tailscale Funnel/포트 공개는 불필요하다.

### 인증의 실제 구성

Moon의 실제 공개 MCP는 **인증 승인 키를 입력하는 OAuth 2.1 방식**이다. 고정 Bearer `MCP_AUTH_TOKEN`은 별도의 직접 클라이언트용 인증 수단이며, ChatGPT 앱에서는 OAuth 클라이언트 등록 + PKCE + 발급된 Bearer 액세스 토큰을 사용한다. 이 Quant 배포는 같은 인증 패턴을 별도 자격 증명으로 구현했다.

- Quant 승인 키: `state/moon-http/oauth/approval-key` (자동 생성, 소유자만 접근 `0600`). Moon의 `MCP_OAUTH_APPROVAL_KEY`는 **사용하지 않음**.
- Quant OAuth 상태: `state/moon-http/research/oauth/quant-oauth.sqlite` (비공개 경로, 토큰은 SHA-256 해시로만 저장).
- OAuth issuer: `https://project-moon.taild689f9.ts.net/quant`
- OAuth audience/resource: `https://project-moon.taild689f9.ts.net/quant/mcp`
- OAuth 메타데이터: `/.well-known/oauth-authorization-server/quant`와 `/.well-known/oauth-protected-resource/quant/mcp`
- 도구당 스코프: `mcp:tools`; 별도 `orders_enabled=false`; 실거래 도구, 내부 Codex 무인 자동 실행은 ChatGPT 전용 11도구에 없음.
- OAuth 인증 코드 PKCE 확인, 승인 코드 재사용 차단, 리프레시 토큰 교체, 잠금된 별도 SQLite 상태를 통합 테스트함.

## 실제 배포 구성

- `scripts/run_quant_moon_http.sh`: 별도 OAuth 키 생성/사용, Moon 기존 `*.ts.net` 호스트 읽기, Quant 백엔드를 루프백 8787에 실행.
- `deployment/moon/20-quant-autoresearch.conf`: Nginx 라우팅. 실제 공유 경로 `/shared/nginx/routes.d/20-quant-autoresearch.conf`에 적용.
- `deployment/moon/quant-mcp.supervisor.conf`: Quant 프로세스를 자동 재시작하는 독립 Supervisor 설정.
- Moon 저장소 `tunneling/Dockerfile`: `/shared/moon-services/quant-mcp.supervisor.conf`가 있을 경우 **다음 이미지 빌드/컨테이너 재생성 시** 설정을 로드하는 선택적 훅. `/shared/moon-services/quant-mcp.supervisor.conf`에 설치됨. Moon의 기본 설정과 인증은 교체하지 않음.

현재 서버는 `nohup scripts/run_quant_moon_http.sh`로 시작되어 공개 엔드포인트가 동작함. **기존 Moon을 중단하지 않았기 때문에** Dockerfile 변경을 적용하는 이미지 재빌드/재생성을 통한 자동 재시작 기능은 아직 검증하지 못했다. 컨테이너를 임의로 재시작하지 말고 Windows Docker 호스트에서 유지보수 시 적용한다.

## ChatGPT에서 처음 연결할 때

1. ChatGPT → **Settings → Plugins → Add custom MCP server** (화면 표기는 계정에 따라 다를 수 있음)를 연다.
2. 주소에 **`https://project-moon.taild689f9.ts.net/quant/mcp`** 를 입력한다.
3. 인증 옵션은 **OAuth**를 선택한다. 새 클라이언트 등록/인증 요청을 시작하면 Quant의 승인 키 입력 화면으로 이동한다.
4. 사용자가 소유한 Windows PowerShell에서 아래 명령어로 **Quant의 승인 키를 직접 확인**한다. 화면에 표시된 승인 키를 *자신의 OAuth 승인 페이지*에만 입력한다. GPT 대화창, Git, Slack, 문제 보고 로그에 붙여넣지 않는다.

   ```powershell
   docker exec project-moon-local /bin/bash -lc 'cat /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/oauth/approval-key'
   ```

5. 앱을 설치/연결하고 `get_research_brief`를 호출하여 11개 도구의 조회 가능 여부를 확인한다. 그다음 사용자 승인된 개발용 데이터로 `run_research_step`을 1회 호출한다.

ChatGPT UI 설정 및 사용자 OAuth 승인 동작은 **사용자가 직접 해야 하는 작업**이다. 코드 및 HTTP 단위 통합 테스트의 성공만으로 사용자 계정의 ChatGPT 플러그인이 설치됐다고 주장하지 않는다.

## 상태 검사 (비밀값 출력하지 않음)

```bash
# 컨테이너에서만
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://project-moon.taild689f9.ts.net/.well-known/oauth-protected-resource/quant/mcp
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://project-moon.taild689f9.ts.net/.well-known/oauth-authorization-server/quant
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST https://project-moon.taild689f9.ts.net/quant/mcp
```

기대: `200`, `200`, `401`. 최초 미인증 `401`은 정상 동작이며 인증 없이 MCP 도구를 사용할 수 없다는 뜻이다.

## 향후 점검/실패 복구

- HTTPS 주소가 달라졌다면 Moon의 기존 `Start-PublicMcp.ps1`와 `tailscale funnel status`로 실제 호스트를 확인한다. **새 호스트명을 임의로 설정하지 않는다**.
- Nginx 경로가 없어졌다면 `deployment/moon/20-quant-autoresearch.conf`와 `/shared/nginx/routes.d/` 파일 및 `nginx -t`를 확인한다. Moon `/mcp` 원본 라우트는 수정하지 않는다.
- 컨테이너를 재생성하기 전에는 Moon 저장소의 선택적 Supervisor 변경 사항이 포함된 이미지로 빌드됐는지와 `/shared/moon-services/quant-mcp.supervisor.conf` 존재를 확인한다.
- 사용자 승인 키를 잃어버렸다면 *기존 상태 디렉터리*의 키를 읽는다. 키 파일을 무심코 재생성하면 기존 승인 워크플로에 영향을 줄 수 있다.
- 재설치하거나 Windows Docker 환경이 바뀌었을 때에는 OAuth 등록 및 승인 플로를 다시 확인한다.

Moon·Quant는 서로 다른 도구/토큰 자격을 사용한다. 기존 Moon의 GitHub/개발 환경 접근 권한을 Quant에게 부여하지 않는다.

## 2026-10-12 persistent public URL pin (anti-reconfiguration guard)

The Quant launcher now pins the Moon-provided OAuth issuer at
`state/moon-http/oauth/public-base-url` (owner-only file, mode `0600`),
which persists under `/shared`, outside source control. On *every* start it
compares the pinned HTTPS `*.ts.net/quant` base with the canonical hostname in
`/shared/AGENTS.md`; mismatches fail closed rather than silently changing the
OAuth issuer/resource and forcing users to register a new ChatGPT URL.

The first migration of an already-running server **must explicitly pin the
currently active, previously verified URL before restart**. If the URL pin is
missing while `quant-oauth.sqlite` already exists, boot fails instead of
guessing/reissuing an identity. A missing approval key with an existing OAuth DB
also fails closed; existing keys/tokens must be retained, not rotated.

The launcher still runs only on loopback port `8787` and the public URL
remains `https://project-moon.taild689f9.ts.net/quant/mcp`; it does not
modify Tailscale identity, Moon's own `/mcp`, or Nginx ingress. `QUANT_MCP_PUBLIC_BASE`
may be supplied only when it matches the durable pin exactly.

Read-only check (must print only the public base, never a key):
```bash
.venv/bin/python -m scripts.quant_public_url   --pin state/moon-http/oauth/public-base-url   --oauth-db state/moon-http/research/oauth/quant-oauth.sqlite
```

User UI plugin updates are separate from endpoint deployment. MCP
`tools/list` can advertise newly added tools at the same URL without any
OAuth re-registration; a client with a cached tool schema may need to refresh
its plugin/tool discovery, but **must not be told to create a new endpoint or
change the URL** unless Tailscale's actual identity is lost.
