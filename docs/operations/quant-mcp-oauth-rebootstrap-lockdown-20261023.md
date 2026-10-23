# Quant MCP 기존 OAuth 재발급 방지 강화 — T4 복구 게이트

**날짜:** 2026-10-23 KST
**상태:** 개발 코드·독립 테스트 완료. **기존 Quant MCP 연결 미복구**, 실 GPT 추가 세대 **0/10**.

## 실제 인증 자료 탐색

- 연결된 `Qaunt_Autoresearch.get_workspace_status`는 여전히 `The tool failed internally`.
- Windows 공유 마운트에서 접근 가능한 `/shared/moon-workspace`의 프로젝트 경로(venv/git/node_modules 제외)와 Moon 자체 상태 `/var/lib/project-moon`을 원본 파일명으로 재검색했다. `quant-oauth.sqlite`, `oauth/approval-key`, `oauth/public-base-url` **모두 검색 결과 0개**.
- 기존 진단 문서 `quant-mcp-runtime-missing-recovery-2026-10-21.md`와 대조: 사용자가 이전 Windows Docker에서 이미 `docker volume ls`, `docker inspect project-moon-local`을 실행했으며 Quant 전용 볼륨이 아니라 **Moon 기본 상태**와 **감사 전용** 두 named volume만 확인됐다. 이번 Linux 실행 컨테이너 내부에는 Docker/PowerShell 명령이나 Docker socket이 제공되지 않아 Windows 다른 디렉터리와 임의의 기존 Docker 컨테이너/비연결 백업을 새로 열 수는 없다.
- 해당 경로에서 발견되지 않았다는 것은 **영구 삭제의 증거가 아니며**, 원본 승인 정보는 접근되지 않는 Windows 경로나 오프라인 백업에 남아 있을 수 있다.
- 현재 활성 Supervisor에는 `quant-mcp` 프로그램이 없는 dashboard-only include가 사용 중이고, nginx에는 `/quant/mcp` reverse proxy와 `8787` listener가 없다.
- **Moon 자체** `/var/lib/project-moon/oauth-approval-key`와 `oauth-state.json`은 Quant 전용 OAuth가 아니며 **절대 대체 키로 사용하지 않는다**.

## 발견한 추가 사고 위험과 수정

**기존 기동 스크립트 `scripts/run_quant_moon_http.sh`는 OAuth client DB가 없는 상태에서 기존 `approval-key`까지 없으면 새 키를 자동 생성하고, 고정 URL 파일도 신규로 기록할 수 있는 경로가 있었다.** 보호된 기존 등록을 보존하라는 고정 정책과 충돌할 위험이 있어, 본 작업에서 **자동 bootstrap 경로를 제거**했다.

1. 운영 기동 스크립트는 작업 시작 전 기존 `approval-key`, `public-base-url`, `quant-oauth.sqlite`가 **정확히 모두 존재하고 비어 있지 않으며 심볼릭 링크가 아닌지** 확인한다. 누락/일부 복원 때는 종료 코드 `78`로 거절한다. 디렉터리 생성과 키 생성 작업 자체를 수행하지 않는다.
2. 신규 `scripts/quant_mcp_identity_guard.py`는 **모두 읽기 전용**으로 key/pin 권한, 기존 공개 HTTPS `*.ts.net/quant` 형식, SQLite `PRAGMA integrity_check`, `clients(id,data)`와 `grants(digest,kind,client_id,payload,expires)` 필수 스키마, 저장된 등록 클라이언트의 존재를 확인한다. 해당 기존 자료가 검증되지 않으면 HTTP 서버가 OAuth 스토어를 초기화하기 전에 차단한다. 이 코드는 인증 키·토큰·공개 URL의 실제 값을 출력하지 않는다.
3. 기존 `scripts/quant_mcp_recovery_preflight.py`가 같은 읽기 전용 검증 함수를 사용하도록 통일했다. 운영에서 쓰던 직접 실행(`python scripts/quant_mcp_recovery_preflight.py`)과 패키지 실행(`python -m scripts.quant_mcp_recovery_preflight`) 양쪽 모두 작동하도록 호환성 회귀 테스트를 추가했다. 활성 Supervisor, nginx 라우트, 리스너 검사는 별도로 유지한다.
4. 신규 두 테스트: `tests/operations/test_quant_mcp_startup_identity_guard.py`는 격리 임시 디렉터리로 스크립트를 복사해 초기/부분 키 분실 시 **새 파일 생성 없음**, 가상 기존 인증 triplet과 mock transport, URL 충돌 및 symlink 거부를 시험한다. `tests/operations/test_quant_mcp_identity_guard.py`는 실제 SQLite fixture로 정상 저장소, 빈 클라이언트, schema 삭제, DB 훼손, 키/URL 문제, 잘못된 접근권한을 시험한다. **실제 OAuth 연결 요청·키 읽기·서비스 재시작 없이 진행.**

## 검증

- 관련 회귀 Pytest **55 PASS**, Ruff 저장소 전수 **PASS**, 변경 인증 점검 Python 2개 Mypy **PASS**, shell `bash -n` PASS.
- 보호된 원장: 기존 G452/452 마지막 증거 `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`; 기존 별도 G552/552 마지막 증거 `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`; T4 개발용 복제 G452/452. 세 DB 모두 `integrity_check=ok`.
- **운영** Supervisor/nginx/MCP 서버 변경 0, OAuth 발급/새 등록 0, 고정 URL 변경 0, trading orders 0, sealed OOS 접근 0. 인증된 GPT 추가 완료 세대 **0/10**.

## 사용 가능한 읽기 전용 점검

```bash
.venv/bin/python scripts/quant_mcp_recovery_preflight.py
.venv/bin/python -m scripts.quant_mcp_identity_guard --root .
```

두 검사는 파일을 생성·변경하거나 서버를 시작하지 않는다. 현재 원본 파일을 아직 찾지 못해 **실행 차단이 정상 동작해야 한다**.

## 남은 의존성

- 원래 등록에 사용된 **동일** key·고정 URL pin·OAuth client/grant SQLite의 보존 경로를 Windows 호스트 원래 바인드 마운트나 공식 백업에서 찾아야 한다. 필요하다면 사용자가 Windows Docker 호스트 측 경로를 직접 확인해야 한다. 백업 원본이 없으면 OAuth 정체성을 유지한 복구는 불가능하며 새 등록은 사용자 별도 승인 없는 한 금지.
- 실제 원본을 찾더라도 기존 토큰/client, issuer, 연구 체크포인트/market provenance를 **복구 전후 동일**하게 검증하고, 별도 승인된 변경 작업에서만 Supervisor와 nginx를 원래 경로로 연결해야 한다.
- 실제 앱 인증 RPC가 성공하고 원본 학술 세대 증거를 확인한 뒤 **T4 실제 GPT 10세대** 완료 검증을 시작한다. 10세대 실패를 방치한 채 100세대로 확장하지 않는다.
- 고정 순서 **V05→T4→V01~V04→V06→V07**, 기존 OAuth/MCP 재등록 금지, 실거래 OFF를 그대로 유지한다.
