# Quant MCP — 신규 OAuth 승인과 기존 Client ID 폐기 (2026-10-23 KST)

**상태:** 새 서버·고정 URL 연결 PASS, **ChatGPT 사용자 OAuth 재승인 대기**, 정식 GPT 자율 10세대 신규 0/10.

## 왜 새 인증인가

사용자가 기존 승인키를 계속 찾지 말고 필요한 경우 같은 고정 공개 URL로 새 OAuth 등록을 승인했다. 기존 Quant 서버의 OAuth key/pin/client/grant DB가 현재 활성 repo root에 없었으므로 새 인증을 명시적으로 발급하되 *같은 URL*을 사용하고 연구 원장과 계보를 유지했다. 원래 ChatGPT의 OAuth client ID는 새 비어 있는 client DB에 없기 때문에 첫 사용자 재연결 시 **invalid_request: Client ID ... not found** 오류가 났다. 해당 ID를 임의로 만들어 삽입하지 않는다. **기존 사용자 지정 Quant 플러그인의 연결을 해제/등록 삭제한 후, 같은 주소의 새 MCP 서버로 OAuth 재등록을 시작해야 한다.** 사용자 UI 승인은 서버가 대신 할 수 없다.

## 변경 내역과 보존 경계

- 신규 일회성 사용자 승인 스크립트 `scripts/provision_quant_fresh_oauth.py --authorize-new-identity`: 3종 신규 key, public URL pin, 빈 client/grant OAuth DB와 marker를 `state/moon-http`에 개인 접근 권한 0600으로 발급. 기존 부분 파일·연구 system 상태 발견 시 중단하고 덮어쓰지 않는다. 승인키/토큰 값은 채팅이나 Git에 출력되지 않음.
- `scripts/quant_mcp_identity_guard.py`: 새 등록의 0 client 상태는 위 marker에 저장된 새 key/pin 해시와 명시적인 fresh schema가 검증된 경우에만 허용한다. 원래 OAuth DB는 등록된 client 1개 이상 요구하는 정책 그대로 유지한다.
- `scripts/run_quant_moon_http.sh`: 인증 파일 생성 로직 없음, 기존 startup guard 통과 시에만 실행하는 정책 유지.
- 고정 issuer: `https://project-moon.taild689f9.ts.net/quant`, MCP URL: `https://project-moon.taild689f9.ts.net/quant/mcp`. 기존 Moon 자체 `/mcp`, 포트 2999/3000과 Moon OAuth는 변경하지 않음.
- 2026-10-23 실제 원장 사전 검사: G452/452 마지막 SHA `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`; G552/552 마지막 SHA `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`. 두 SQLite `PRAGMA integrity_check=ok`와 이전 count/head 일치. 보존 원장 변경 없음.
- 로컬 loopback 127.0.0.1:8787 Quant OAuth 앱 기동 성공. Quant nginx 라우트 파일만 신규 설치: `/shared/nginx/routes.d/20-quant-autoresearch.conf`, 기존 `35-fresh-quant-dashboard.conf` 유지. `nginx -t` 및 reload 성공. 현재 서버는 독립 nohup 백그라운드 프로세스(실행 PID는 영속 보장 식별자 아님). 운영 Supervisor 실제 include 파일에 `[program:quant-mcp]` 등록하였으나 해당 설정은 **다음 Supervisor 시작 시 적용**되며, 본 턴에 전체 Moon Supervisord를 재시작하지 않았음.
- 공개 HTTPS 검증: /quant/mcp 미인증 401, OAuth authorization-server와 protected-resource 각각 200. 등록 엔드포인트 `/quant/register`는 GET 405 (POST-only), authorization/consent의 파라미터 없는 GET은 각각 400; 예상한 OAuth 라우트 존재. Moon /health 200, /mcp 미인증 401. **GPT 인증 tools/call 성공 증명은 아님**.
- 이번 차수 예비 테스트: 신규·기존 OAuth/통합 29 pytest PASS, repo Ruff PASS, 변경 module mypy PASS, bash -n PASS; 신규 ChatGPT 사용자 재연결은 사용자 승인 대기. real GPT 연구 0/10, 다른 유료 OpenAI API 호출 0, 실거래 0, sealed OOS 접근 0.

## 사용자 인증 방법

1. ChatGPT 설정 → Plugins 에서 기존 **Qaunt_Autoresearch** 사용자 지정 MCP 연결을 해제한다. 기존 client ID를 재사용한다면 기존 등록을 제거하고 **새 사용자 지정 MCP 서버**를 똑같은 URL로 추가한다.
2. URL: `https://project-moon.taild689f9.ts.net/quant/mcp`. 인증은 OAuth. 새 DCR 등록 요청 후 consent로 이동해야 한다.
3. 필요한 신규 승인키는 본인 Windows PowerShell에서만 읽어 클립보드로 복사 가능:
   `docker exec project-moon-local sh -c 'cat /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/state/moon-http/oauth/approval-key' | Set-Clipboard`.
   이 값을 채팅/Git/외부 메신저에 보내지 않고 정식 Quant OAuth 승인 페이지에만 입력.
4. 이후 Quant MCP `get_workspace_status` 및 `get_research_brief` 읽기 요청이 실제 인증으로 작동하는지 확인한 뒤 격리된 실제 GPT 계획/진단·S7의 1세대, 이후 T4 10세대를 진행한다.

## 후속 우선순위

본 작업은 T4 Q02/Q06/Q15/Q17의 실제 모델 연결을 위한 **필요한** 운영 종속성이다. OAuth 신규 발급이나 401/200 상태만으로 자동 연구 완성을 주장하지 않는다. 기존 V05→T4 GPT 10/100→V01–V04→V06→V07 고정, 기존 세대 원장 immutable, 주문 OFF 유지.
