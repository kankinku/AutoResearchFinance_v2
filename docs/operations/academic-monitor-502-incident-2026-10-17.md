# 2026-10-17 Quant Academic Dashboard 502 — 원인·복구·재발 방지

**단계:** 2-3/T4 운영 관측 복구. **대응 20문답:** Q15(중단·재개), Q16(간결한 상태 보고), Q17(완결 세대 무결성). 기존 100세대 연구/20문답 범위, GitHub 브랜치/전략 및 Trading OFF 정책 변경 없음.

## 실측 원인
- Nginx의 `GET /academic`과 `/api/academic/*`, JS/CSS 역프록시 경로는 `http://127.0.0.1:8085`를 바라봄.
- 서버(컨테이너) 재시작 후 해당 포트 미리스닝·대시보드 PID 없음; 2026-10-17 14:21 KST Nginx 에러 로그에 upstream `127.0.0.1:8085` 연결 거부(111)와 사용자 화면의 502가 대응.
- 기존 foreground 임시 모니터는 `nohup` 실행이었으며 supervisor 자동 시작 등록이 없었음. Quant MCP는 `[program:quant-mcp]`로 감독되고 있어 구조적으로 불일치함. OAuth/비밀번호/연구 데이터 원인 아님.

## 즉시 복구
- 원래 고정 연구 모니터 소스 `2251d4935395872df9234448ebbb20495d1ea9d6`, 포트 `127.0.0.1:8085`, 기존 checkpoint DB 경로로 **읽기 전용 프로세스 재기동**.
- `GET 127.0.0.1:8085/` 200, `/api/academic/overview` 200, S7 누락 0, 주문 false 확인. 운영 중 다른 채팅에서 세대 수가 계속 변하므로 이전 완료 수를 상수로 취급하지 않음.
- 기존 `2999/academic` Nginx 인증(미인증 401) 그대로, proxy 경로·htpasswd·MCP URL/OAuth·주문권한 변경 없음.

## 재발 방지 구현
- `scripts/run_quant_academic_monitor.sh` : 고정 코드 SHA/작업트리 청결·원래 SQLite 존재·로컬 Python 확인 후 `--host 127.0.0.1 --port 8085`로 실행. 코드 변경·원장 유실 시 무단 대체나 외부 바인딩 없이 실패.
- `deployment/moon/quant-mcp.supervisor.conf`: 원래 MCP 프로그램을 유지한 상태에서 별도 `quant-academic-monitor` 항목 추가. `autostart=true`, `autorestart=true`, `startsecs=3`, 시작 순서 40.
- 기존 `/etc/supervisor/conf.d/workmachine.conf`가 이미 동일 파일을 include하므로, **다음 supervisor/container 부팅에서 모니터 자동 실행·비정상 종료 시 자동 재시작**. 다른 연구 세대가 진행되는 시점에 PID1 HUP으로 Quant MCP를 강제 재시작하지 않음. 현재 복구 프로세스는 임시 독립 실행이며 실제 supervisor 제어 전환·재부팅 리허설은 별도 시점에 검증 필요.

## 검증 및 후속
- `bash -n` launcher, supervisor 설정 parser, git diff --check; 운영 HTTP 200·미인증 401, 읽기 전용 세대/S7/주문 비활성 검사.
- **아직 미실행:** 전체 재부팅 실증/새 supervisor 프로그램 프로세스 감시, Windows Firefox 사용자 로그인, 전체 Pytest/Ruff/Mypy 및 독립 성과 OOS 검증. 재부팅 없이 supervisor에 동적 등록 가능한 제어 채널은 해당 런타임에서 확인되지 않았음.
- 원래 계획: T4 GPT 100세대 완결 → PIT/OOS 등 후속 검증 단계로 복귀. 새 알고리즘 세대는 이 복구 작업에서 생성하지 않음.
