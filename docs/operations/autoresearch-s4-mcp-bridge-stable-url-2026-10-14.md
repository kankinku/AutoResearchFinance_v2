# Quant Autoresearch S4 — 기존 MCP URL 유지형 ChatGPT 연구 체크포인트

기준: 2026-10-14. 원 요구: **기존 Quant Autoresearch 앱을 재등록하지 않고 MCP URL을 그대로 유지**하며 S4의 GPT 기반 알고리즘 생성·백테스트·원인 분석을 연결한다.

## 절대 변경하지 않는 계약

- 기존 공개 리소스: `https://project-moon.taild689f9.ts.net/quant/mcp`.
- Moon nginx: `/quant/mcp` → 기존 loopback port 8787 `/mcp/`.
- OAuth 공개 기준 주소: `https://project-moon.taild689f9.ts.net/quant` (기존 pinned file 보존).
- 기존 OAuth 키·승인 sqlite·리프레시 토큰 저장 위치 변경/회전/초기화 금지.
- 기존 MCP 이름 24개 유지, 새 도구만 **additive**로 추가. 연결 해제, plugin 삭제·재등록, 리다이렉트/엔드포인트 변경 금지.
- 기존 운영 브랜치/원본 개발용 복구 커밋을 수정하지 않음; 소스 변경은 `feat/p0-indicator-research-engine-v1`에 커밋.

## 현재 신규 MCP 도구 (같은 URL의 tools/list)

- `start_algorithm_research(data_path, generations)` — 개발 데이터와 지표 카탈로그 고정, 세션·새 Plan 컨텍스트 생성.
- `get_algorithm_research(session_id)` — 세션 상태, 이전 결과와 다음에 GPT가 작성할 구조화 응답의 컨텍스트 조회.
- `submit_algorithm_plan(session_id,checkpoint_token,plan)` — *GPT가 직접 작성한* 구조화 AlgorithmPlan을 검증하고 실제 백테스트/판단 기록을 계산, 원인 분석용 증거 컨텍스트 반환.
- `submit_algorithm_diagnosis(session_id,checkpoint_token,diagnosis)` — GPT 원인 가설·반대 설명·실험 설계를 정확한 거래/평가 원장 해시와 대조하고 **한 세대를 커밋**, 다음 세대 입력 반환.
- `resume_algorithm_research(session_id)` — 중단된 세대에 대해 운영자의 명시적 재시도; 기존 완료 세대 보존.

**원리:** 서버는 LLM API를 내장하거나 모델 키를 보관하지 않는다. 인증된 ChatGPT MCP 클라이언트 자체가 Research Director이고, 두 시점마다 서버 증거를 확인해 모델이 Plan/Diagnosis를 제안한다. 사용자 인증은 기존 MCP OAuth가 담당한다. 이 호출 방식은 한 대화/워크플로 안에서 사용자의 세대별 수동 메시지 없이 여러 세대 진행 가능하나, ChatGPT 앱이 독립적으로 요청을 시작하는 무제한 백그라운드 연구 기능은 아니다.

**완료된 세대의 의미:** 생성된 Plan → 검증된 인디케이터와 비용 모델을 이용한 canonical backtest → 의사결정·체결 감사 → GPT의 **검증 전 원인 가설** + typed follow-up experiment → 이전 세대 해시와 링크된 체크포인트 저장. 의미상 같은 알고리즘 또는 **해당 개발 데이터에서 매매신호가 완전히 동일한 알고리즘**은 새로운 유효 세대로 세지 않는다.

## 상태 및 보안 경계

- 신규 연구 체크포인트는 기존 state dir 아래 별도의 `academic-gpt-checkpoints` 영역에만 저장. 기존 OAuth, 배치 워커/증거, 거래 데이터 파일을 수정하지 않음.
- 모든 입력 파일은 기존 `resolve_project_input` 로 project root 내부 `.parquet`만 허용하고, `DEVELOPMENT`만 평가 가능. Sealed OOS 및 실행·주문 권한 없음.
- 세대의 plan/diagnosis 단계를 분리한 32바이트 임의 checkpoint 토큰으로 중복 제출 차단. 주어진 토큰·단계·데이터/카탈로그 해시와 당시의 audit/diagnosis context를 다시 확인한다.
- 전송값의 오류는 기존 세대 원장을 수정하지 않는다. 상태가 비정상 종료 상태라면 자동으로 새 세대를 커밋하지 않는다.
- Plan은 인디케이터 **투표 비중**만 제어한다. 실제 투자금 배분이나 주문 실행이 아니다. 학술/개발 데이터의 결과는 independent OOS/PIT/live alpha가 아니다.

## 운영 적용 원칙

현재 공개 Quant HTTP 서버는 별도 복구용 Git 작업 디렉터리에서 시작한다. 실제 서버 코드를 새 기능이 있는 개발 작업 디렉터리로 바꾸더라도 `--project-root`는 **기존 운영 원본**을, `--state-dir`, `--public-url`, `--approval-key-file`은 **기존 절대 경로**를 사용한다. 새로운 server URL, OAuth issuer, approval DB를 만들지 않는다. 서비스 갱신 전후에는 주소 pin·OAuth 파일·비인증 401·OAuth metadata·기존 연결에서 `get_research_brief`를 확인한다. 실패 시 동일 URL과 기존 기동 스크립트로 롤백한다.

본 기능은 MCP 서버에서 모델을 호출하는 것이 아니라 기존 연결 클라이언트가 제출하는 진짜 GPT의 두 응답을 받아 처리하도록 **서버 능력을 추가**한 것이다. 새 5개 이름이 이미 열려 있는 오래된 채팅의 캐시 목록에 바로 나타나지 않을 수 있다. 이 경우 새 채팅에서 현재 연결 앱을 호출해 최신 tools/list를 확인하면 되며, 등록/URL 변경은 불필요하다. 새 채팅에서도 툴 목록이 갱신되지 않는다면 캐시의 문제로 구분해 보고하고, 도구가 이미 노출됐다고 가정하지 않는다.

## 개발 브랜치 최종 검증

- 단일/다세대 GPT 체크포인트 API, 잘못된 단계/nonce, 기존 도구 호환성, OAuth·HTTP 경로와 도구 추가 검증: **집중 테스트 61건 통과**.
- 저장소 전체 `pytest -q -p no:cacheprovider`: **1,337 passed / 0 failed / 415.62초**.
- `ruff check .` PASS; `mypy .` PASS (223 source files).
- OAuth·nginx route·public URL pin 구현 파일과 저장된 OAuth 데이터 형식을 변경하지 않았음. 인증 리소스 URL과 기존 도구 24개를 그대로 유지하고 MCP tools/list에 5개만 추가.
- 위 결과는 외부 GPT 도구 호출을 수용하는 서버 계약 및 mock-directed 2세대 백테스트 평가의 테스트. 실제 앱의 신규 도구 캐시 노출과 실제 GPT 대화의 후속 연구 능력은 운영 점검에서 별도 확인해야 함.

## 2026-10-14 실제 운영 URL 유지형 배포·검증 결과

- 원래 서버의 공개 URL pin: **`https://project-moon.taild689f9.ts.net/quant`**. OAuth 보호 리소스: **`https://project-moon.taild689f9.ts.net/quant/mcp`**. `/quant/mcp` nginx 경로, 로컬 listen `127.0.0.1:8787`, OAuth 키·승인 SQLite의 **절대 경로와 기존 파일**을 보존했다. 앱 삭제·재등록·URL 변경·토큰 재발급 작업 없음.
- 실제 실행 코드: 정식 Git 커밋 `17fddd5392bb210c06f4d6d3a0f0388efac0029d`를 **별도의 detached 고정 Worktree** `/shared/moon-workspace/AutoResearchFinance_v2-quant-mcp-runtime-17fddd5`에서 읽는다. 개발 브랜치 HEAD 변경이 실수로 운영 재시작에 섞이지 않도록 런처가 commit과 clean worktree를 검사한다.
- 기존 운영 작업 디렉터리의 런처 변경은 새로운 **배포 브랜치** `deploy/quant-mcp-stable-url-s4`, 커밋 `c2586f0`으로 기록하고 GitHub에 push했다. 최초 복구 브랜치 `docs/mcp-phase3-5-1-state-inventory`는 커밋 `4a74233` 그대로 보존되며 작업 디렉터리도 clean 상태이다. 원래 실행 스크립트 원본은 기존 ignored state 내부 `state/moon-http/deployment-backup/run_quant_moon_http_before_17fddd5.sh`에 권한을 유지해 백업했다.
- 기존 인증 없는 요청 `GET /quant/mcp`: **401** (OAuth 인증 적용 정상). 기존 공개 OAuth resource metadata `resource`: **동일한 `/quant/mcp` URL**. 운영 재시작 후 실제 연결 중이던 `Qaunt Autoresearch` plugin의 **기존 `get_research_brief` 및 `get_workspace_status`를 재등록 없이 호출**, 도구수 **29**, 연구상태 **READY**, 실거래 주문 **비활성** 확인.

### 실제 GPT 작성 입력 2세대 개발 백테스트 시연

새 MCP 응용 디스패처를 Moon 도구에서 직접 호출해, **GPT가 거래별 지표·손실 사례를 읽고 작성한 Plan과 DiagnosticResponse**를 실제 기존 개발용 QQQ 1,508봉에 제출했다. 2세대는 1세대에서 관측된 Parkinson variance `0.0001` 경계 교차 시의 손실/전환 현상을 검증하려고 경계를 `0.00015`로 변경했다. 그 결과 2세대 개발 구간 성과가 악화됐으며, 개선 성공으로 오인하지 않는다.

| 세대 | 누적 개발구간 수익률 | 최대 낙폭 | 체결수 | 연구가설 |
|---:|---:|---:|---:|---|
| 1 | +56.55% | 12.98% | 69 | 변동성 문턱값 전환이 손실과 잦은 청산에 영향을 줬는가 |
| 2 | +40.20% | 29.43% | 53 | 문턱값 수정만으로 위험이 줄지 않았으므로 자본 노출 축소를 통제실험하자 |

- SQLite 세대 원장이 `COMPLETED/2`로 끝났고 이전 세대 해시·가설 ID와 다음 세대 체크포인트가 연결됐다. 실거래 주문/OOS 검증/PIT/수익성이 검증됐다는 주장이 아니다. 두 개의 외부 모델 응답의 경제적 질을 독립 평가한 연구도 아니다.
- **중요한 구별:** 기존 OAuth를 이용한 연결 도구 호출로는 `get_research_brief`, `get_workspace_status`와 29개 `tools/list` **광고 상태**를 실제로 확인했다. 이번 GPT의 신규 Plan/Diagnosis **제출은 Moon의 서버 디스패처를 직접 이용**했으며, 현재 ChatGPT 대화가 캐시한 신규 MCP 5개 도구를 직접 호출한 것으로 기록하지 않는다. 서버의 `real_model_connection_verified=false` 플래그는 이 때문에 그대로 둔다.
- 이 대화의 툴 목록에는 일부 기존 도구만 보일 수 있다. **기존 연결을 지우거나 재등록하지 말고**, 새 채팅에서 현재 연결된 Quant Autoresearch를 사용해 신규 도구가 제공되는지 먼저 확인한다. 이것이 S4 외부 MCP 클라이언트 실제 2세대 호출의 남은 최종 수락 기준이다.

### 되돌리는 방법 (운영 지침)

기존 복구 스크립트를 백업 위치에서 `scripts/run_quant_moon_http.sh`로 권한 유지 복구하고 Quant 서비스 프로세스만 Supervisor로 재시작하면 원래 소스 코드로 돌아간다. 공개 URL pin, approval key, oauth SQLite DB 및 nginx 경로는 이동/수정하지 않는다. 별도의 Git 복구 브랜치 `docs/mcp-phase3-5-1-state-inventory`는 변경하지 않았으므로 동작 확인 후 그 브랜치로 복귀할 수도 있다. 다만 실제 장애가 없다면 자동 재설치·재인증·URL 변경은 하지 않는다.
