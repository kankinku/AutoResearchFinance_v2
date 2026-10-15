# Quant Autoresearch — 상시 진행 현황 및 잔여 작업표

갱신일: 2026-10-16 KST / 2026-10-15 UTC. 운영 런타임 `da2331d` 불변. V01 BLOCKED_UTC_DATE, V02 BLOCKED_EXTERNAL_EVIDENCE(`4c62d0d`); 다음 V03.
관련 문서: [기능 우선순위](autoresearch-feature-first-priority-2026-10-15.md), [개발 연대기](autoresearch-implementation-roadmap-2026-10-14.md).

**운영 원칙:** 기능 개발 우선, 최종 데이터·성과 검증은 마지막. 다만 코드 변경 때 기본 테스트·무결성 검사는 즉시 수행. 이 문서는 **매 작업 완료 시 직접 갱신·Git Push하는 고정 기준 문서**이다. 미검증을 완료로 표현하지 않는다.

## 1. 전체 작업 상태

| ID | 작업 | 현황 (2026-10-15) | 남은 기능 / 검증 |
|---|---|---|---|
| 1-1 | Nasdaq 날짜별 실제 원본 | **검증 진행·날짜 조건 BLOCKED:** 실제 보존 QQQ 원본 3본 무결성 통과, 1,508봉/본, 비교 3,016건·수정 관측 0건. 수집일 모두 2026-10-15 UTC, 상태 `INSUFFICIENT_COLLECTION_DAYS`. 동일 일 재수집 생략 검증, 증거 `5297994a…` | 최소 다른 UTC 날짜인 2026-10-16 00:00 UTC(한국 09:00) 이후 실제 독립 신규 수집·재감사. 당일 수집본 복제·날짜 조작 금지. 그 전에는 V02를 병행 |
| 1-2 | 독립 공급자 발표 시각 | **연구용 일괄 검증 개발 완료·외부 증빙 BLOCKED:** QQQ 3본 원본 재검증 3/3, 공급자 서명 0/3, 독립 공개시각 0, Databento AUTH_REQUIRED; 새 V02 CLI/변조/시각 차단 51 PASS(`4c62d0d`) | 실제 공급자 승인 키·발행/수신시각·이용권 계약·과거 시점 as-of 확인 필요. V03 진행 가능 |
| 1-3 | 배당·분할·가격 수정 게이트 | 부분 구현: QQQ 배당 25건 대조·분할 잔차 | 각 과거 의사결정 시점의 이용 가능성 |
| 2-1 | ChatGPT MCP 연구 도구 E2E | **운영 반영:** D07 32도구 사전 입력 검증 적용. 기존 URL/OAuth 및 32개 tool, Workspace READY, 기본 ChatGPT MCP, 주문 비활성(`da2331d`), 익명 401·앱 읽기전용 3종 확인 | 실제 모든 상태변경 도구 32개 호출 및 GPT 장시간 10~100세대 T4는 미실행. D03/D04/D06 Lab CLI는 MCP 도구로 미노출 |
| 2-2 | 실제 GPT 10~100세대 | **부분 구현:** GPT 2세대 실제·mock 10세대, 무거래 관측 ID 대응 및 최근 동일 Plan/Diagnosis 안전 재제출(`d9255d9`) | 실제 GPT 10/100세대·RUNNING 중단 복구·지속 실행 실증(T4 후순위) |
| 2-3 | 자율 장시간 실행·복구 | **부분 구현:** checkpoint·취소·재개·전경 실행기 + D02 `reconcile/resume` 멱등 복구 및 커밋 세대의 누락 S7 증거 복원(`86c2ccd`) | 실제 장시간 중단·중복 호출 내성 및 10~100세대 외부 GPT 실증(T4), 서버 배포·운영 리허설(T3) |
| 3-1 | 학술 지표 확장 | **부분 구현:** 내부 승인된 지표 수치 참조 + D04 비실행 연구용 FormulaNode 계산, 직접 계산/별도 스칼라 참고 결과 대조, 유한값·causal prefix 검증 및 버전별 SQLite 수치 증거 기록(`3723904`) | 실제 논문 원문·라이선스 검토, 확장된 학술 공식의 검증된 지표 라이브러리 등록 및 멀티마켓 제품 사용 미완료 |
| 3-2 | 논문 자동 수집·계산식 구현 | **부분 구현:** Crossref 탐색→D03 수식 제안→D04 수치 sandbox 검증(`52c5bfb`/`3723904`). 계산식이 테스트를 통과해도 `RESEARCH_NUMERIC_CROSSCHECK_ONLY` | 실제 원문·권리 독립 검토 및 운영 전략/브로커 실행 승인 불가; 연구 프로세스와 결합은 향후 과제 |
| 3-3 | LLM 가설·대조실험·무작위 비교 | **부분 기능 구현:** 기존 S7/S8 대조실험·방향 선택에 D05 실패 유형 분류·반증 우선순위·경쟁 설명·중복 자식 해시·세대별 S7 증거 연결을 GPT 다음 Plan 컨텍스트로 자동 재구성(`5a903e1`) | 진짜 무작위 대조군·독립 검증 및 GPT 장시간 자율 진화/실제로 더 높은 수익 성과 검증은 미완료 |
| 4-1 | 다자산·다시장 연구 | **부분 기능 구현:** D06 2~8개 지정 미국 ETF의 뉴욕 거래일 정합성·마감 관측 시각·다음 공동 09:30 오픈 계산·중복/결측/미완료 봉 거부, 동일 typed AlgorithmPlan의 종목별 StrategyIR 독립 비용 백테스트와 결과 해시 비교(`6fdf881`) | 실제 서로 다른 거래소·자산군 세션 정렬, 공통 계좌 자금배분 포트폴리오, PIT·기업행동 독립 확인, 운영 MCP 배포·실증 미완료 |
| 4-2 | 독립 OOS 검증 | 대기: 기존 walk-forward 구성은 있음 | 선택 과정 동결·봉인 OOS 검증 |
| 4-3 | 비용·유동성·우연 반영 순수익 | 대기: 백테스트/비용 기반은 있음 | 슬리피지·용량·다중검정 포함 |
| 5-1 | 브랜치 통합·MCP 배포 안정화 | **운영 배포 완료:** 통합 SHA `da2331d` 고정 Worktree, 배포 런처 `9c4749d`, 전체 Pytest 1605 PASS·Ruff·Mypy 252소스 PASS, 운영 venv HTTP/OAuth 13 PASS. 원 URL/OAuth와 이전 고정 소스·런처 백업 보존 | 실제 롤백 실패경로 리허설 미실행, 긴 GPT 10~100세대·T5 PIT/OOS·T6 paper 검증 잔여; D03/D04/D06은 별도 MCP 미노출 |
| 5-2 | 실주문 없는 페이퍼트레이딩 | 대기 | 실제 시점 추적·비주문 모의 체결 |
| 5-3 | 최종 목표 대비 승인 평가 | 대기 | 기능·안정성·독립 성과 GO/NO-GO |

## 2. 앞으로의 진행 순서

| 순서 | 작업 ID | 다음 실행 내용 |
|---|---|---|
| D01 | 2-2 | **코드 구현 완료:** 무거래 진단·동일 Plan/Diagnosis 최근 재제출 멱등 처리(`d9255d9`); 실제 GPT 장기 검증은 T4 보류 |
| D02 | 2-3 | **부분 기능 완료:** 중단 후 reconcile/resume 멱등 수신증, 누락 S7 복원·무결성 차단(`86c2ccd`); 운영/장기 실행 검증은 T3~T4로 보류 |
| D03 | 3-2 | **기능 개발 완료(실제 원문 검토 미진행):** DOI 검토 큐, 권리/방법론 기록, 비실행 수식 AST 제안 및 무결성 검사(`52c5bfb`) |
| D04 | 3-1 | **개발 기능 완료:** research-only AST evaluator, 별도 scalar numeric cross-check, 인과 prefix·입력 경계·버전별 증거 SQLite(`3723904`). 실제 전략 지표 승인/상용 운용 검증은 미진행 |
| D05 | 3-3 | **개발 기능 완료:** S7 evidence-bound 실패 지식·무효 가설 재사용 방지 힌트·다음 반증 설계 제안이 자동으로 GPT Plan 컨텍스트에 전달(`5a903e1`); 실제 모델 10~100세대 진화 실증 T4 보류 |
| D06 | 4-1 | **제한적 기능 개발 완료:** QQQ/SPY 포함 2~8 US ETF 동일 거래일·마감 시각 검증, 종목별 AlgorithmPlan→StrategyIR costed backtest 분리 실행, CLI preview·입력 해시 검증(`6fdf881`); 타 거래소/공동 포트폴리오/경제성은 미완료 |
| D07 | 2-1 | **개발판 계약/권한 테스트 완료:** 32개 정합성·정상/오류 입력 사전 검증, HTTP/OAuth·연구 세대 포함 69 PASS(`18c1bbb`); 실서버 부작용 포함 32개 전체 호출과 배포는 미실행 |
| D08 | 5-1 | **운영 적용 완료:** D01~D07 상속 코드와 새 릴리스 게이트를 `da2331d`로 배포. 기존 고정 소스 `cfc66cf`·런처 백업 유지. 운영 32도구·READY·기본 mcp·주문 off / 미인증 401 확인. T3 1605 PASS, 운영 venv 13 PASS, 추가 5 PASS |
| V01 (BLOCKED_UTC_DATE) | 1-1 | 기존 실제 3본·동일 날짜 2쌍 무결성 29 테스트 통과. 신규 다른 UTC 날짜 수집은 2026-10-16 00:00 UTC 이후에만 가능; 지금 원본 보존·강제 재다운로드 없음 |
| V02 (BLOCKED_EXTERNAL_EVIDENCE) | 1-2 | 실제 QQQ 원본 3개 중 공급자 서명 0/3, 과거 공개시각 0. Databento metadata AUTH_REQUIRED. 연구 전용 검사기·관련 51 PASS(`4c62d0d`); 실공급자 증거 전에는 PIT 불가 |
| **V03 (다음)** | 1-3 | 배당·분할·가격 정정의 의사결정 당시 as-of 이용 가능성/수정본 검증. V01 신규 수집은 2026-10-16T00:00Z 이후 |
| V04 | 4-2 | 봉인 OOS 순차 검증 |
| V05 | 4-3 | 수수료·유동성·통계적 우연 반영 |
| V06 | 5-2 | 페이퍼트레이딩 |
| V07 | 5-3 | 최종 운영 승인 여부 결정 |

시간·외부 공급자 때문에 막힌 항목은 `BLOCKED`라고 적고, 실행 가능한 D 순서를 진행한다.

## 3. 테스트 실행 순서

| 순서 | 시점 | 테스트 범위 |
|---|---|---|
| T0 | **매 기능 수정 직후** | 변경 기능 단위 테스트·실패 케이스·기본 권한 차단 |
| T1 | **매 작업 커밋 직전** | 변경 범위 Ruff·Mypy·관련 Pytest, diff 검사 |
| T2 | 기능 통합 시 | MCP Plan→Diagnosis→실험, 재실행/원장 일관성 |
| T3 | 배포 또는 기능 묶음 통합 직전 | 전체 Ruff·Mypy·Pytest·롤백 가능성 |
| T4 | 자율 엔진 개발 후 | 실제 GPT 10/100세대·장시간 복구 |
| T5 | **개발 종료 후** | 실제 원본/과거 발표 시각, OOS, 비용·통계적 신뢰 |
| T6 | **최후 단계** | 페이퍼트레이딩·최종 운영 평가 |

**검증 후순위의 의미:** T4~T6을 후순위로 두며 T0/T1을 생략하지 않는다. 장시간 전체 테스트는 중단 시 통과한 개수와 미완료를 분리 기록한다.

## 4. 완료 내역 (새 항목을 맨 위에 기록)

| UTC 날짜 | ID | 변경 및 실측 | 테스트 | 브랜치·코드 커밋·배포 |
|---|---|---|---|---|
| 2026-10-15 UTC | 1-2/V02 | 기존 발행자 서명 intake와 Nasdaq QQQ 아카이브 일괄 감사를 연결. 로컬 CLI `audit-qqq-publication-coverage` 신규. 실제 기존 3본 raw/Parquet/manifest 재검증, `PUBLISHER_PROOF_MISSING` 3건, 역사 독립 공개시각 0건. 보고 해시 `3d633431d8b5ab36105333807102caa8df695324730aa9fa2a1c94221ccff9a2`, Databento metadata `AUTH_REQUIRED`, PIT/주문 금지 유지 | 신규 V02 7개 포함 관련 **51 PASS**, Ruff/Mypy PASS. 운영 MCP 및 기존 원본/권한 변경 없음; 외부 시각/서명/계약 미확보 | `feat/v02-publisher-availability-matrix-20261016` 코드 `4c62d0d` Push, 상세 `autoresearch-stage-1-2-v02-publisher-availability-2026-10-16.md`, 증거 `docs/operations/evidence/quant-validation-20261016/v02-publication-coverage-audit.json`. V02 BLOCKED_EXTERNAL_EVIDENCE, 다음 V03 |
| 2026-10-15 UTC | 1-1/V01 | 기존 Nasdaq QQQ 2020-01-02~2025-12-31 실제 원본 3본을 모두 raw JSON/Parquet/manifest로 다시 감사: 3/3 검증, UTC 수집일 1일(10/15), 연속 비교쌍 2개·총 3,016 공통봉·관측 수정 0. Inventory 해시 `5297994a0c8fcff855437c84d12aa6c5e7bd530f5bd30dc1709dabf92752362c`. 같은 날 재수집 명령은 `ALREADY_COLLECTED_TODAY`로 fetch 생략. **실제 2일째 원본 수집은 아직 물리적 시점 미도래**(다음 2026-10-16T00:00Z). 증거 JSON 보존, 소스 수정/실주문/운영 재배포 없음 | 관련 기존 Pytest **29 PASS**(archive/daily/inventory/pair), Ruff/Mypy 대상 파일 PASS, 실제 2개 UTC 날짜 미충족; 역사 PIT·OOS·수익성 T5 미승인 | `feat/v01-qqq-utc-vintage-evidence-20261016`, 증거 `docs/operations/evidence/quant-validation-20261016/v01-qqq-collection-day-gate.json`, 상세 `autoresearch-stage-1-1-v01-utc-boundary-2026-10-16.md`, V01 날짜 의존 `BLOCKED`, V02 진행 가능 |
| 2026-10-15 UTC | 5-1/D08 | D01~D07 선형 개발 변경을 통합해 릴리스 게이트(고정 SHA·인증/핵심 데이터 모듈 불변·롤백 고정 source 검사) 구현. 고정 후보 `da2331d` 개발 GitHub Push, 별도 배포 checkout 런처의 SOURCE_ROOT/EXPECTED_SOURCE_SHA만 갱신(`9c4749d`)하여 실제 운영 MCP 교체. OAuth DB/URL pin/approval key 및 연구 원장 보존. PID cwd 새 고정 runtime 확인, 익명 401·OAuth metadata resource 유지, 앱 read-only 32/READY/기본 MCP/주문 off 확인 | 전체 Pytest **1605 PASS**, Ruff 전체 PASS·Mypy 252소스 PASS, D08 게이트 5 PASS, 실제 운영 Python venv HTTP/OAuth/MCP 13 PASS. T4 GPT 10/100세대·T5 PIT/OOS/수익성·T6 paper 및 실제 오류 시 롤백 리허설은 미실행 | 개발 `feat/d08-integrated-release-gates-20261016` 기능 `da2331d` Push 완료, 배포 `deploy/quant-mcp-d08-integrated-20261016` 런처 `9c4749d` Push 완료, **운영 DEPLOYED**. 상세 `autoresearch-stage-5-1-integrated-deployment-2026-10-16.md` |
| 2026-10-15 UTC | 2-1/D07 | 연결된 Quant MCP 도구 정의 32개와 운영서버 brief 32개 확인, Workspace READY·주문 false·기본 GPT MCP 방식. 실제 미인증 URL HTTP 401. 개발판 32개 JSON Schema 선행 검증과 민감 정보 없는 INVALID_TOOL_ARGUMENTS 차단(내부 dispatch 전), 32개 ABI 보존 | 신규 D07 5 PASS, HTTP/OAuth·학술 체크포인트·D01/D02/D05/D06 관련 **69 PASS**, Ruff/Mypy PASS. T3 전체·T4 GPT 장시간·T5 PIT/OOS·T6 paper 미실행. 실운영 상태 변경 32도구 호출 미실행 | `feat/d07-mcp-public-contract-gates-20261016`, `18c1bbb` Push 완료·운영 미배포, 상세 `autoresearch-stage-2-1-mcp-integration-2026-10-16.md` |
| 2026-10-15 UTC | 4-1/D06 | 두 미국 ETF 이상의 뉴욕 현지 거래일·마감 타임스탬프 정렬. 마감 전·거래일 누락·중복·주말·불일치·입력 변경 시 fail closed; 모든 종목이 마감 완료된 뒤에만 신호 생성, 다음 공동 개장 시각 표시. 동일 typed AlgorithmPlan에서 종목마다 기존 StrategyIR/비용 엔진 독립 실행 및 CLI 추가. 공동 포트폴리오 PnL 생성하지 않음 | 신규 D06 **10 PASS** + 기존 AlgorithmPlan **17 PASS** = **27 PASS**; Ruff·Mypy 변경 경로 통과. T3 전체 회귀·T4 실제 GPT 장기·T5 PIT/OOS/수익성·T6 paper 거래 미실행 | `feat/d06-multi-asset-session-alignment-20261016`, 기능 `6fdf881` GitHub Push 완료, 운영 미배포. 상세 `autoresearch-stage-4-1-multi-asset-alignment-2026-10-16.md` |
| 2026-10-15 UTC | 3-3/D05 | 커밋된 S7 결과와 original 세대 해시를 재검증해 실패 유형·원래 설명/대안·추가/제거/리사이즈 집계·중복 자식 해시·다음 대조 설계 우선순위 생성. Gateway의 매 GPT Plan 생성 시 읽기 전용 `experiment_learning`에 자동 포함. 인과 관계, OOS, 수익성 승인 없음 | T0/T1 신규 테스트 **17 PASS**, 기존 S8/MCP 포함 선별 회귀 **51 PASS**, Ruff/Mypy 2개 소스 PASS. T3 전체 저장소·T4 실제 GPT 장시간·T5 PIT/OOS·T6 모의거래 미실행 | `feat/d05-evidence-learning-20261016`, 기능 `5a903e1` Push 완료, 운영 미배포. 상세 `autoresearch-stage-3-3-evidence-learning-2026-10-16.md` |
| 2026-10-15 | 3-1/D04 | typed FormulaNode 단일자산 완료 봉 입력 sandbox 평가, 독립 scalar reference·prefix 확인, 1봉 후 적용 계약, 버전·수식/입력/출력 해시 묶인 SQLite RESEARCH_NUMERIC_CROSSCHECK_ONLY 증거와 CLI 2개 구현. 실거래·검증 지표 레지스트리와 격리 | 관련 Pytest **29 PASS**(D04 15·D03 8·S9 6), Ruff PASS, Mypy 변경 소스 2건 PASS; T3 전체 회귀, T4 실제 10~100세대, T5 PIT/OOS/수익성 및 T6 paper는 미실행 | `feat/d04-safe-research-formula-calculators-20261015`, `3723904` Push 완료; 운영 미배포; 상세 `autoresearch-stage-3-1-formula-calculators-2026-10-15.md` |
| 2026-10-15 | 3-2/D03 | 실제 Crossref DB에서 후보 상위 5개 `METHOD_REVIEW_REQUIRED` 확인. DOI·원본 해시 묶인 검토 이력, 초록/원문 접근·라이선스 상태, 버전별 비실행 수식 AST 및 CLI 구현. 실제 원문·라이선스 확인은 실시하지 않음 | Pytest **14 PASS**(D03 신규 8+기존 문헌 6), Ruff/Mypy 통과; T3 전체 회귀, T4 GPT 장시간, T5/T6 경제성 최종 검증 미실행 | `feat/d03-paper-review-spec-20261015`, 코드 `52c5bfb` Push 완료, 운영 미배포; 상세 `autoresearch-stage-3-2-methodology-spec-2026-10-15.md` |
| 2026-10-15 | 2-3/D02 | RUNNING gateway 장해 시 기존 cycle 세대·S7 실험 증거 복원 후 새 checkpoint 발급; reconcile/resume 결과 토큰·세대 해시 수신증으로 중복 복구 방지, 변조 시 fail closed. 기존 MCP 32개 불변 | 새 D02+이전 D01 관련 **8 PASS**, 기존 reconcile/resume **3 PASS**; Ruff/Mypy 변경 소스 PASS, 도구 32개 계약 확인. T3 전체 Pytest·T4 실제 GPT 장시간·T5/T6 최종 검증 미실행 | `feat/d02-gpt-recovery-reconcile-20261015`, `86c2ccd` Push 완료, 운영 미배포; 상세 `autoresearch-stage-2-3-crash-recovery-2026-10-15.md` |
| 2026-10-15 | 2-2/D01 | 동일 Plan/Diagnosis 재제출 시 최근 완료 단계·S7 기록만 반환, 다른 페이로드/오래된 토큰/레코드 변조 거부. 이전 세대 증거 보존, 도구 목록 32개 유지 | 신규·관련 선택 테스트 **8 PASS, 20 deselected**, Ruff/Mypy 통과, 32-tool schema 점검. T3 전체 회귀 및 T4 실제 GPT 10~100세대 **미실행** | `feat/d01-mcp-idempotent-submission-20261015`, `d9255d9` Push 완료, 운영 미배포; 상세 `autoresearch-stage-2-2-submission-replay-2026-10-15.md` |
| 2026-10-15 | 3-2 | Crossref 서지 탐색·후보 중복 제거·로컬 리뷰 큐. 선행 후보 5건 + 신규 관측 12건, API 429 중단·복구 대상 기록 | 관련 22개 통과, 변경 소스 Ruff/Mypy 통과. 전체 회귀 미실행 | `feat/s9-crossref-literature-pipeline-20261015`, `aef8f18`, Push 완료·운영 미배포 |
| 2026-10-15 | 1-1 | 실제 가격 원본 3회, 일별 멱등 보관 CLI | 관련 20개 통과·정적 검사 통과. 전체 Pytest 617건 PASS 후 중단 | `feat/p1-nasdaq-daily-archive-20261015`, `2fcde28`, Push 완료·운영 미배포 |

## 5. 매 작업 완료 시 필수 문서 갱신

1. 시작 시 이 문서의 ID/상태/다음 순서를 읽고 실제 코드·운영 상태를 재확인한다.
2. 기능 구현과 T0/T1을 수행한 뒤, 1번 표 상태·남은 조건, 2번 표 실행 순서, 4번 표 신규 작업 로그를 **모두 갱신**한다.
3. 변경 파일, 실제 테스트 통과/실패/중단/미실행, 알려진 위험, 별도 운영 배포 여부를 기록한다.
4. **코드 커밋·Push 후 확정 SHA를 문서에 기록해 문서 커밋·Push**한다. 문서 갱신이 실패하면 사용자에게 작업 완료로 보고하지 말고 상태를 명시한다.
5. 이전 상세 문서·증거 원장은 보존한다. 과거 데이터를 최신 수정판으로 덮어쓰거나, 불확실한 상태를 `완료`로 승격시키지 않는다.

업데이트 로그 양식: `UTC 날짜 | ID | 변경 기능·파일 | 실제 테스트 | 잔여 조건 | 브랜치/SHA/Push·배포 상태 | 다음 ID`.

## 문서 관리 작업 이력

- 2026-10-15: 15개 작업 현황, 개발·테스트 순서, 완료 시 갱신 절차를 문서화. 기준 커밋 `0bff84f` 원격 저장 성공. 문서 검사 15/15 ID 및 T0~T6 PASS, 전체 회귀 미실행(문서 변경).
