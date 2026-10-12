# Quant Autoresearch 전수조사 및 Jev Trader 참고 개선 계획

- 조사일: 2026-10-12 (KST)
- 실제 서비스 워크트리: `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory`
- 조사 기준: `8b3d6c21b3939e2eabd2e9aefb7b1cc3d498785e` (`docs/mcp-phase3-5-1-state-inventory`)
- 범위: 읽기 전용 저장소·MCP 서비스·시장 데이터·연구 DB·보안 모드·시스템 모듈 조사 및 문서 작성
- 비범위: 주문 실행, 자격증명 출력, 계정 연결 변경, 실거래 활성화, 전략 생산 코드 수정, 외부 OOS 승인
- 상위 정본: `docs/architecture/quant-autoresearch-architecture-v1.0.md`, `docs/operations/mcp-current-state.md`; 정본은 이번 작업에서 수정하지 않는다.

## 1. 근거 및 실제 관측

| 분류 | 실제 관측 | 근거 / 판정 한계 |
| --- | --- | --- |
| 서비스 | Quant Streamable HTTP 프로세스 실행 중(`127.0.0.1:8787`), 비인증 `/mcp/` 요청 HTTP 401 | 프로세스, 소켓, 비인증 HTTP GET 확인. 실제 인증된 ChatGPT MCP 호출 전체 시나리오는 미실행 |
| 데이터 공급자 | Tiingo `configured=true`, KIS `configured=false` | `MarketDataService.provider_status()`를 직접 읽기 전용 호출. 구성 여부이지 신규 다운로드 성공 보증은 아님 |
| 시장 데이터 | `data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet`, QQQ 1,508개 일봉, development | `list_datasets()`/`validate_dataset()` 성공. 품질 `UNVERIFIED`, `revisions_not_as_of`, `corporate_action_adjustment_unverified` |
| 워크스페이스 | `READY`, mode `paper`, `orders_enabled=false`; Champion `EMPTY`, Frontier family 0 | `WorkspaceService.status()` 조회; 준비됨은 투자 성과 또는 데이터 유효성 보증이 아님 |
| 연구 기록 | 총 3개 배치 모두 COMPLETED, 합계 11세대, 기록된 후보 평가 21회, 매 세대 REJECT, 승계 0건 | `gpt-research-batches.sqlite`를 SQLite read-only 모드로 집계; 21회는 unique 전략 21개 의미 아님 |
| 후보 반복 | 한 5세대 배치에서 매 세대 1회씩 거부된 후보 반복; 다른 5세대 배치는 세대당 3회 평가, 모두 REJECT | `generation_history`; 실제 Strategy IR hash별 중복률은 상세 Evidence 기반 재검증 필요 |
| 산출물 | `strategies/imported` 10, `strategies/normalized` 10, `strategies/champions` 0, `strategies/generated` 0 | 파일 개수 확인; validated_manifest 0과 구조화 파일 수는 같은 지표가 아님 |
| 연구 증거 | 별도 `evidence.sqlite`, DB 이벤트 31건 | 이벤트 테이블 count; 독립적인 sealed OOS 또는 성과 승인은 확인되지 않음 |
| 워커 | 로컬 큐와 Docker 격리 실행 경로 구현; Moon 셸에서 Docker CLI 없음 | 실제 Windows/Docker 실습 acceptance는 미확인 |
| 검사 | Ruff PASS, Mypy 182 files PASS | 전체 Pytest는 안전 도구 단계에서 차단되어 결과 없음; 테스트 실패로 간주하지 않는다 |

## 2. 기능별 조사 결과

### 2.1 데이터 수집·검증

- `application/market_data_service.py`: `TiingoDailyProvider`, `KISDailyProvider`, 명시적 EOD 다운로드, 불변 Parquet 파일 명명, 파일 경로 격리, 기간 완결성 검사.
- `core/data/{contracts,quality,parquet,access,timebase}.py`: 데이터 버전·품질·provenance·시간축·접근권한 계약.
- 현재 데이터는 단일 QQQ EOD 원천 데이터다. 개별 종목 유니버스, 상장폐지 포함, 실제 거래소 휴일 검증, 법인행위의 독립 PIT 검증, 틱·호가·거래소 세션 기록은 완성됐다고 볼 수 없다.
- 개선은 데이터 공급자를 새로 처음 만드는 것이 아니라 **기존 ingest → validate → research 입력 연결 및 품질 게이트 강화**다.

### 2.2 전략 연구 및 세대 실행

- `application/research_batch_service.py`: 1~100세대 비동기 배치, 한 번에 한 워커, 단일 외부 ResearchIntent, 최대 4개 parameter domain/각 24값, 상태·ETA·취소·세대 결과 DB 기록.
- `application/research_batch_worker.py`: 분리된 subprocess에서 세대를 실행한다. 워커 강제 종료 시 INTERRUPTED 처리하며 자동 재개는 미구현.
- `orchestration/evaluation_runner.py`, `application/evaluation_service.py`, `runtime/evaluation_executor.py`: local_scheduler 및 Docker worker 평가 경로. 실제 Docker 경로 검증은 별도.
- `research/llm/provider.py`: 서버 내 임의 원격 LLM 호출은 제거. ChatGPT가 계획한 하나의 의도만 고정해서 여러 세대를 실행한다.
- 현재 주요 기능적 간극: 배치 세대 숫자가 곧 독립적인 후보 다양성·효과적인 진화를 뜻하지 않는다. 고정 intent와 좁은 parameter domain으로 이전에 거부된 동일 후보를 반복 평가할 수 있다.

### 2.3 검증 및 연구 상태

- Strategy IR 원본, mutation, 평가/견고성, provenance, immutable Evidence, Frontier 등 구현된 기반이 있으므로 중복 재구축을 금지한다.
- `docs/operations/finance-improvement-execution-plan.md`와 `finance-improvement-full-acceptance-gaps.md`의 T-002~T-014 잔여 과제가 아직 전체 완료되지 않았다.
- 개발 데이터의 walk-forward/후속 홀드아웃은 독립 sealed OOS와 구별해야 한다. 데이터 누출, 통계 검정, 출처 유효성 검증은 아직 외부 실증을 요구한다.

### 2.4 실거래·운영 경계

- MCP는 인증 필요. 연구 도구에 주문 권한이 없고 현재 `orders_enabled=false`.
- KIS 주문과 연구의 권한 경계, 별도 승인 게이트는 유지한다. 새로운 실시간 이벤트 기능도 기본값 read-only/paper-only.
- 현재 Moon 환경에서 Docker CLI가 보이지 않아 실제 격리 워커 및 장애 복구에 대한 엔드투엔드 호스트 검증은 못 했다.

## 3. 설계 원칙: Jev Trader에서 선택적으로 참고할 것

| Jev Trader 기법 | Quant에 적용 방식 | 그대로 복사하면 안 되는 부분 |
| --- | --- | --- |
| WebSocket + HTTP polling fallback(`chain.ts`) | 데이터 스트림 끊김 감지, 재연결 및 시퀀스/누락 복구 | Monad 블록 높이·300ms 매매 주기는 한국/미국 증권사 API에 부적합 |
| 저지연 order book 조회(`book.ts`) | 호가 snapshot/delta 표준화, latency 측정, 데이터 해시 | Kuru ABI와 RPC 호출 규격 |
| 거래 전송·영수증 분리(`market.ts`) | Intent → Order → Ack → Fill/Cancel/Reject 상태기계, idempotency key, 재조정 | Kuru `batchUpdate`, gas/nonce, on-chain post-only 특성 |
| 실시간 의사결정 및 체결 이벤트(`trader.ts`) | Strategy Signal → Risk Gate → Execution Plan → Paper Fill → Ledger | 블록마다 반드시 buy/sell하는 정책. HOLD와 무주문은 정상 행동이어야 함 |
| SSE 이벤트 서비스(`server.ts`) | 상태·지연·체결·위험·연구 결과 모니터링 | 임의 사용자에게 내부 키/계좌/연구 지표 노출 |

실시간 주문 엔진을 붙이기 전 `Research Strategy IR`과 `Execution Signal` 및 `OrderRequest`를 분리하고, 모든 실제 주문은 기존 별도 권한 경계를 통과하도록 한다.

## 4. 개선 단계, 의존성, 완료 기준

| ID | 우선순위 | 작업 / 위치 | 선행 조건 | 객관적 완료 기준 |
| --- | --- | --- | --- | --- |
| A0 | P0 | baseline·운영 관측 확보 (`application/workspace_service.py`, `integrations`, `dashboard`, `state` 읽기 전용) | 없음 | 공개 MCP 17개 노출 도구의 schema/권한/오류 계약 비교; 인증·비인증, 각 read-only 도구 응답; 세대·후보·중복·상태 지표 재현 |
| A1 | P0 | 데이터 파이프라인 연동/품질 (`application/market_data_service.py`, `core/data/`) | A0 | Tiingo/KIS 구성별 ingest→validate→run preflight, provider 장애 negative test, 개발 데이터 원본/보정 구분, 종목·기간·세션·중복 품질 규칙; 데이터 출처/원본 해시 보존 |
| A2 | P0 | 후보 중복/진화 정정 (`application/research_batch_service.py`, `experiments/`, `memory/`) | A0,A1 | 후보 IR 실행 의미 hash 기준으로 동일 배치 중복 평가를 회피/명시; 평가횟수·고유 후보·재활용 cache HIT 별도 기록; parameter domains가 다른 후보 생성 재현 테스트 |
| B1 | P1 | train-only 생성/검정 보강 (`orchestration/train_only.py`, `evaluation/`, `core/validation/`) | A1,A2 | 각 fold의 입력 시점 준수, 라벨 overlap purge/embargo 필요 시 적용, 봉인 OOS 접근 차단 negative test, 비용·슬리피지·통계 추정 검증 |
| B2 | P1 | 세대 진화/Frontier/Rescue (`research/`, `experiments/`, `memory/`, `application/research_batch_service.py`) | A2,B1 | 탐색·활용·구조변이·부모전략 도입을 실제 후보 계보로 구분; 동일 성과가 없는 세대의 대안 가설 동작; 점수만으로 승계/Champion 자동 승인 금지 |
| B3 | P1 | 워커 회복·자원 통제 (`runtime/{persistent_queue,evaluation_executor,recovery_state}.py`) | A0,B1 | 중복 실행 없는 재시작/중단/재시도, 실패원인·ETA, subprocess와 Docker 호스트 검증, 데이터 read-only 마운트, 예산/타임아웃 테스트 |
| C1 | P2 | 시장 스트림/표준 이벤트 (`integrations/market_data_*`, 신규 분리된 market-events 어댑터) | A1,B3 | read-only WebSocket/poll fallback, heartbeat, gap detection/backfill, 원천 timestamp/수신 timestamp 분리, 처리 지연 p50/p95 기록 |
| C2 | P2 | 주문 상태기계·위험 게이트 설계 (`deployment/paper/`, `integrations/kis/` 별도 계층) | C1,B1 | HOLD·거부 정상 처리; 중복 주문 방지; 잔고·거래시간·최대 포지션·당일 손실 한도·긴급 중지; 주문/체결/잔고 대조; paper만 테스트 |
| C3 | P2 | 모니터링·관측 (`dashboard/`, `integrations/chatgpt_mcp_sdk.py`) | A0,C1,C2 | 연구 상태와 실제 평가 결과 분리; 실시간 quote/fill/risk/latency 이벤트; 최소 권한 및 비밀정보 미노출 |
| D1 | P3 | 독립 OOS·최종 승인 (`core/validation`, `memory/promotion`, `deployment/live`) | B1~C3 | 독립 데이터·sealed OOS·전략 해시·수동 승인, 주문 프로세스 권한 검토, 별도 paper/host acceptance. 이 계획만으로 live 활성화 금지 |

## 5. 첫 번째 구현 묶음: A0 → A1 → A2

1. 기존 데이터가 실제 연구에 전달되는지 **read-only preflight**로 확인하고, 누락 원인을 `PROVIDER_NOT_CONFIGURED`, `DATA_FILE_NOT_FOUND`, `INVALID_DATASET`, `PARENT_ID_MISMATCH`, `INSUFFICIENT_HISTORY` 등으로 분리한다.
2. 연구 배치 시작 전 dataset version/hash, 전략 ID, 정책, 예상 자원, 생성 가능한 고유 후보 수를 명시하는 preflight 보고를 추가한다. 잘못된 설정은 워커를 시작하기 전에 실패해야 한다.
3. 세대 결과의 `requested`, `evaluated_candidate_instances`, `unique_candidate_count`, `cache_hits`, `duplicate_skipped`, `eligible_successor`, `rejection_reasons`를 각각 집계해 사용자가 5세대=5가지 전략으로 오해하지 않도록 한다.
4. 후보 선택/변형의 dedup은 실행 의미의 Strategy IR fingerprint 및 데이터·Evaluator·비용 모델 버전을 사용한다. 유효한 반복 실험은 별도 허용 옵션으로 명시하고 결과를 구분한다.
5. 같은 데이터와 seed로 재현되는 단위 계약과 다른 parameter domain에서 다른 후보가 생성되는 테스트를 먼저 작성한다. 실제 `start_research_batch`를 호출하기 전에 모의 fixture에서 검증한다.

## 6. 합격 게이트

- 모든 구현 변경은 실패를 증명하는 테스트부터 작성한다. 전부 통과한 뒤 atomic commit, 독립 review, 최종 변경/문서/배포 영향 보고.
- 기본 개발 검증: `.venv/bin/python -m pytest -q`, `.venv/bin/ruff check .`, `.venv/bin/mypy .`. 이번 조사에서 Pytest는 안전 도구 차단 때문에 미실행이므로 이후 별도 실행 필수.
- 실제 데이터 검증은 1,508개 QQQ 일봉을 기반으로 하되, 이는 **개발용 비검증 단일 ETF 샘플**이다. 성과 검증용 독립 OOS로 사용하면 안 된다.
- 실행/복구 검증은 local_scheduler 테스트와 실제 Windows/Docker Desktop 호스트 승인을 분리한다.
- 금융 안전성 게이트: `orders_enabled=false` 유지, 주문 API 불접근·인증정보 미노출·sealed OOS 접근 불가 부정 테스트. 인간 승인 없는 live 주문 0건.
- Jev Trader 기술 도입 수락은 거래 속도가 아니라 **데이터 정합성, 재현 가능한 상태 전이, 잔고 대조, 안전한 취소/복구, 실거래 비용 모델**로 판단한다.

## 7. 미해결·검증 제외

- 전체 Pytest 실행 결과: 미확인(요청이 도구 안전 검사에서 차단됨). Ruff/Mypy만 통과.
- 인증된 ChatGPT 플러그인 경유 end-to-end 도구 호출: 이 조사에서 별도 로그인/토큰을 사용하지 않았으며 미확인.
- Tiingo 신규 API 다운로드 성공률, KIS 계정/증권사 API 연동: 미실행.
- 외부 원천/기업행위/미상장 종목 포함 PIT 검증 및 수익성: 미확인.
- 실제 KIS paper order, 실거래, Docker 재시작/타임아웃, 윈도우 호스트 acceptance: 미실행.
- 이번 조사는 **연구·실행 시스템 개선 계획**만 확정한다. 거래 활성화 및 기존 정본 구조 변경은 포함하지 않는다.

## 8. 구현 1차 완료 기록 (2026-10-12)

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| A0 서비스 진단 | PARTIAL | Moon 프로세스/데이터/연구 SQLite와 API 정적 점검; 별도 인증된 ChatGPT UI 도구 재검색은 클라이언트 상태에 의존 |
| A1 입력 검증 | DONE (범위 한정) | `preflight_research_batch`가 개발용 Parquet와 series zone을 검사, 데이터 해시·품질 공개, 워커 이전 오류 차단; 독립 PIT/법인행위 검증은 미완료 |
| A2 중복 회피 | PARTIAL | 동일 배치에서 세대 전체가 기존 전략과 중복일 때 평가 생략/증거 기록; 혼합된 신규+중복 후보의 부분 필터링 및 전역 캐시는 후속 과제 |
| MCP public URL 안정성 | DONE (코드/로컬) | `scripts/quant_public_url.py`의 영구 핀 검증, drift/missing-pin/missing-key fail closed, 기존 OAuth 상태 유지 |
| Jev Trader C1~C3 | PENDING | 초저지연 데이터 스트림/주문 엔진은 아직 도입하지 않음; 연구 주문 권한 비활성 유지 |

인증과 공개 endpoint 검증은 배포 후 결과를 별도로 기록한다.
기존 13-tool canonical stdio ABI는 그대로 유지하며 ChatGPT MCP 도구만
`preflight_research_batch`를 추가한다. 신규 도구 계약 갱신은 공개 URL의
변경이나 사용자 OAuth 클라이언트 재등록을 요구하지 않도록 한다.
