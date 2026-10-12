# Quant Autoresearch — CTO Lean MVP 개선 계획

기준일: 2026-10-12. 운영 커밋 3e9e499. 이 문서는 조사·계획 전용이며 기존 서비스·코드·인증·데이터를 변경하지 않는다.

## 제품 목표

한 문장의 요청으로 등록된 ETF 전략을 연구하고, 검증 가능한 결과와 실패 원인, 다음 실험을 이해하게 한다. 실거래 자동화나 수익률 보장은 MVP 범위 밖이다.

## 현재 상태

- Quant MCP 18개 도구, OAuth 메타데이터 HTTP 200, 비인증 MCP HTTP 401, Moon health HTTP 200.
- Workspace READY / paper / orders_enabled=false. Champion EMPTY, Frontier 0.
- Tiingo 제공 QQQ 개발용 일봉 1,508개. 데이터 품질 UNVERIFIED, KIS 미설정.
- 전략 입력 10개, 개발 데이터 파일 1개. 실제 전략과 데이터의 호환성 검증은 별도로 필요.
- 기록된 3개 배치·11세대: 후보 평가 21회 전부 REJECT, 해시 기준 고유 후보 9개, 중복 평가 12회. 과거 개선 패치 전 데이터.
- 탈락 게이트 발생: 견고성 20건, 검증 18건, 빠른 평가 17건, 전체 평가 9건, 연간 거래수 5건. 복수 중복 가능.
- Python 소스 346개, 테스트 파일 162개, 문서 131개. 대시보드에 이전 Codex/계좌·CLI 중심 UI가 남아 있으며 독립 대시보드 프로세스는 미확인.
- Ruff 통과. 직전 변경에서 Pytest 943 PASS 및 Mypy 183파일 PASS가 보고되었으나 이번 조사에서 전체 재실행하지 않았다.

## 설계 원칙

기존 Python, MCP SDK, Parquet, SQLite, Strategy IR, 백테스트, 불변 Evidence를 재사용한다. 새 프레임워크·브로커·데이터베이스·별도 LLM·정식 웹 UI는 만들지 않는다. ChatGPT 대화를 첫 제품 인터페이스로 사용한다.

## 문제의 우선순위

1. **P0 — 시작 흐름:** GPT가 기존 get_research_brief, preflight_research_batch, start_research_batch를 조합해 전략과 데이터 경로를 자동 선택한다. 선택지가 모호하면 질문은 한 개만 한다. 새 MCP 도구를 만들기 전에 기존 스킬을 활용한다.
2. **P0 — 진실한 상태:** READY는 서버 상태일 뿐 검증된 전략이 아니다. 서비스 준비, 실제 데이터, 선택한 전략의 실행 가능성, 성과 검증을 구분한다.
3. **P0 — 실패 이유:** 불변 Evidence에 있는 failed_gates와 기준값을 읽기 전용으로 집계한다. 사용자에게 상위 세 가지 실패 이유 및 한 가지 다음 실험을 설명한다. 추가 DB는 만들지 않는다.
4. **P0 — 표현 수정:** N세대는 GPT의 N회 신규 가설이 아니라 최초 고정 ResearchIntent 아래의 N차 로컬 탐색이다. 평가 횟수와 고유 후보 수를 분리한다.
5. **P1 — 중복 계산:** 기존 의미 해시를 이용해 이전 세대와 혼합된 중복 후보만 걸러낸다. 캐시가 평가 조건이 다른 결과를 재사용하지 않도록 데이터·모델·비용 버전을 고려한다.
6. **P1 — 탐색 소진:** 더 이상 신규 후보가 없으면 조기 종료하고 소진 사유를 표시한다. 성공 세대 수로 포장하지 않는다.
7. **P1 — 결과 품질:** development, UNVERIFIED, OOS NOT_MEASURED 등의 한계를 보고서 전면에 유지한다. 평가 기준을 성과를 만들 목적으로 완화하지 않는다.
8. **P2 — 유지보수:** 레거시 실행/복수 대시보드/병렬 워커는 변경을 동결하고, 실제 사용 여부 확인 후에만 제거한다. Jev Trader의 초저지연 주문 계층은 MVP에서 보류한다.

## 단계별 개발 계획과 완료 기준

**M0 — 사용자가 바로 시작하도록 한다 (P0).** 기존 QQQ 데이터·등록 전략 1개·탐색 변수 3~5개를 사용하는 대표 경로를 고정한다. 자연어 요청에서 호환 가능한 전략·데이터를 확인한 뒤 기존 preflight를 수행한다. 완료 기준은 사용자가 source_path, parent_ids, Parquet 경로를 입력하지 않고 한 문장과 필요 시 질문 하나로 연구를 요청하고 상태를 조회하는 것이다.

**M1 — 결과를 이해하도록 만든다 (P0).** 새 저장소 없이 Evidence를 집계하는 요약기를 만든다. 기존 21회 탈락 이력에서 후보 고유성, 판정 결과, 대표 탈락 원인과 실제 값/임계값, 데이터 품질, 다음 실험을 한국어로 출력한다. 완료 기준은 기존 탈락 사례 모두가 원본 Evidence와 연결되고 재현 가능하며 원장 수정이 없는 것이다.

**M2 — 의미 없는 반복을 줄인다 (P1).** 현재의 전체 세대 중복 생략을 유지하면서 부분 중복 후보 필터를 추가한다. 탐색 공간이 소진되면 정확한 중단 사유를 표시한다. 완료 기준은 동일 입력·seed의 재현성, 실제 평가 횟수와 집계의 일치, 데이터존 및 주문 권한 부정 테스트 통과다.

**M3 — 제품 가치를 검증한다 (P1).** 초기 대상 사용자 5명 정도에게 한 문장 연구 요청 → 결과 이해 → 다음 실험 선택 과정을 관찰하는 테스트를 **제안**한다. 이는 미실행 실험이다. 불편이 확인되면 프롬프트·UX를 먼저 바꾸고 새 시스템을 만들지 않는다.

**이후 검토 (조건부):** 여러 자산, 추가 데이터 제공자, Docker 운영 고도화, 별도 웹 UI, Frontier 자율 재계획, paper 주문 및 Jev Trader식 시장 이벤트. 독립 OOS 검증과 사용자 수요 없이는 실거래 확장하지 않는다.

## MVP 구조

사용자 자연어 → 기존 MCP 및 스킬로 소스·데이터 선택 → 기존 사전검증 → 기존 단일 배치 워커/평가 엔진 → 불변 Evidence → **작은 실패 원인·결과 요약** → 사용자.

Python, 기존 SQLite/Parquet/MCP, Strategy IR을 유지한다. 새 DB, 메시지 브로커, 마이크로서비스, 다른 AI 서비스, 새 프론트엔드 프레임워크는 필요 없다.

## KPI: 제품 가치 중심

North Star 제안: **실제 개발 데이터에서 고유 후보를 평가하고, 사용자에게 근거·다음 선택지를 전달한 완료 연구 건수**.

- 시작 성공률: 자연어 요청이 유효한 연구 배치로 이어진 비율.
- 고유 후보율: 중복을 제외한 실효 후보 / 생성된 후보. 기존 역사적 9/21은 해시 기준 참고치일 뿐이다.
- 해석 가능성: 리포트가 실패 원인과 측정값/기준을 설명하는 비율.
- 반복 선택률: 사용자가 결과를 보고 다음 실험을 명시적으로 요청하는 비율.
- UX 검증: 사용자가 짧은 결과만 보고 탈락 이유를 설명할 수 있는지.

## 안전·유지보수 릴리스 게이트

- Quant MCP 주소는 https://project-moon.taild689f9.ts.net/quant/mcp 로 유지. URL 영구 핀, 기존 OAuth DB·승인 키, Moon 원래 /mcp 경로를 보존한다.
- Tool schema 변경을 위해 주소 재등록이나 승인 키 재발급을 요구하지 않는다. 서버 반영, 앱/스킬 릴리스, 클라이언트 도구 캐시 문제를 구별한다.
- orders_enabled=false, sealed OOS 비노출, 개인정보/인증정보 차단, 주문 API 접근 금지를 유지한다.
- 수정 범위에 해당하는 회귀 및 경계 테스트·Ruff/Mypy·실제 MCP 읽기 스모크를 우선한다. 테스트 커버리지 100%를 목표로 하지 않는다.
- 작은 커밋으로 배포하며 서버 코드 배포와 ChatGPT 플러그인/스킬 패키지 릴리스를 별도로 보고한다.
- 이번 조사에서 신규 배치, 데이터 다운로드, 백테스트, 주문, OAuth 변경, 서버 재시작, 플러그인 업데이트를 실시하지 않는다. 문서 1개만 추가한다.

## 주요 구현 소유권

- 시작·상태·보고: application/research_batch_service.py, integrations/chatgpt_mcp_sdk.py.
- 데이터: application/market_data_service.py, core/data, orchestration/evidence.py.
- 후보·평가: experiments/identity.py, experiments/candidate_generator.py, orchestration/pipeline.py.
- 근거 요약: memory/evidence_knowledge.py, memory/evidence_store.py.
- 진단용 UI: dashboard/static/index.html, dashboard/static/app.js.
- 인증/배포: scripts/quant_public_url.py, scripts/run_quant_moon_http.sh, deployment/moon.

운영·수익성·실제 고객 효과 중 이번 조사로 검증하지 않은 항목은 이미 완료된 것으로 표현하지 않는다.

## M0–M1 Implementation (2026-10-12)

- M0: 기존 source/path/parent_id 식별은 get_research_brief를 사용하고, read-only preflight를 start 이전에 호출하는 **연결 플러그인 스킬 워크플로**로 안내. 새 MCP 도구/프레임워크 추가 없음.
- 입력 카탈로그의 ready_for_batch는 이제 readiness_scope=INPUTS_DISCOVERED_ONLY 및 requires_preflight=true를 함께 반환한다. 이는 입력 검색 가능 여부이지 전략 품질 검증이 아니다.
- M1: get_research_batch_report에 failure_analysis 필드 추가. 불변 Evidence 내 REJECT의 failed_gates, 실제 측정/임계값 예시, 발생 횟수, 원천 데이터 품질, 고유 후보 해시 수 및 대표 검토 제안을 읽기 전용으로 집계한다. 이유의 **인과관계는 UNKNOWN**, OOS는 NOT_MEASURED.
- 보고서의 reviewed gate는 실행을 자동으로 시작하거나 성과 개선을 보장하지 않는다. 복수 원인 집계/후보 해시 중복을 분리해 설명한다.
- 기존 batch DB schema, MCP 도구 이름·스키마, JWT/OAuth, 고정 URL, Evidence 기록, 평가자 규칙과 KIS 주문 권한은 변경하지 않는다.
- M2(혼합 후보 부분 중복 제거), M3(초기 사용자 검증), Docker 호스트 acceptance는 미완료로 유지한다.

## M2 구현 (2026-10-12 이후 별도 변경)

- 동일 배치·동일 데이터/비용/평가 설정 내 실행 의미(semantic Strategy IR) 기준으로 이전 세대와 겹치는 후보는 재평가하지 않는다. 새 후보가 섞여 있으면 해당 새 후보만 실제 평가한다.
- 기존 평가 runner, GenerationPipeline, train-only fold selection, Docker EvaluationJobRequest JSON 경계에 excluded_semantic_hashes를 선택적 내부 필드로 전달한다. 독립 배치 간 캐시나 불변 Evidence 수정은 하지 않는다.
- generation_history의 기존 JSON에 DUPLICATE_SKIPPED를 추가하되 리포트의 퍼널 상태 counts에서는 별도 duplicate_skipped와 total_skipped_duplicate_candidates로 표시한다. DB 마이그레이션 없음. Evidence attempt execution / generation 이벤트에도 실제 생략 횟수를 남긴다.
- Grid 고정 탐색 또는 파라미터 도메인이 없는 고정 후보가 전부 이미 평가됐다면 조기 종료한다. Random 탐색의 일회성 중복은 전체 공간 소진의 증거가 아니므로 조기 종료하지 않는다.
- 조기 종료 시 최종 상태는 COMPLETED이고, completed_generations가 requested_generations보다 적으며 stopped_early=true, stop_reason=SEARCH_SPACE_EXHAUSTED, unexecuted_generations가 공개된다. 미실행 세대를 완료로 계산하지 않는다.
- 세대별 새 후보가 없는 경우 NO_NEW_CANDIDATES를 계속 남긴다. sealed OOS/실거래 주문 권한은 변화 없다.
