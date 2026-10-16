# Quant Autoresearch — T4 / 3단계 실제 운영 배포 및 GPT 100세대 부분 실행

확인: 2026-10-16 KST/UTC. **원래 20문답 Q02 Q06 Q07 Q08 Q15 Q17 Q20** 범위 잠금 준수. 이전 [T4 10+10 비교 및 복구](autoresearch-t4-preregister-random-recovery-2026-10-16.md) 직계 후속. 실거래 비활성.

## 1. 릴리스 후보·운영 배포 실측

- 기존 실행 코드 `da2331d2f60e792f302a4bbb7de6a1ac5ffb6fe5`에서 현재 개발 진단·S7 집계 수정 등이 포함된 `b50b4c7fd759e283b10c5145b7477345922be8dc`에 대해 *별도 고정 clean Git Worktree* `/shared/moon-workspace/AutoResearchFinance_v2-quant-mcp-runtime-b50b4c7`를 생성했다.
- `scripts/d08_release_gate.py`로 기존 launcher pin, 이전/후보 worktree 및 상태 파일, OAuth와 모든 protected `core/data/backtest/evaluator/validation/costs/integrity` Python 모듈 동일성 검사 **RELEASE_PRECHECK_PASSED_NOT_DEPLOYED**.
- 검증: 현재 코드가 있는 개발 작업 디렉터리에서 기존 시장 Parquet 포함 **전체 Pytest 1,655 PASS**, 별도 고정 Worktree 전체 Ruff PASS, 기존 개발 Python 환경 `application/academic_checkpoint_service.py` 대상 Mypy PASS. 후보 Worktree에 비추적 가격 Parquet가 없어서 첫 전체 Pytest에서 `test_only_registered_second_parent_is_accepted_in_mixed_mode`가 `DATA_FILE_NOT_FOUND`로 실패; 소스 버그가 아닌 비추적 fixture 부재로 확인하고, 데이터가 이미 존재하는 원래 개발 디렉터리에서 **동일 b50b4c7 커밋을 재실행하여 1,655 PASS**. 후보 환경 MCP/세션/범위 잠금 집중 테스트 **30 PASS**. 전체 mypy **이번 변경 후 미실행**.
- 기존 운영 체크아웃 `deploy/quant-mcp-d08-integrated-20261016`의 추적되는 `scripts/run_quant_moon_http.sh`에서 `SOURCE_ROOT`·`EXPECTED_SOURCE_SHA`만 변경 후 `6e09457` 커밋·원격 Push. 동일 기존 `ROOT`, URL pin, OAuth 승인 DB/key 및 연구 원장 인자 유지. 원래 launcher는 `state/moon-http/deployment-backup/run_quant_moon_http_before_t4_20261016.sh`에 소유자 전용 권한으로 보존. 자동 롤백 검사를 포함한 one-time controlled Supervisor restart 실행. 실제 rollback **발생하지 않음**.
- 실제 운영 Quant HTTP Supervisor 프로세스 PID `22` → PID `4010`, `/proc/4010/cwd`가 새 고정 Worktree `...b50b4c7`인 것 확인. localhost MCP 익명 POST `401` 확인, 기존 approval key/public URL pin 바이트 SHA 양쪽 유지, 기존 연결된 ChatGPT 앱 MCP 도구 **32** 확인, `get_workspace_status`에서 `READY`/`orders_enabled=false` 확인.
- 운영 OAuth 앱 재등록/갱신·비밀번호 재설정·실주문/비공개 API 모델 호출 **없음**. 여전히 `https://project-moon.taild689f9.ts.net/quant/mcp` 주소 유지.

## 2. S7 집계 버그의 운영 실제 해결

- 운영에서 기존 완료 GPT 10 세션 `49d3033496844ea391f7bdc983da3fc9`와 무작위 10 세션 `bb06ec457ee443bd9fb22273457c054f`를 **실제 연결된 MCP `get_algorithm_research`로 재조회**:
- 두 세션 모두 `COMPLETED 10/10`, `final_report.tested_hypotheses=10`, `all_proposed_hypotheses_measured=true`, `gateway_s7_count_source=HASH_VERIFIED_IMMUTABLE_GATEWAY_REPORTS` 확인. 이전 서버의 잘못된 `0` 집계 해소됨.
- 이 수정은 **데이터/세대 증거를 수정하는 것이 아닌 report 계산층**의 결함 수리. `model_autonomy_verified=false` 및 주문 off 그대로 유지.

## 3. 실제 GPT↔MCP 100세대 세션 진행

- 기존 고정 QQQ `data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet`, dataset SHA `328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6`. 실제 새 세션 `a84a100b15a242269b554282b01d91c9`를 `start_algorithm_research(generations=100)`로 생성, **10/100세대 완료·90세대 남음**.
- 이번 ChatGPT 턴에서 10개씩 서로 다른 typed Plan을 직접 작성·제출하고, 매 세대 수익/낙폭/거래별 손실 ID 관찰에 근거해 구조화 가설과 대조실험을 제출한 후 별도 S7 보고서 직접 호출. 실제 운영 원장에서 **10개 세대마다 증거 해시와 S7 체인 10/10 결속**, 서로 다른 전략 semantic hash 10/10, 기대 방향 일치 4·불일치 6. 성공만 저장하지 않고 반례를 모두 기록.
- 기존 운영 서비스를 재시작할 때 이 세션은 **7/100·AWAITING_PLAN** 상태였다. Supervisor 재시작 후 새 실제 MCP에서 **기존 7세대/7번째 근거 해시 `7777cb584ed63340ef7f0fdee7dca357bf745191ab6f13d73e25d680e2a158af`가 변함없이 유지**되었고, **8/9/10세대를 새 서비스에서 더 커밋**. 10세대 새 S7 3건 정상 결속; 실제 재시작을 통한 상태 지속성을 검증했다.
- 읽기 전용 `cycles.sqlite`·`gateway.sqlite` SHA-chain 감사 결과 `docs/operations/evidence/quant-validation-20261016/t4-100run-postrollout-10gen-hash-audit.json`. `AWAITING_PROVIDER`/`AWAITING_PLAN`로 다음 **11세대** 입력 가능. 세션 재시작·카탈로그/원장 새로 생성 안 함.
- 표시된 각 세대 수익/Sharpe/MDD는 **재사용 NON_PIT DEVELOPMENT** 데이터의 관측일 뿐, 새로운 독립 OOS·PIT·여러 시장·실현 가능 순수익을 검증한 게 아니다. 서버의 `model_autonomy_verified=false`를 true로 위조하지 않음. 이번 10세대는 ChatGPT가 툴을 직접 순차 호출했으나 모델 호출 주체의 제삼자 attestation·무인 지속형 자율 운용 검증은 아직 없다.

## 4. 남은 T4 수락 조건과 다음 확정 작업

**상태: T4_CONNECTED_MCP_100_SESSION_PARTIAL_10_OF_100__OPERATIONS_DEPLOYED.**

- 같은 세션을 이어서 **11→100세대까지 실제 GPT 계획·진단·대조 실험을 매 세대 커밋**하고, 주기적으로 초깃값·세대/S7 hash·실험 실패율·최종 보고 정확성 검증. 90개 세대 미완료를 완료로 표시하지 않는다.
- 무인 실행/중단/재시작/예산 통제와 제삼자 모델 연결 증명, 동일정책·복수 시드 완전 사전등록 랜덤 vs GPT 비교 및 재현 가능한 연구효율 향상은 아직 T4 미수락 게이트.
- 기존 GPT 10과 난수 10 동예산은 개발용 제한 비교이며 GPT 우월성을 증명하지 못한다. 새로운 100세대에서 최상위 수익이 발견돼도 독립 PIT/OOS 봉인·수수료·유동성·다중검정 승인 전에는 수익 알고리즘 성공이나 거래 GO를 선언하지 않는다.
- 다음 순서 기존 인터뷰 잠금대로 **T4 11~100세대**. 완료 후 V01~V04 독립 원본/타임스탬프/OOS 증빙 → V06 주문없는 Paper → V07 3단계 별개 GO/NO-GO. 목적·우선순위 변경 없음.
