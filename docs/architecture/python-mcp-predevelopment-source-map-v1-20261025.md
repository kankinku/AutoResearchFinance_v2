# Python MCP 개선 포크 — 개발 전 소스 전수조사 및 아키텍처 기준서 v1.0

**조사 기준:** 2026-10-25 KST · **새 포크 `kankinku/AutoResearchFinance_PythonMCP`의 `main`, 사전 조사 기준 SHA `c2cc3d8`**
**작업 유형:** T4-PY-MCP-INVENTORY-01 — **문서·정적 분석 전용**. 기능 추가·서버 설정 변경·모델 로그인·실거래·연구 세대 생성 없음.
**결정 상태:** 기존 동작의 발견 사실은 *CONFIRMED CODE/OBSERVED*; 통합·삭제·인증 변경은 **PROPOSED / NOT IMPLEMENTED**.
**관련 목표:** 원본 20문답 Q02·Q05·Q06·Q08·Q09·Q10·Q11·Q15·Q17·Q20, 고정 V05→T4→V01~V04→V06→V07.
**목적:** 새로운 Python·GPT 결합 연구 루프를 만들기 전에 전체 코드의 소유권, 연결 방식, 재사용 가능성, 중복 위험, 검증 경계 및 실제 미완성 부분을 파일 단위로 파악한다.

## 0. 이 문서를 읽는 순서와 자동 생성 색인

1. `AGENTS.md`: 변경 불가 범위·보호 디렉터리·진짜 연구 세대 정의
2. `docs/decisions/2026-10-14-autoresearch-interview-20q.md`: 사용자의 원래 20개 답변 — 수정 금지
3. `docs/decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md`: 명시적으로 고정한 범위/순서/승인권
4. `docs/architecture/quant-autoresearch-architecture-v1.0.md`: 기존 승인된 아키텍처 — 변경 금지
5. `docs/operations/autoresearch-master-progress.md`: 작업 완료/진행/차단 사유
6. **본 문서**: '실제로 어느 파일을 재사용해야 하는가?'에 대한 탐색 지도
7. **[`python-mcp-file-inventory-20261025.tsv`](python-mcp-file-inventory-20261025.tsv)**: 추적 파일 **1,107개 전부**, 경로/역할/크기/행 수/SHA-256 앞 12자리/Python 최상위 심볼/내부 import 수
8. **[`python-mcp-python-import-edges-20261025.tsv`](python-mcp-python-import-edges-20261025.tsv)**: Python의 **정적 내부 import 관계 2,051개** (source file → imported module). 동적 로딩·런타임 호출을 포함하는 완전한 콜그래프는 아님.
9. [실제 신규 MCP 클라이언트 P0 실행/격리 보고서](../operations/python-mcp-hybrid-fork-bootstrap-20261025.md).

**정적 범위:** `git ls-files` 기준 **1,107개 파일**, 이 중 Python **679개 = 일반 소스 351개 + 테스트 328개**, Markdown 문서 306개, Markdown 이외 문서(JSON) 34개 등. 문서·테스트가 많은 저장소이므로 새 기능 개발보다 기존 모듈 재활용이 우선이다. **전체 1,107개 파일의 존재/크기/해시 및 Python AST/import는 자동 조사**했지만, 각 파일의 모든 분기·실행 동작을 1개씩 E2E 테스트한 것이 아니다. 바이트 동일 그룹은 빈 `.gitkeep` 한 그룹이며 **의미상 중복 부재를 증명하지 않는다**. 조사 코드가 Git 추적 대상만 읽으므로 무시된 런타임, 비공개 계정 자격증명, Moon MCP 서버 본체 내부 소스는 범위 밖이다.

## 1. 무엇이 'Moon'이고 무엇이 'Quant'인가

```text
ChatGPT / 미래의 Codex (모델 호출·가설·진단: 사용량 한도)
           |               |
      Moon MCP          Quant AutoResearch MCP  (서로 다른 도구·권한)
   원격 파일/명령/작업      연구 서비스 API, 거래/증거, 32 ChatGPT 도구
           |               |
     Moon 호스트          Quant 애플리케이션
     /shared/...          AcademicMCPCheckpointService 등
           |
     별도 Git 포크 작업공간
     /shared/moon-workspace/AutoResearchFinance_PythonMCP
           |
     Python 직접 MCP 클라이언트 (모델 호출 0회)
       -> 새 포크 안에서 'Quant MCP' 자식 프로세스 STDIO
           -> 포크-local state/python-mcp/ (새 연구 미개시)
```

| 실체 | 실제 위치/근거 | 책임 | 절대 혼동하지 말 것 |
|---|---|---|---|
| **Moon MCP** | ChatGPT 도구 네임스페이스 `mcp__moon__`, 현 노출 도구 **38개** | 원격 프로세스·파일·Git·작업 통제 | Moon 자체는 투자 전략 연구 엔진이 아니다. Moon MCP 서버 전체 내부 구현 소스는 이 Quant Git 저장소에 없음 |
| **Quant AutoResearch ChatGPT MCP** | 현 `mcp__Quant_AutoResearch__` **32개**; `integrations/chatgpt_mcp_sdk.py` | Quant의 정식 연구 도구·시장 데이터·실험 | 기본 Quant MCP의 state와 별도 P5 state가 자동으로 같지 않음 |
| **원본 Quant Git** | `kankinku/AutoResearchFinance_v2`; 원래 기능·증거의 upstream | 원본 기준선 | 원본에 개선 포크 전용 코드를 역으로 push하지 않음 |
| **원본 P5 세션 원장** | `/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024` | 기존 **28/100** 실제 GPT작성 세대 | 새 포크로 복사·이관·카운트 병합 금지. 마지막 확인 원장 상태 28/100 |
| **새 포크 Git** | `kankinku/AutoResearchFinance_PythonMCP`, `main` | 개선 Python-MCP 실험만 | GitHub native Fork 표시는 아니고 upstream 커밋 이력 보존 별도 repo |
| **새 포크 Moon 폴더** | `/shared/moon-workspace/AutoResearchFinance_PythonMCP` | 작업본·코드·테스트 | 물리적으로 Moon 호스트 내부에 있으나 Moon MCP 자체 복제본은 아님 |
| **새 포크 상태** | `<포크>/state/python-mcp/` | 독립 상태·캐시 | 현재 `NOT_INITIALIZED`, GPT 자동 연구 0세대 |
| **Codex Python SDK** | 공식 외부 클라이언트 라이브러리, 저장소 내부 없음 | 미래 GPT 실행자 후보 | Codex의 ChatGPT 플러그인 UI와 Python 프로세스의 인증·MCP는 별도. 새 포크 내 Codex 로그인/SDK 실측 성공 아님 |

**실측 P0:** `scripts/python_mcp_probe.py`로 **STDIO 13 도구 인식, 173개 지표 조회, `NOT_INITIALIZED`, `model_calls: 0`, `orders_enabled: false`**. 단 `model_calls:0`은 해당 코드 경로에 모델 API 호출이 없는 사실을 설명하는 클라이언트의 고정 메타데이터이지, 독립적인 계량 서비스의 사용량 영수증이 아니다.

## 2. 가장 중요한 '정식 실행 경로' — 새로 만들지 말 것

### 2.1 Quant ChatGPT MCP (기존 32도구 외부 플러그인)

```text
integrations/chatgpt_mcp_http.py   (원격 Streamable HTTP, OAuth/Bearer)
                  또는
integrations/chatgpt_mcp_stdio.py  (STDIO, 외부 터널 별도)
          -> integrations/chatgpt_mcp_sdk.py::ChatGPTMCPAdapter
          -> integrations/codex_mcp_sdk_server.py::SDKMCPServerAdapter
          -> integrations/codex_mcp_core.py::CodexMCPServer._dispatch
          -> application/*Service / AcademicMCPCheckpointService
          -> core, research, evaluation, memory, state
```

- ChatGPT용 `chatgpt_tools()`: **32개**, 실제 플러그인 도구 표면.
- **HTTP 보안 소유자** `integrations/chatgpt_mcp_http.py`, `integrations/quant_oauth.py`; Bearer/OAuth·범위 점검, 신뢰 터널/배포와 역할 분리. `integrations/quant_mcp_diagnostics.py`는 MCP 진단; `integrations/mcp_context_budget.py`는 반환 컨텍스트 크기 제한.
- `scripts/run_quant_moon_http.sh`, `deployment/moon/quant-mcp.supervisor.conf`, `scripts/quant_public_url.py`는 기존 운영 터널/프로세스 관리 참고. **고정 URL·기존 OAuth를 새 포크 개발 때문에 수정하지 않는다**.

### 2.2 Quant Codex MCP (별도 13도구)

```text
integrations/codex_mcp_server.py::main
  -> integrations/codex_mcp_sdk_server.py::main / SDKMCPServerAdapter
  -> integrations/codex_mcp_core.py::_tools (13개)
  -> 동일 CodexMCPServer._dispatch
  -> 동일 application services
```

- `.codex/config.toml.example`: Codex STDIO 연결 예시; 상대 `--project-root .`, `--state-dir state`, `uv run --locked`가 **정확한 새 포크 P5/독립 상태 지정이라고 가정하면 안 된다**.
- `integrations/codex_mcp_manual_server.py`, `codex_mcp_manual_adapter.py`, `codex_mcp_protocol.py`: **이전 수동 newline JSON-RPC·명시적 emergency rollback/호환용**, 신규 정식 서버로 복제 금지.
- `integrations/codex_mcp_payload.py`: 서버 응답 직렬화, `integrations/codex_mcp_sdk_server.py::_safe_academic_checkpoint_error`: 공개할 수 있는 에러 코드로 치환하는 fail-closed 처리.
- **주의:** Codex MCP `_tools()`의 13개와 ChatGPT 플러그인 `chatgpt_tools()` 32개는 같지 않다. 새 Python 클라이언트가 13개를 발견했다고 ChatGPT 외부 32도구의 계획/진단 제출 API 전체를 사용할 수 있는 것은 **아니다**. G29~를 자동 실험하려면 승인된 제출 인터페이스의 별도 동등성 점검이 선행되어야 한다.

### 2.3 신규 Python MCP (현재 실험 포크에만 존재)

```text
scripts/python_mcp_probe.py
    -> integrations/python_mcp_direct.py::QuantMCPDirectClient.probe
       -> mcp.client.stdio.stdio_client + ClientSession
       -> 같은 포크 integrations.codex_mcp_server (자식 프로세스)
       -> get_workspace_status, list_features
       -> 출력 JSON (read only, no LLM)
```

- `QuantMCPSettings`는 state가 **같은 포크 `state/` 하위**인지, 전달 세션 ID 형식이 올바른지 확인. 기존 P5 경로는 거부.
- `PUBLIC_READ_TOOLS`는 3개뿐이며 실제 `probe`는 상태·지표 2개 호출. 현재 Codex 공개 13도구에는 get_algorithm_research가 없다. 클라이언트 허용목록에만 이름을 추가해도 실행은 불가능하다. 향후 별도 도구 계약 동등성 검증이 필수다.
- 클라이언트 자체의 `require_read_only_tool`은 **클라이언트 측 허용목록**이다. 자식 MCP 서버가 전체적으로 읽기 전용 서버로 격리됐다는 증거는 아니다. 향후 신뢰 경계를 강화하려면 **서버 측에서 도구 목록 자체를 제한**하거나 OS 별도 권한이 필요하다.
- 자식 환경변수에는 OS 최소 항목과 해당 세션용 P3/P4/S7만 전달. 새 fork-local 상태임에도 원래 P5 세션 ID로 직접 접근하는 API는 불허.

## 3. 한 세대의 실제 알고리즘 연구 처리 경로

**유일한 '정식 GPT 증거/계수' 기준은 `application/academic_checkpoint_service.py::AcademicMCPCheckpointService`를 통한 적격 세대**다.

```text
AcademicMCPCheckpointService.start/get (line 701 / 2061)
  -> get.model_context: 검증 지표·부모·중복·증거·계획 토큰
  -> 외부 실제 GPT가 ResearchIntent/AlgorithmPlan 작성  [모델은 서비스 내장 아님]
  -> submit_plan (2565)
     -> strategy_ir/schema.py::StrategyIR 및 typed Intent
     -> research/llm/inherited_feature_compiler.py
     -> core/features/registry.py  (173 registry)
     -> research/llm/t4_feature_units.py  (STC 실제 0..1 도메인)
     -> core/backtest/engine.py + core/costs/*  (비용 포함)
     -> research/llm/s2_execution_preflight.py  (실제 체결 변화)
     -> opt-in require_trade_activity  (완료거래 0건이면 계획 전 차단)
  -> 반환 model_context.metrics / 실제 손익 거래·비체결 decision IDs
  -> GPT가 관측 trade/decision ID로 DiagnosticResponse 가설 제시
  -> submit_diagnosis (2705)
     -> research/llm/diagnostic_research.py
     -> research/llm/s7_quality_gate_p4_3.py + evaluation/academic_s7_risk_replay.py
     -> 동일 데이터 S7 통제실험 실제 수행·계수 게이트
     -> SQLite checkpoint / 증거 SHA 및 계보 커밋
  -> get (재조회) -> 다음 세대 AWAITING_PLAN
```

핵심 메서드: `start:701`, `get:2061`, `_stage_inherited_plan:2311`, `submit_plan:2565`, `submit_diagnosis:2705`, `reconcile:2972`, `resume:3388`. **현 코드 시점의 줄 번호**이며 코드 수정에 따라 달라질 수 있다.

- **실제 부모 계승** `research/llm/parent_portfolio_v2.py`, `generalization_parent_v1.py`, `lineage_selection.py`, `lineage_replay.py`; 거래·신호 동일 중복 차단 `s2_execution_preflight.py`, `p3_semantic_preflight.py`.
- **대조·S7** `research/llm/s7_quality_gate_p4_3.py`, `p4_random_candidate_control.py`, `research/llm/diagnostic_research.py`.
- **단위/무거래** `research/llm/t4_feature_units.py`: STC percentile 특수 단위는 0..1, 미등록 다른 지표의 출력 범위는 임의로 정하지 않는다.
- **증빙** `research/llm/model_provenance_v1.py`, `integrations/quant_mcp_diagnostics.py`, `core/integrity/{hashes,audit}.py` 및 서비스 SQLite. Model host가 본인 서명을 남긴다고 독립 제공자 서명을 갖는 것은 아님.
- **기존 P5 28/100**은 외부 원본 상태 기준. 새 포크의 연구 세대는 이 사실을 도용하거나 누적할 수 없다.

## 4. 헷갈리는 여러 연구 실행 서비스 — 목적을 구분하자

| 위치 | 이미 하는 일 | 그 기능을 신규 개발에 그대로 '세대 완결'이라고 쓰면 안 되는 이유 |
|---|---|---|
| `application/academic_checkpoint_service.py` | **현재 P5의 증거 기반 계획→백테스트→실제 GPT 진단→S7→정식 계수** | **우선 재사용**할 정확한 연구 세대 서비스 |
| `application/gpt_guided_research_service.py` | `start/get/submit/reconcile` 타입의 guided 연구·별도 SQLite | 정식 academic P4/S7와 동일한 원장·완료 조건이라고 증명되지 않음 |
| `application/chat_directed_research_service.py` | 채팅 지시 기반 `run` | 호출 단계 간 model provenance 및 GPT 진단 완결을 보장하지 않음 |
| `application/research_batch_service.py` + `research_batch_worker.py` | 사전 후보·배치 preview/start/status/resume/cancel/report | 모의/계획된 후보 배치 실행을 실제 GPT 세대로 집계하면 안 됨 |
| `runtime/research_loop.py`, `runtime/research_generation.py` | 이전 연구 루프·작업 제어 기능 | `AcademicMCPCheckpointService`의 checkpoint/S7 계수 경로와 성격 다름 |
| `orchestration/generation.py`, `orchestration/pipeline.py` | 평가·세대 실행 구성요소 | 상위 GPT 호출·증거 완결 기준을 새로 정의하지 말고 검증된 실행 부품만 재사용 |
| `application/t4_checkpoint_orchestrator.py` | 컨텍스트·계획·진단 콜백 연결 인터페이스 | **운영 콜백을 `EXTERNAL_MCP_UNVERIFIED`로 차단**, mock은 TEST_ONLY만 통과 |
| `application/t4_model_host_preflight.py` | 읽기 전용 모델 호스트 준비도 판단 | 모델을 실제 호출하거나 자격증명을 발급하지 않음 |

**설계 원칙:** 개선 포크에 **새 연구 엔진을 만들지 않는다**. 오직 검증된 실제 모델 응답을 `AcademicMCPCheckpointService`의 기존 계약에 전달하는 *얇은 Python 제어기*만 검토한다.

## 5. 실제 GPT 호출 코드는 이미 어디에 있는가?

| 파일 | 존재하는 인터페이스 | 현재 유효성·재사용 판단 |
|---|---|---|
| `research/llm/provider.py::GPTIntentProvider` | `propose(context)` transport 주입 어댑터 | 외부 transport가 실제 GPT를 호출해야 함. **내장 GPT 호출 아님**. 재사용 후보 |
| `research/llm/provider.py::OfflineProvider` | 고정/오프라인 연구 입력 | 테스트 용도. 실제 GPT 세대 계수 금지 |
| `research/llm/provider.py::CodexIntentProvider` | `GPTIntentProvider` alias | 별도 Codex SDK 래퍼가 이미 있다는 뜻 **아님** |
| `research/llm/provider.py::ConfiguredJSONProvider` | 명시적으로 retired/raise | 부활·우회하지 말 것 |
| `research/llm/codex_exec.py::CodexExecProvider` | 이전 Codex CLI 실행자 호환 타입 | 생성 시 `RuntimeError`: **구형 기능 제거**. 실제 실행 경로로 채택 금지 |
| `research/llm/openai_response_transport.py::OpenAIResponsesResearcher` | **선택형 OpenAI Responses HTTP 클라이언트 실제 구현** | `OPENAI_API_KEY`/명시 model 필수. 기본 MCP를 침묵 속에 유료 API로 변경 금지 |
| `application/t4_checkpoint_orchestrator.py::run_checkpoint_loop` | GPT 계획·진단을 단계적으로 받아 재개 | 아직 운영 인증 증거 호스트 미배선. mock 100세대는 실제 모델 100세대 아님 |
| `research/llm/model_provenance_v1.py` | 모델 provenance 개념/검사 부품 | 독립 공급자 서명 충족 여부는 별도 검증 필요 |

**실제 누락:** 공식 Codex Python SDK 설치 및 ChatGPT 계정 로그인, 실제 모델 작성 응답의 확인 가능한 ID·출처/usage, P4-2 provenance 사전승인, 모델 사용량 제한 시 checkpoint 보존. **새 포크 P0에서는 GPT 호출 0회**다.

## 6. 데이터·지표·전략·평가·보존의 파일 소유권

| 계층 | 원래 코드 위치 | 재사용 규칙 |
|---|---|---|
| 로컬/시장 데이터 | `core/data/{access,parquet,quality,timebase,contracts}.py`, `application/market_data_service.py`, `application/market_data_audit.py` | 새 연구 드라이버가 데이터를 별도로 파싱·시장시각 추정하지 말고 원래 입력 검증으로 위임 |
| 지표 정의/등록 | `core/features/{registry,catalog,contracts,calculators,alignment,series,provenance}.py`, `research/indicator_engine/` | `research_feature_specs()` **173개**, 단위·timeframe·warmup·lookback 확인. 지표 계산식 중복 작성 금지 |
| 전략 DSL | `strategy_ir/{schema,validator,normalizer,compiler,parser,provenance}.py`, `research/llm/director.py` | **StrategyIR가 전략의 유일한 canonical representation**. 원격 GPT 작성 Python을 검증 엔진에 직접 실행 금지 |
| 계획 IR/변경 | `research/indicator_engine/algorithm_plan.py`, `research/llm/intent_bridge.py`, `mutation/{engine,parameter,primitive_registry}.py` | Typed operation 재사용; 새 문자열 전용 조건 엔진 도입 금지 |
| 체결/위험 | `core/backtest/{engine,p2_policy}.py`, `core/costs/{model,slippage}.py` | 기존 다음 시점 체결·수수료/슬리피지/리스크 모델 단일 기준 |
| 성과 분석 | `evaluation/{metrics,risk,attribution,benchmark,pareto,robustness,scoring}.py` | LLM은 계산된 숫자를 원인 가설로 해석할 뿐 실측 성과를 다시 계산하지 않음 |
| 봉인 및 편향 | `core/validation/{walk_forward,cpcv,cscv,gates}.py`, `evaluation/{trial_dependence,trial_null_calibration}.py` | 개발 데이터와 독립 OOS 권한 분리. 현재 과거 2020~2025 QQQ non-PIT 성적은 일반화/수익성 증거 아님 |
| 증거/원장 | `application/academic_checkpoint_service.py`, `memory/{evidence_store,evidence_frontier,training_trace_store,trial_inventory}.py`, `runtime/evidence_session.py`, `core/integrity/*` | **각 저장소가 가진 증거의 의미가 다름**. 기존 학술 checkpoint SQLite/해시의 계수 권한은 checkpoint service |
| 진화/부모 | `research/llm/{cross_generation_memory,parent_portfolio_v2,lineage_selection,experiment_learning}.py`, `memory/{knowledge,frontier,promotion,rescue_pool}.py` | 좋은 자식 선택·원인 기록·중복 방지를 새 드라이버에 재구현하지 않음 |
| 비주문 실행/배포 | `runtime/{scheduler,persistent_queue,lifecycle_lock,resource_manager,system_controller}.py`, `deployment/{moon,paper,live}/` | 신규 Python 루프 자체가 주문 서비스·대시보드 감독자를 중복 시작하지 않도록 제한 |
| 대시보드 | `dashboard/`, `dashboard.py`, `scripts/fresh_research_dashboard.py`, `runtime/dashboard_supervisor.py` | 기존 포트/고정 URL과 경쟁하는 별도 데몬 자동 시작 금지. 필요하면 독립 포트 승인 후 |

## 7. 사전에 확인한 중복·충돌 후보 목록

> 아래 **중복 위험**은 파일명·실제 선언·일부 핵심 구현을 검토한 **검토 후보**다. 두 모듈이 의미까지 동일하다는 입증 없이 삭제·합치기 금지. `P0`는 실제 장애를 막는 사전 필수, `P1`은 구조 정리 후보.

| 우선 | 유사·충돌 경로 | 구체적 원인 | 권장 처리 |
|---|---|---|---|
| **P0** | `chatgpt_mcp_sdk.py` 32 tools vs `codex_mcp_core._tools()` 13 | **서로 다른 공개 계약**. 로컬 Python 프로브의 13개에는 `submit_algorithm_plan` 등의 ChatGPT 전용 학술 도구가 노출되지 않을 수 있음 | 기능을 재개발하기 전에 정식 API와 도구 schema 표면을 비교, **명시적 승인된 fork-only 연구 도구 subset**만 실험 |
| **P0** | `academic_checkpoint_service.py`의 `require_trade_activity` vs `chatgpt_mcp_sdk.py` 학술 `submit_algorithm_plan` 입력 schema | 서비스는 bool 지원, 외부 schema에는 옵션 미노출 — **계약 불일치** | fork-only 계약 회귀 테스트 후 schema 정렬, 원본 MCP 기본값 무단 변경 금지 |
| **P0** | `python_mcp_direct.py` read-only allowlist vs `codex_mcp_server.py` 전체 13도구 | **클라이언트 필터만으로 서버가 읽기 전용이 되는 것은 아님** | 개발 호스트의 프로세스 OS 권한/서버 측 도구 제한/경로 ACL 별도 점검 |
| **P0** | `.codex/config.toml.example` 상대 경로·`uv` vs 포크 실제 상태 | 예제는 fork-local 프로젝트 고정·독립 venv 보장 안 함 | 독립 venv, 절대 project/state 주소 사용. **원래 P5 state와 혼합 금지** |
| **P0** | `AcademicMCPCheckpointService` vs `GPTGuidedResearchService` vs `ResearchBatchService` | 별도 세션·SQLite/worker·단계·계수 방식, 세대 결과를 혼동하기 쉬움 | T4에는 Academic 서비스만 정식 계수, 나머지는 기능별 부품/테스트로 분리 |
| **P0** | `t4_checkpoint_orchestrator`, `GPTIntentProvider`, `CodexExecProvider`, `OpenAIResponsesResearcher` | 일부는 콜백만 제공·일부 retired·일부 별도 API 과금 | 모델 실행 출처가 검증되기 전 **자동 카운트 경로 도입 금지**, 새 Codex wrapper 중복 구현 전에 상태별 분류 |
| **P1** | `codex_mcp_sdk_server.py` vs `codex_mcp_manual_server.py` 및 adapter/protocol | 공식 MCP SDK와 구형 rollback 구현 공존 | 공식 SDK primary, 구형은 테스트/rollback만; API helper 복사 금지 |
| **P1** | `core/features/registry.py` vs `core/features/catalog.py` vs `research/indicator_engine/` | 지표 등록·정의·학술적 선택/실행이 분리 | 계산기/등록 정의는 core 단일 기준, 연구 계획은 검증된 spec만 참조 |
| **P1** | `core/backtest/engine.py` vs `runtime/docker_evaluation.py` vs `orchestration/evaluation_runner.py` | 메트릭 계산을 여러 관문이 부를 수 있음 | canonical replay를 우선, Docker/runner는 호출 격리/운영자로 한정 |
| **P1** | `memory/evidence_store.py` vs `memory/research_evidence.py` vs `runtime/evidence_session.py` vs academic SQLite | 보관 단위·영수증·대상 상태가 다름 | evidence namespace 명시, 동일 거래 결과의 복수 authoritative ledger 방지 |
| **P1** | `mcp_context_budget.py` vs `research/llm/context_builder.py` vs `cross_generation_memory.py` | 응답 길이 축약과 연구용 요약 정보 계승의 서로 다른 문제 | MCP 출력 압축과 연구 세대 기억을 분리, 해시/거래 ID 훼손 금지 |
| **P1** | `scripts/*dashboard*`, `runtime/dashboard_supervisor.py` vs `dashboard.py` | UI 배포·관리·생성 스크립트 다수 | 원본의 8081/8082 포트·감사 API에 새 포크가 간섭하지 않도록 별도 namespace |
| **P1** | `application/t4_model_host_preflight.py` vs `scripts/quant_t4_host_readiness.py` | 모델 호스트 사전 진단의 라이브러리와 CLI | **재사용**; 세 번째 진단 엔진 도입 금지 |
| **P1** | `runtime/research_loop.py` vs `application/research_batch_service.py` vs `orchestration/generation.py` | 과거/배치/실험 운영 루프 각각 목적 다름 | 진짜 T4를 모델-권한·원장 중심으로 좁혀 기존 루프들과 동작 동등성을 무조건 주장하지 않음 |
| **P2** | 51개 이상 `main()`, 다수 동일 명 함수 | 진입점의 일반적인 반복 이름; **실제 기능 중복 증거가 아님** | AST export/경로로 구별, 이름만으로 일괄 리팩터링하지 않음 |

**결론:** 현재 우선순위는 *코드 삭제나 거대 리팩터링*이 아니다. **API 노출 차이·P5 원장 격리·실제 GPT 출처·연구 세대 계수** 4가지가 새 하이브리드 연구기의 성패를 결정한다.

## 8. 테스트·실측 증거 지도

| 기능/위험 | 기존 테스트·도구 |
|---|---|
| 신규 Python STDIO 실제 호출·격리 | `tests/integrations/test_python_mcp_direct.py`; `scripts/python_mcp_probe.py` |
| Codex 공식 SDK 대 수동 parity | `tests/integrations/test_codex_mcp_sdk_parity.py`, `test_codex_mcp_cutover.py`, `test_codex_mcp_manual_adapter.py` |
| ChatGPT SDK/HTTP/stdio/OAuth | `tests/integrations/test_chatgpt_mcp_sdk.py`, `test_chatgpt_mcp_http.py`, `test_chatgpt_mcp_stdio.py`, `test_chatgpt_mcp_moon_oauth.py` |
| Academic checkpoint 시퀀스·재시도 | `tests/integrations/test_academic_mcp_sessions.py`, `test_academic_mcp_submission_replay.py`, `test_academic_mcp_recovery_d02.py` |
| 부모·P3·P4/S7·거래 게이트 | `tests/integrations/test_quant_generalization_p3_b_enrollment.py`, `test_quant_p4_s7_precommit.py`, `tests/research/test_t4_feature_unit_gate.py` |
| 모델 호스트·출처·코드 금지 경계 | `tests/integrations/test_t4_model_host_preflight.py`, `test_t4_checkpoint_orchestrator.py` |
| 범위 동결 및 단계·원본 20문답 | `tests/governance/test_autoresearch_scope_lock.py` |
| 보안/KIS 주문 경계 | `tests/integrations/test_kis_isolation.py`, `test_paper_orders.py`, `tests/security/` |
| 전체 코드 정적·테스트 | `python -m pytest -q`, `ruff check .`, `mypy .`; **이 조사 단계에서 전체 테스트 수행은 아님** |

**이전 실측 유지:** 포크 P0 실행 `STDIO 13 tools / 173 features / GPT 0 / orders false / NOT_INITIALIZED`, 신규 테스트 6, 기존 관련 테스트 포함 14 PASS, 이전 포크 전체 Ruff PASS. 이번 문서 작성은 **모델·데이터셋을 새로 실행한 성능 검증이 아님**.

## 9. 다음 개발을 시작하기 위한 최소 의존성 순서 (제안, 기존 로드맵 변경 아님)

| 순서 | 재사용/추가 대상 | '완료'의 최소 증거 | 금지되는 단축 경로 |
|---|---|---|---|
| **D0** | 본 문서 + 전체 파일/의존성 TSV | 새 포크 origin/main commit, 원본/upstream 불변 | 전수조사 생략·원본 수정 |
| **D1** | `python_mcp_direct.py`, `codex_mcp_sdk_server.py`, 인증/경로 설정 | **새 포크 독립 venv**, fork-state에서 read-only 조회·프로세스 lifecycle PASS | 기존 P5 원장이나 OAuth 복사 |
| **D2** | `chatgpt_mcp_sdk.py` 학술 도구 schema, `codex_mcp_core.py` | 필요한 계획/진단/게이트 도구의 **명시적 fork-only endpoint** 계약 동등성 테스트 | 내부 private `_dispatch`를 무검증·무권한 우회로 호출 |
| **D3** | `AcademicMCPCheckpointService` + typed intent/diagnostic/S7 | **실제 외부 GPT 구조화 응답을 허용된 MCP로** 제출, 거래 ID 검증, 올바른 SHA 및 세대 증가. 콜백 가짜 테스트와 운영증거 분리 | 테스트 mock 100을 진짜 GPT 100으로 보고 |
| **D4** | 승인된 Codex SDK/모델 호스트 or 지원되는 연결 실행 환경 | 사용자 승인 로그인/비용·쿼터, 출처 식별자·실패 시 중단·동일 토큰 재개 | 기존 OAuth 자동 추출·유료 API 무단 전환 |
| **D5** | 정식 독립 포크 연구 원장 + 대시보드 | 실제 GPT 1세대→3세대→목표 수까지 증거, OOS 미개봉·orders OFF | 원본 28세대 이식해 포크 실적으로 계산 |

**작업 분해 기준:** 기존 인터뷰의 연구 자유도와 발전·증거 보존을 우선해야 하며, 앞으로 **새 파일을 만들 때마다 먼저 본 문서 7절의 중복 후보와 두 TSV에서 동일 기능을 탐색**한다. 재활용 불가능하거나 계약 불일치가 실측된 경우에만 신규 모듈을 추가하고, 새 파일에는 해당 재사용 검토 근거를 문서화한다.

## 10. 조사 확실성 및 명시적 미조사 경계

- **확인됨:** Git 추적 파일 1,107개, Python 679개, AST 기반 정적 내부 import 2,051개, Moon 노출 도구 38개, ChatGPT Quant 노출 도구 32개, 코드 내부 Codex 공개 도구 13개, 173 registered feature specs, 프로세스 기반 Python STDIO 연결 P0.
- **확인됨:** 원본 Quant 체크포인트 경계와 새 포크는 프로젝트/상태 경로가 다르다. 제공된 포크 P0는 GPT 호출·실거래·새 연구 세대 증가 없음.
- **부분 확인:** 코드 중복은 **후보 매핑**이다. 실제 세부 함수/응답 동등성은 통합 테스트로 확인해야 하고, 동적 함수 호출/JS/셸/바이너리 의존 그래프는 별도.
- **이번에 하지 않음:** 원본 Moon MCP 서비스 내부 비공개 코드 역추적, 사용자 계정 OAuth 및 자격증명 값 열람/복제, 원본 P5 디렉터리의 내부 SQLite 전수 스캔, 봉인 OOS 해제, 신규 API 모델 호출, 무인 백그라운드 세대 실행, 모든 1,107개 파일의 기능별 E2E 실행.
- **후속 현장 검증 필요:** 기존 상태/권한 로직을 모델 실행자가 실제로 통과할지, ChatGPT 플러그인 OAuth가 Codex SDK 프로세스에 자동 상속되는지(**자동 상속 확인 안 됨**), 독립 가상환경 재현성, 성능 병목, 실제 100세대에서 rate/quota 발생 조건.

**요약 의사결정:** *Moon을 복제하거나 Quant 엔진을 두 번 개발하지 않는다.* 이미 동작한 Python→Quant STDIO MCP를 기반으로, **원래 checkpoint 서비스와 도구 계약의 차이를 해결하고 인증된 GPT 판단만 연결**한다. 모든 운영 원장·원본 Git·OAuth·실주문/OOS 경계는 계속 격리한다.
