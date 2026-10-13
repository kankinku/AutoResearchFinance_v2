# Quant MCP — Supervisor 재시작 실증 및 Windows Docker Desktop 호스트 검증

작성/검증 기준: 2026-10-13, Paper / orders_enabled=false.

## 구분해야 하는 세 가지 검증

| 환경 | 실험 | 수용 판정 |
|---|---|---|
| Moon Linux 컨테이너, Supervisor PID 1 | **Quant MCP 프로세스만 종료**하여 Supervisor가 다시 시작하도록 함 | **PASS**, 운영에서 실제 확인 |
| Windows Docker Desktop | Moon **컨테이너 전체** `docker restart project-moon-local` | 아직 **PENDING_EXTERNAL**, Windows CLI/Engine은 Moon 셸에서 접근 불가 |
| Windows 시스템 전체 재시작 / Docker Desktop 자동 시작 | 로그온 후 컨테이너, OAuth, Tailscale/Nginx, 연구 복구 확인 | **NOT_TESTED**, 컨테이너 재시작 결과와 혼동하지 말 것 |

Moon 셸 확인: WSL2 Linux `6.18.40.1-microsoft-standard-WSL2`, Supervisor가 PID 1, Windows C:는 `/shared`에 9p(드라이브 공유)로 마운트, 컨테이너 내부에는 `docker` CLI와 `/var/run/docker.sock` 모두 없음. 이는 Windows 호스트의 Docker Desktop 미설치를 뜻하지 않는다.

## 2026-10-13 실제 Supervisor 실증

1. 관리형 연구 상태에서 활성 `QUEUED/RUNNING` 배치가 없음을 확인.
2. `scripts.verify_quant_moon_restart before`로 **읽기 전용** 기준 지문을 0600 전용 파일에 기록. OAuth 승인 키·OAuth client/grant 기록·연구/세대/가설 SQLite·불변 Evidence를 비교하지만 **키·토큰·SQLite 행은 화면에 출력하지 않음**.
3. 실행 중 Quant MCP PID `10628`에 `SIGTERM` 전송. Supervisor에 등록된 `[program:quant-mcp]`의 `autostart=true`, `autorestart=true` 설정으로 PID `12066` 자동 재기동. Moon 자체 서비스와 Nginx, Supervisor PID 1은 종료하지 않음.
4. 초기 확인 시 로컬 연결 `000`, Nginx 게이트웨이 `502`를 관찰. 서비스가 준비된 후 양측 미인증 MCP 응답 `401/401` 도달. 401은 인증이 작동한다는 뜻이지 애플리케이션 오류가 아님.
5. `scripts.verify_quant_moon_restart after` **PASS**: 지문 10개 일치, OAuth client 2개, Evidence 이벤트 163개, 연구 배치 레코드 7개, GPT 세션 2개, orders_enabled=false. **동일 상태가 새 PID에서 보존됨**.

이 검증은 프로세스 재시작에 대한 저장 지속성 확인이다. 컨테이너의 파일시스템 전체 재생성·이미지 업데이트·Windows 호스트 정전 또는 재부팅에 대한 수용 시험이 아니다.

## Windows Docker Desktop: 사용자 소유 호스트용 안전한 실행 절차

현재 연결된 Moon 내부에서는 Windows `docker.exe`를 호출할 수 없으므로 **호스트에서 직접 실행한 증거 없이는 PASS 판정 금지**.

Windows PowerShell에서 이 저장소의 현재 코드를 확인한다. 신규 스크립트:

`scripts/verify_quant_windows_container_restart.ps1`

먼저 Docker Engine과 대상 컨테이너를 **읽기만** 하며 상태를 출력하는 기본 실행:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_quant_windows_container_restart.ps1
```

기대: `LINUX_ENGINE=PASS`, `WINDOWS_DOCKER_RESTART=NOT_EXECUTED`, 현재 restart policy 표시. 이 결과는 **실제 재시작 성공이 아님**.

Moon 전체가 잠시 중단되어도 되는 **명시적으로 승인한 점검 창**에만 다음을 실행한다:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_quant_windows_container_restart.ps1 -RestartContainer
```

수행 순서: Linux Docker Engine 확인 → 실행 중 컨테이너 확인 → 활성 연구 배치 **0개 요구** → 지속 상태의 비밀 제외 fingerprint 저장 → `docker restart project-moon-local` → 원래 컨테이너가 `Running`인지 확인 → 내부 MCP 로컬/게이트웨이의 미인증 `401/401` 도달 확인 → 동일한 보존 지문 10개 및 기록 수 비교.

`WINDOWS_DOCKER_RESTART=PASS`는 **실제 해당 Windows PC에서 명령어가 종료 코드 0으로 완료되고**, 이전 OAuth·Evidence·세션 상태 지문이 같을 때에만 수용. 장애 발생 시 `BLOCKED`와 원인 요약을 출력하며, 저장된 원래 OAuth 키·DB를 재생성하거나 암묵적으로 배치를 재실행하지 않는다.

### 자동 시작 정책 추가 확인

`DOCKER_RESTART_POLICY=always` 또는 `unless-stopped` 여부는 호스트 자동 시작과 관련된 별도 설정이다. 정책이 그 밖의 값이면 스크립트가 `WINDOWS_HOST_AUTOBOOT_ACCEPTANCE=PENDING_RESTART_POLICY`를 표시한다. 그러나 해당 설정이 맞아도 Windows 부팅과 Docker Desktop 실행 여부는 **실제 호스트 재시작 시험 전에는 NOT_TESTED**다. 이 스크립트는 restart policy를 사용자 동의 없이 변경하지 않는다.

### 안전 경계 및 별도 남은 작업

- Quant OAuth 승인 키·등록 Client·접근 토큰을 채팅이나 Git에 복사하지 말 것. 기준 fingerprint 원본은 ignored private state 내 0600 파일로 보관.
- 컨테이너 전체 재시작은 Moon 서비스 및 Nginx에도 일시 중단을 일으킨다. 실제 업무 중, 활성 배치 중, 사용자 인증 절차 도중에는 실행하지 말 것.
- 재시작 중 `INTERRUPTED`로 남은 배치는 명시적 `resume_research_batch` 호출 전에 체크포인트/불변 Evidence를 완전 검증한다. `CANCELLED`와 `FAILED`를 자동 복구하지 않는다.
- 재시작 직후 인증되지 않은 HTTP 401, 서버 PID 변화, SQLite 지문 일치만으로 ChatGPT에서 **새 도구 메타데이터 갱신** 또는 **인증된 도구 호출**이 검증된 것은 아니다. 기존 ChatGPT connector에는 도구 캐시 갱신이 여전히 필요할 수 있다.
- 별도 초기 Phase 3-7 Docker worker image/build/host acceptance는 기존 `docs/operations/mcp-phase3-7-8-final-host-acceptance.md`에 따른다. 이 문서는 Quant **서비스 재시작** 검증이며 worker image 성능·주문·sealed OOS는 다루지 않는다.
