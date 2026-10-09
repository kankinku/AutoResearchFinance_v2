# ChatGPT ↔ Quant MCP 연결 운영 절차 (Secure MCP Tunnel)

**2026-10-09.** 목표는 기존 Moon Tailscale Funnel을 변경하지 않고 ChatGPT에서 별도의 Quant Autoresearch 연구 도구를 호출하는 것이다. 이 문서는 실제 조직 계정의 터널 생성·승인을 대신하지 않는다. **터널 ID·Platform API 키·ChatGPT 앱 설치가 없으면 원격 연결은 아직 미완료**다.

## 현재 검증 범위

- `integrations.chatgpt_mcp_stdio`: 외부 GPT 전용 공식 MCP SDK stdio 서버. 11개 연구 도구, 주문 권한 없음. 내부 Codex 실행 없음.
- `scripts/run_chatgpt_mcp_stdio.sh`: 현재 저장소 경로와 가상환경을 찾아 실행하는 표준 래퍼. 표준 출력에 MCP 외 텍스트를 쓰지 않는다.
- `integrations.chatgpt_mcp_http`: 선택적으로 인증된 루프백 HTTP 전송 지원. **고정 bearer 토큰 HTTP 방식은 ChatGPT 플러그인용 OAuth가 아니다.** ChatGPT는 임의 API 키를 직접 제시하는 사용자 정의 서버 인증을 지원하지 않으므로 이 HTTP 방식만으로 앱 등록을 완료할 수 있다고 간주하지 않는다.
- Moon Linux 컨테이너에서는 `curl`로 `api.openai.com` HTTPS 응답 수신을 확인했지만 `tunnel-client`, `tailscale`, `docker` 명령은 찾지 못했다. 이는 Windows Docker 호스트에 이들 도구가 없다는 뜻은 아니다.

## 1. 기존 서버에서 사용 가능 여부 확인 (이미 내부 통과)

```bash
cd /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory
PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  -p no:cacheprovider tests/integrations/test_chatgpt_mcp_stdio.py \
  tests/integrations/test_chatgpt_mcp_launcher.py
```

실제 프로토콜 통신 테스트가 GPT 전용 11개 도구를 발견해야 한다. 기존 13개 도구를 노출하는 `integrations.codex_mcp_server`가 아닌 **`scripts/run_chatgpt_mcp_stdio.sh`**가 터널 대상이다.

## 2. OpenAI Platform에서 터널 생성 (계정 소유자 직접 수행)

1. OpenAI Platform의 **Tunnel settings**에서 private MCP tunnel을 생성하거나 사용 권한이 있는 기존 터널을 선택한다. 권한이 없다면 Platform 조직 owner에게 Tunnels Read + Manage(생성), Tunnels Read + Use(연결)를 요청한다.
2. 터널 ID(`tunnel_...`)를 기록하고 `tunnel-client`용 런타임 API 키를 안전하게 발급한다. **API 키를 채팅·Git·콘솔 기록에 남기지 않는다.** 터널 ID도 공개 링크로 게시하지 않는다.
3. 공식 배포 페이지의 최신 OpenAI `tunnel-client`를 **MCP 서버가 실행되는 곳에서 호출 가능한 호스트**에 설치한다. 그 호스트에서 `tunnel-client help quickstart`를 확인한다. 임의의 설치 스크립트를 `curl | bash`로 실행하지 않는다.
4. OpenAI Platform 조직과 ChatGPT workspace의 터널 연관 설정 및 앱 생성 권한을 확인한다.

## 3A. 터널 클라이언트를 Moon Linux 컨테이너 안에 설치한 경우

개인적으로 관리하는 터미널에서만 `CONTROL_PLANE_API_KEY` 환경변수를 설정한다. 다음의 터널 ID는 **실제 사용자 계정에서 발급받은 값**으로 대체한다.

```bash
# CONTROL_PLANE_API_KEY는 비밀값. 다른 사람에게 전달하지 않는다.
# QUANT_TUNNEL_ID는 실제로 생성한 터널의 ID로 설정한다.
tunnel-client help quickstart
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile quant-chatgpt \
  --tunnel-id "$QUANT_TUNNEL_ID" \
  --mcp-command "/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/scripts/run_chatgpt_mcp_stdio.sh"
tunnel-client doctor --profile quant-chatgpt --explain
tunnel-client run --profile quant-chatgpt
```

클라이언트 종료 시 터널 연결도 끊길 수 있으므로 프로덕션에서는 검증 후 서비스 관리자를 설정한다. 이 프로젝트는 아직 서비스를 자동 시작하도록 변경하지 않았다.

## 3B. 터널 클라이언트를 Windows Docker 호스트에 설치한 경우

`workmachine` 컨테이너가 실행되고 있으며 `/shared/moon-workspace/...`가 **컨테이너 안**의 실제 경로인지 PowerShell에서 먼저 확인한다.

```powershell
# 기존 Moon 컨테이너를 삭제/재생성하지 않는다.
docker ps --filter "name=workmachine"
docker exec workmachine /bin/bash -lc "test -x /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/scripts/run_chatgpt_mcp_stdio.sh"
```

컨테이너가 확인되면 Windows의 `tunnel-client`가 `docker exec -i`로 전용 MCP 프로세스를 실행하도록 설정할 수 있다.

```powershell
$mcpCommand = 'docker exec -i workmachine /bin/bash /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/scripts/run_chatgpt_mcp_stdio.sh'
tunnel-client init --sample sample_mcp_stdio_local --profile quant-chatgpt --tunnel-id $env:QUANT_TUNNEL_ID --mcp-command $mcpCommand
tunnel-client doctor --profile quant-chatgpt --explain
tunnel-client run --profile quant-chatgpt
```

위 PowerShell 명령은 **운영 지침**이다. Moon 컨테이너에서 Windows 호스트의 `docker`와 `tunnel-client`를 호출할 수 없어 아직 Windows 실기기로 검증하지 못했다. `CONTROL_PLANE_API_KEY`는 환경변수로 제공해야 하며 사용 전에 도구의 공식 `help` 출력을 확인한다.

## 4. ChatGPT에서 연결 (계정 소유자 직접 수행)

1. ChatGPT **Plugins → + → Add custom MCP server**를 연다.
2. **Connection: Tunnel**을 선택하고 사용 권한이 있는 터널을 선택하거나 실제 터널 ID를 입력한다.
3. 이 경로에서는 전용 stdio 서버가 별도의 사용자 OAuth를 구현하지 않으므로 **No authentication** 모드를 사용할 수 있는지 계정/조직 정책을 확인한다. 터널의 접근 통제는 Platform/ChatGPT workspace 권한에 의해 이루어진다. 다른 사람에게 앱을 공유하지 않는다.
4. 도구를 스캔해 `get_research_brief`, `run_research_step`이 보이고 `start_system`, 주문 도구는 보이지 않는지 확인한다.
5. 앱을 생성·설치한 뒤 새로운 대화에서 해당 앱을 지정하여 읽기 전용 `get_research_brief`로 최초 검증한다.
6. 연구 실행은 **승인된 synthetic/development 데이터**로 단일 `run_research_step`을 실행하고 응답에 `orders_enabled=false`와 `research_run_id`가 있으며 Evidence가 남는지 확인한다.

계정 및 조직별 ChatGPT 앱/도구 권한이 허용되어야 한다. 사용 중인 플랜 또는 workspace에서 `run_research_step`을 허용하는지 실제로 확인해야 하며, 단순 코드 성공을 설치 성공으로 해석하지 않는다.

## 5. 실패 시 진단 및 대응

| 실패 지점 | 확인할 사항 |
| --- | --- |
| Moon stdio 사전검사 실패 | 가상환경 및 코드 테스트 상태, `scripts/run_chatgpt_mcp_stdio.sh` 경로 |
| tunnel-client 실행 파일 없음 | 공식 최신 릴리스 설치, 실행 호스트와 CPU/OS 구조 일치 |
| `tunnel-client doctor` 실패 | Platform 터널 ID/실행 키/Read+Use 권한, OpenAI HTTPS egress |
| ChatGPT에 터널이 안 나타남 | Platform ↔ ChatGPT workspace association 및 앱 생성 권한 |
| 도구 목록이 13개 | 잘못된 기존 정본 MCP 진입점을 사용함. GPT 전용 stdio 래퍼로 변경 |
| 요청 때 연결 끊김 | 터널 클라이언트 프로세스 유지·컨테이너 실행 상태 확인 |
| 인증·승인 문제가 발생 | 토큰 공개 금지, 조직 관리자가 OAuth/터널 정책 확인 |

**금지:** 기존 Moon Funnel 해제, 무인증 공개 포트 개방, 실거래 권한 활성화, 계좌 API 키를 MCP 도구 인수로 입력, Sealed OOS 접근 허용.

## 공식 참고 문서

- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/plugins/build/auth
- https://github.com/openai/tunnel-client

## 6. 상태를 확인하는 안전한 명령

Moon 프로젝트 디렉터리에서 다음을 실행하면 서버 준비도, 터널 실행 파일 존재 여부, 자격 증명 환경변수의 **설정 유무만** 출력한다. 실제 API 키나 터널 ID의 값은 출력하지 않는다.

```bash
scripts/check_chatgpt_tunnel_environment.sh
```

2026-10-09 Moon Linux 환경의 검증 결과:

```text
MCP_STDIO=READY
TUNNEL_CLIENT=MISSING
CONTROL_PLANE_API_KEY=NOT_SET
QUANT_TUNNEL_ID=NOT_SET
HTTPS_EGRESS=REACHABLE
```

출력의 `MISSING`/`NOT_SET`은 사용자의 Windows 호스트 전체에 해당하는 상태가 아니라 **현재 접근한 Moon Linux 프로세스의 환경**이다. 외부 바이너리 자동 설치는 보안 검사에서 차단되어 수행하지 않았다. 이 값을 근거로 터널 설정이 완료됐다고 주장하지 않는다.
