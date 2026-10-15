# Quant Autoresearch D08 / 5-1 — 통합 MCP 운영 배포 결과

점검 기준: 2026-10-15 UTC / 2026-10-16 KST

## 실제 운영 배포

- D01~D07 개발 변경을 직계 상속한 D08 코드 브랜치 `feat/d08-integrated-release-gates-20261016`. 고정 소스 커밋 `da2331d2f60e792f302a4bbb7de6a1ac5ffb6fe5`, Worktree `/shared/moon-workspace/AutoResearchFinance_v2-quant-mcp-runtime-da2331d`, GitHub Push 완료.
- 기존 운영 repository `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory` 안에서 배포 브랜치 `deploy/quant-mcp-d08-integrated-20261016`, 런처 커밋 `9c4749d`로 런처의 SOURCE_ROOT, EXPECTED_SOURCE_SHA 두 항목만 갱신하여 GitHub Push.
- 운영 이전 소스 `/shared/moon-workspace/AutoResearchFinance_v2-quant-mcp-runtime-ab6e96b`, 고정 SHA `cfc66cf3f21980b7ca9cd329fb6ce0d51bd20bdd`와 `state/moon-http/deployment-backup/run_quant_moon_http_before_d08.sh` 복구 파일 보존. 기존 OAuth 키, 승인 SQLite DB, 공개 URL 핀 및 연구 원장 삭제/갱신/재등록 없음.
- 실제 서비스 리스너 graceful 중지 후 새 런처로 재시작. 포트 127.0.0.1:8787 리스너 PID의 CWD가 새 고정 Worktree임을 확인. 기존 `https://project-moon.taild689f9.ts.net/quant/mcp` URI 유지, 익명 MCP POST 401, OAuth protected-resource의 resource 불변.
- 기존 연결된 앱에서 read-only `get_research_brief`, `get_workspace_status`, `list_market_data` 직접 호출 확인: 도구수 32개, Workspace READY, 기본 mode mcp, orders_enabled false. OAuth 신규 등록/모델 API/실제 주문 호출 없음.

## 소스 및 검증

- `scripts/d08_release_gate.py` 추가. 운영 launcher/롤백 워크트리/후보의 Git SHA·clean 상태·서로 다른 경로 검사, 기존 인증·core/data/backtest/evaluator/validation/costs/integrity 모듈 코드 동일성 확인. 기존 Git 추적 빈 초기 연구 상태 JSON 네 건만 허용하고 다른 state, symlink, 자격 정보나 변경된 인증 코드는 거부. 실제 배포 전 `RELEASE_PRECHECK_PASSED_NOT_DEPLOYED` PASS.
- `tests/integrations/test_d08_release_gate.py` 5개 PASS (pin·백업/버전·코어변조·인증변경·예상 밖 state 거부). 추가 변경 모듈 Ruff, Mypy PASS.
- T3 전체 저장소 Pytest **1605 passed, 0 failed**. 전체 Ruff PASS, Mypy **252개 소스 PASS**. 신뢰된 기존 운영 Python venv으로 새 고정 Worktree 내 HTTP/OAuth/MCP 및 D08 검사 **13 passed**. 인증은 실제 운영 키가 아닌 격리 테스트 데이터로 검증.
- 운영 전환 전후 익명 401/metadata 확인, 전환 후 연결된 실제 앱 읽기 전용 3종 확인. **실제 장애 롤백 실행은 발생하지 않아 복구 리허설 PASS로 주장하지 않음**; 단 실패 시 원래 고정 코드로 복원할 수 있도록 저장된 source SHA와 이전 launcher 백업을 보존.
- 운영 32개 도구의 쓰기/연구 전체 직접 호출, 실제 GPT 10~100세대·시간 단위 복구(T4), PIT/봉인 OOS·통계·거래비용(T5), 모의거래(T6) 모두 **미실행**. 수익 알고리즘 발견·독립 검증을 의미하지 않음.

## 미완성 인터페이스·후속 순서

- D01/D02/D05의 체크포인트, 복구, S7 증거 기반 실패학습은 기존 Academic MCP 경로에서 접근 가능해짐. D03 논문 리뷰, D04 수식 평가, D06 다자산 연구 비교는 지금도 안전한 **로컬 CLI** 기반이며 기존 공개 MCP 32개에는 별도 호출 도구가 없다. 기존 OAuth/URL 및 도구 개수를 유지하려고 자동 노출하지 않았으며 향후 별도 연동 과제로 보존.
- 다자산 공동 계좌 매매/교차시장 rank, 논문 원문/라이선스 독립 검토, 긴 연구 세대 GPT 재시도/자동 진행, 통계 유의한 투자 수익 검증은 미완료.
- 다음 기본 순서: **V01** 진짜 다른 UTC 날짜 Nasdaq QQQ 원본→V02 과거 공개 시점 증빙→V03 as-of 기업행동→V04 sealed OOS→V05 비용·우연→V06 paper→V07 최종 평가. 운영 MCP 기본은 기존 ChatGPT MCP이며 주문 비활성 유지.

## 긴급 복구 기준

기존 Worktree(`cfc66cf`)와 백업 런처를 사용해 동일 127.0.0.1:8787 서버를 재시작한 뒤 익명 401, OAuth resource URL, 기존 앱의 32도구·READY·주문 비활성을 확인. OAuth DB·키·URL 핀을 새로 발급하지 않음. 배포 checkout Git 원격 브랜치와 보존된 백업은 별도 관리.
