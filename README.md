# Quant Autoresearch Harness

시스템 전반의 용어·경로·연산자·상태 라벨·지시문 기준은
[`docs/operations/notation-contract.md`](docs/operations/notation-contract.md)에 통합되어 있습니다.
새로운 전략·feature·연구 명령은 이 계약의 canonical 표기만 사용합니다.

An LLM-assisted autonomous quantitative research platform.

The system separates responsibilities:

```text
LLM = research direction and interpretation
LOCAL = IR mutation, planning, analysis, and persistence
WORKER = isolated backtest execution
EVALUATOR = immutable statistical judgment
MEMORY = experiment and knowledge accumulation
```

Research is separate from KIS order execution. Live trading is denied by default and requires a separate, explicit human approval gate.

## Development

This repository targets Python 3.10+ and uses pytest, Ruff, and mypy. Install the development dependencies from `pyproject.toml`, then run:

```powershell
python -m pytest -q
ruff check .
python -m mypy .
```

The approved architecture and the complete implementation plan are in `docs/architecture/` and `docs/superpowers/plans/`.

날짜별 개선 사항과 실제 실행 성과는 [`docs/operations/improvement-log-2026-09-03.md`](docs/operations/improvement-log-2026-09-03.md)에 기록한다.

운영 기준은 `dashboard/` FastAPI 대시보드와 `research/policy.yaml`이다. 루트의
`dashboard.py`는 이전 Streamlit 화면의 보존·테스트용 파일이며 `cli.py dashboard`가
실행하지 않는다. QQQ 대비 최소 연복리 초과수익률과 완료 연도별 최소 거래수 기본값은
정책 파일에서 읽으며, 현재 기본값은 각각 0.10(10%p)과 30회 초과(31회 이상)이다.

## Quick start

```powershell
python cli.py init --state-dir state
python cli.py validate-strategy --source path\to\strategy.yaml
python cli.py import-strategy --source path\to\strategy.py
python cli.py import-strategies --source path\to\strategy.py --strategies-dir strategies
python cli.py import-strategies --repo https://github.com/ORG/REPO.git --ref main --kis-presets
python cli.py plan-generation --parent champion-1 --method random --count 32 --seed 7
python cli.py list-features
python cli.py run-generation --source strategies\normalized\golden_cross.json --data data\daily.parquet --method random --count 8 --seed 7 --domain '{"name":"indicators.sma_fast.period","values":[5,10,20]}'
python cli.py set-mode --state-dir state --mode paper
python cli.py mode --state-dir state
python cli.py dashboard-refresh --state-dir state --env-file .env
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
python cli.py paper-order-smoke --state-dir state --env-file .env --symbol QQQ --quantity 1 --confirm-paper-order
python cli.py research-intent --state-dir state --env-file .env --project-root .
python cli.py autoresearch --source strategies\normalized\golden_cross.json --data data\daily.parquet --series-data data\external-series.parquet --generations 20 --count 8 --method random --min-annual-trades 30 --min-qqq-cagr 0.10 --state-dir state --env-file .env
```

For Codex Desktop, the MCP system orchestrator can preflight and start the local
dashboard and managed research worker with the selected evaluation backend. Docker
evaluation is opt-in and creates one isolated container per evaluation job rather than
a permanent backtest worker. See `docs/operations/system-orchestrator.md` for
registration and the natural-language command flow.

The local paper operations dashboard is available at `http://127.0.0.1:8080/` after
starting the last command. It reports the effective paper-only mode, sanitized KIS
account snapshot, evaluation ledger, Champion strategy, generation trend, and worker
heartbeat state. See `docs/operations/paper-dashboard.md` for the safety boundary and
refresh behavior.

백테스트 탐색 중 대시보드를 항상 유지하려면 별도 PowerShell에서 supervisor를
실행한다. 대시보드가 종료되면 자동으로 재시작하며, 로그는
`state/system/dashboard-supervisor.log`에 남긴다.

```powershell
.\scripts\start_dashboard.ps1
```

브라우저 화면은 백테스트·연구 상태를 15초마다 다시 읽는다.

`import-strategies` is the safe external-strategy intake path. It scans local files or
clones a public GitHub repository at a specified ref into a temporary directory, then
uses AST/static analysis only. KIS builder presets can be imported with
`--kis-presets`; the ten preset files under `strategy_builder/strategy_core/preset` use
the same conversion and duplicate-detection path as any other source. Imported and
normalized records are written under `strategies/`, while dynamic or non-representable
logic is retained as `REVIEW_REQUIRED` with a reason. No external Python source is
executed and no order endpoint is called.

Use `--dry-run` to inspect counts without writing:

```powershell
python cli.py import-strategies --repo https://github.com/ORG/REPO.git --ref main --kis-presets --dry-run
```

The dashboard's 접힌 `전략 카탈로그` section reads `strategies/catalog.json` and shows
conversion status, source path, duplicate classification, and review reasons. A
successful import is not a Champion promotion; run the approved backtest pipeline
separately before considering a strategy for Frontier.

## How to use the system

Run commands from the repository root. Create the state directory once, keep the
trading mode set to paper, refresh the read-only KIS snapshot when needed, and leave
the dashboard process running in its own terminal:

```powershell
python cli.py init --state-dir state
python cli.py set-mode --state-dir state --mode paper
python cli.py dashboard-refresh --state-dir state --env-file .env
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/`. The dashboard's Quick Guide contains the same commands
with copy buttons. `init` is only for a new state directory; do not repeat it over a
state directory whose experiment history you want to keep. `dashboard-refresh` reads
paper account/quote data; it does not place orders.

### 1회 KIS 모의주문 검증

실제 KIS 모의계좌 주문 경로를 확인할 때만 다음 명령을 명시적으로 실행합니다.

```powershell
python cli.py paper-order-smoke `
  --state-dir state `
  --env-file .env `
  --symbol QQQ `
  --quantity 1 `
  --confirm-paper-order
```

이 명령은 Paper 엔드포인트에서 시장가 매수 1건을 넣고, 주문체결 조회에서
매수 체결 수량을 확인한 뒤, 체결된 수량만 시장가 매도합니다. 최종 잔고가
기존 수량으로 돌아오지 않으면 성공으로 처리하지 않습니다. 매수 미체결,
잔고 조회 실패, 장 운영시간 외 오류가 발생하면 매도 주문을 추가로 넣지
않습니다. 연구 루프·대시보드 새로고침·Codex MCP에서는 주문을 실행하지
않습니다.

For Codex Desktop, register `.codex/config.toml.example` in the Desktop MCP settings.
The local MCP server can then be started with:

```powershell
python -m integrations.codex_mcp_server --state-dir state --project-root .
```

In Codex Desktop, use `get_workspace_status` for bootstrap/configuration state,
`get_system_status` for managed runtime health, and `get_dashboard_status` for
research/performance data. The public MCP surface contains 13 tools covering workspace
bootstrap, static strategy/catalog operations, evidence/status reads, one-shot
evaluation, and managed research lifecycle control. Public tool responses include an
additive `_contract` block with `schema_version=1` and `orders_enabled=false`.

Low-level compatibility names such as `set_research_mode`, `validate_research_cache`,
`plan_generation`, `get_research_context`, and `submit_research_intent` are no longer
advertised in `tools/list`; they remain direct-call compatibility shims through the
Phase 3-6 compatibility window. The server has no order or live-account MCP tool.
For a non-interactive alternative, authenticate the Codex CLI and run:

```powershell
codex login status
python cli.py research-intent --state-dir state --env-file .env --project-root .
```

The command records a validated intent in `state/llm/intents.jsonl`; the dashboard
shows the provider state in the Codex LLM card. Keep KIS values only in the ignored
`.env` file, never in a prompt or source file.

### Mimir 명령으로 시스템 호출하기

`Mimir`는 Codex 대화와 자동연구를 짧은 명령으로 호출하는 Windows용 진입점입니다.
두 진입점은 같은 로컬 연구 코드를 사용하므로 결과 저장 위치와 안전 정책이 같습니다.

#### 설치

저장소 루트에서 개발 모드로 한 번 설치합니다.

```powershell
python -m pip install -e .
```

설치 후 PowerShell에서 다음처럼 호출합니다. Windows에서는 명령 대소문자를 구분하지
않으므로 `mimir`와 `Mimir`를 모두 사용할 수 있습니다.

```powershell
Mimir /help
Mimir /status
Mimir /research 20
Mimir /research 100 --intent-repairs 3
Mimir /chat "최근 탈락 전략의 원인을 요약해줘"
```

설치하지 않은 경우에는 같은 기능을 다음처럼 실행할 수 있습니다.

```powershell
python -m runtime.mimir /research 20
```

#### `Mimir /research 20` 설정

세대 수만 지정한 간단한 명령은 전략·데이터 경로를 다음 순서로 찾습니다.

1. `MIMIR_SOURCE`, `MIMIR_DATA`, `MIMIR_SERIES_DATA`를 `.env`에 지정
2. `state/system/research_loop.json`에 저장된 마지막 연구 설정 사용
3. 둘 다 없으면 실행하지 않고 누락된 설정을 안내

새로운 기본값을 직접 지정하려면 `.env`에 다음을 추가합니다. 경로는 저장소 루트
기준의 상대경로 또는 절대경로를 사용할 수 있습니다.

```dotenv
MIMIR_SOURCE=strategies/normalized/your-strategy.json
MIMIR_DATA=runs/your-run/qqq_daily.parquet
MIMIR_SERIES_DATA=runs/your-run/qqq_series.parquet
```

또는 명령에 직접 지정합니다.

```powershell
Mimir /research 20 `
  --source strategies\normalized\your-strategy.json `
  --data runs\your-run\qqq_daily.parquet `
  --series-data runs\your-run\qqq_series.parquet `
  --count 8 `
  --min-annual-trades 30 `
  --min-qqq-cagr 0.10
```

Codex가 반환한 전략 제안이 등록되지 않은 인디케이터나 지원하지 않는 IR 변경을
포함하면, Mimir는 별도의 읽기 전용 Codex 프로세스를 최대 3회 호출해 제안을
복구합니다. `--intent-repairs 0`으로 복구 호출을 끌 수 있고, 복구 횟수는 세대마다
독립적으로 적용됩니다. 복구에 실패해도 해당 세대는 부모 전략을 baseline으로
평가한 뒤 다음 세대로 진행합니다.

세대별 기록은 `state/system/autoresearch.json`에 남습니다.

- `REPAIRED`: 복구된 제안으로 평가
- `FALLBACK`: 제안 복구 실패 또는 후보 평가 실패 후 부모 전략으로 평가
- `DEGRADED`: 후보와 fallback 평가가 모두 실패했지만 다음 세대로 계속 진행

Codex의 출력은 `ResearchIntent`의 canonical typed operation 계약을 따라야 합니다.
`ADD_RULE`과 `ADD_REGIME_FILTER`는 반드시 `Condition` 객체를 사용하고, 기간·수치 변경은
scalar 값으로 반환해야 합니다. JSON Patch의 임의 `add`·`replace`·`remove` 조합은 Codex
출력에서 허용하지 않습니다. 따라서 `regime_filters.0`에 리스트를 추가하거나 조건 자리에
`true`, `[true]`, `{}`를 넣는 응답은 백테스트 전에 거부됩니다.

조건 연산자는 검증된 `cross_above`, `cross_below`, `less_than`, `less_equal`,
`greater_than`, `greater_equal`, `equal`만 사용합니다. 인디케이터는 검증된
`IndicatorSpec`의 `type`, `period`, `parameters` 형식으로만 호출하며, 추가·교체 대상은
반드시 `indicators.<alias>`입니다. feature·외부 시계열은 `features.<alias>`와
`FeatureRef`를 사용합니다. 조건 참조는 alias만 사용하고, 경로는 `entry.conditions.0`처럼
점 표기와 정수 index를 사용합니다. `entry.conditions[0]` 같은 입력은 경계에서 canonical
표기로 정규화되어 기록됩니다.

각 제안은 백테스트 전에 부모 Strategy IR 복제본에 dry-run으로 적용하고, 연산 순서·참조·자료형·
등록 상태·최종 Strategy IR을 검증합니다. 성공한 canonical 제안만 실험 큐에 들어가며,
검증 단계는 `research-events.jsonl`의 `preflight_completed` 이벤트로 기록됩니다.

복구가 같은 잘못된 payload를 반복해서 반환하면 같은 Codex 호출을 계속하지 않습니다.
해당 오류는 `state/system/repair-knowledge.jsonl`에 오류 코드, payload 서명, 세대,
처리 결과로 누적되고, 그 세대는 부모 전략을 그대로 평가하는 `FALLBACK`으로 진행합니다.
이 기록은 전략 성능 증거가 아니라 LLM·하네스 오류를 줄이기 위한 운영 지식입니다.

오류 기록에는 `code`, `phase`, `generation`, `message`, `retryable`과 함께 오류 유형에
따른 `path_expected`, `reference_received`, `available_references`, `available_targets`,
`repair_action`이 포함됩니다. 동일 진단의 간결한 요약은 복구 Codex 요청에도 전달되므로,
복구 agent가 부모 IR 전체를 추측하지 않고 오류 위치와 허용 형식을 바로 수정할 수 있습니다.
`research-events.jsonl`에서는 `proposal_started`, `preflight_completed`,
`repair_started`, `evaluation_started` 등의 이벤트별 `duration_seconds`로 각 단계 시간을
분리해 확인할 수 있습니다.

따라서 `Mimir /research 100`은 개별 세대 오류로 중단되지 않고 요청한 100세대를
처리합니다. 최종 상태가 `COMPLETED_WITH_FALLBACKS` 또는
`COMPLETED_WITH_ERRORS`이면 전략 품질 성공이 아니라, 모든 세대의 처리와 오류
기록이 완료됐다는 뜻입니다. 모든 자동연구 실행은 현재처럼 주문을 끄고 백테스트만
수행합니다.

`Mimir /research`는 유한 세대만 허용합니다. 무한 반복은 지원하지 않으며, 실행 중
즉시 중지하려면 해당 PowerShell 창에서 `Ctrl+C`를 누릅니다. 자동연구는 Paper-only
백테스트 전용이고 KIS 주문 API를 호출하지 않습니다.

`--min-qqq-cagr`를 생략하면 동일 기간 QQQ 연복리보다 0.10(10%p) 이상 높은 후보만
통과 대상으로 판정합니다. 다른 기준을 시험할 때만 예를 들어
`--min-qqq-cagr 0.05`처럼 명시적으로 덮어씁니다. 이 기준은 수익성 비교를 위한
기본 게이트이며, 연도별 거래수·위험·강건성·비용·Walk-forward 검사는 그대로 유지됩니다.

인디케이터 카탈로그가 포함된 연구 요청은 일반 대화보다 오래 걸릴 수 있습니다. 기본
Codex 실행 제한은 300초이며, 더 길게 허용하려면 `.env`의
`QUANT_CODEX_TIMEOUT_SECONDS`를 초 단위로 설정합니다. Codex 설정 파일의 호환되지 않는
`service_tier` 값은 자식 호출에서 기본값 `fast`로 덮어쓰며, 필요하면
`QUANT_CODEX_SERVICE_TIER=fast` 또는 `flex`로 선택할 수 있습니다. 시간초과나 Codex 비정상 종료
시에는 Mimir가 종료 코드와 진단 메시지를 함께 출력합니다.

제안과 복구의 timeout을 따로 조정하려면 `QUANT_CODEX_PROPOSAL_TIMEOUT_SECONDS`와
`QUANT_CODEX_REPAIR_TIMEOUT_SECONDS`를 설정합니다. 복구는 구조화된 오류 수정 작업이므로
기본 복구 제한을 더 짧게 둘 수 있습니다. 두 값을 지정하지 않으면 공통
`QUANT_CODEX_TIMEOUT_SECONDS`가 양쪽에 적용됩니다.

#### 기존 `quant>` 터미널 안에서 사용

기존 터미널도 그대로 사용할 수 있습니다.

```powershell
python cli.py terminal `
  --mode autoresearch `
  --source strategies\normalized\your-strategy.json `
  --data runs\your-run\qqq_daily.parquet `
  --series-data runs\your-run\qqq_series.parquet `
  --iterations 20 `
  --state-dir state `
  --env-file .env `
  --project-root .
```

이후 다음 두 방식이 모두 같은 명령으로 처리됩니다.

```text
quant> /research 20
quant> Mimir /research 20
```

터미널 내부에서 `Mimir /research`를 사용할 때는 먼저 `--mode autoresearch`로
시작해야 합니다. 일반 대화는 `quant>`에 문장을 그대로 입력하면 되고, 상태는
`Mimir /status` 또는 `/status`로 확인할 수 있습니다.

### Codex 자동연구 터미널 사용법

이 터미널은 두 가지 일을 합니다.

1. 일반 문장을 Codex에 질문합니다.
2. Codex가 연구 방향을 제안하고, 로컬 백테스트가 후보 전략을 평가합니다.

연구는 항상 Paper-only·백테스트 전용으로 실행되며 주문을 생성하지 않습니다.
반드시 저장소 루트(`C:\Users\hanji\Documents\ChatGPT\주식`)에서 실행하세요.

#### 1. 일반 대화 터미널 시작

```powershell
python cli.py terminal `
  --mode chat `
  --state-dir state `
  --env-file .env `
  --project-root .
```

실행 후 `quant>` 프롬프트에 일반 문장을 입력하면 Codex가 읽기 전용으로 답합니다.

```text
quant> 현재 Champion과 최근 탈락 원인을 요약해줘
quant> QQQ 대비 평가 게이트를 설명해줘
```

#### 2. Codex 자동연구 터미널 시작

자동연구에는 반드시 전략 원본과 데이터 파일을 지정해야 합니다.

```powershell
python cli.py terminal `
  --mode autoresearch `
  --source strategies\normalized\golden_cross.json `
  --data data\daily.parquet `
  --series-data data\external-series.parquet `
  --iterations 20 `
  --count 8 `
  --min-trades 10 `
  --min-annual-trades 30 `
  --min-qqq-cagr 0.10 `
  --state-dir state `
  --env-file .env `
  --project-root .
```

터미널이 열린 뒤 다음을 입력합니다.

```text
quant> /research 20
```

`/research 20`은 Codex 제안과 로컬 평가를 20세대 수행합니다. 세대 수는 반드시
양의 정수여야 하며, 현재 무한 반복은 안전상 지원하지 않습니다. 무한 반복이
필요하면 여러 개의 유한 실행을 외부 스케줄러로 묶되, 각 실행의 상태와 결과를
확인해야 합니다.

#### 3. 터미널 명령

| 명령 | 기능 |
|---|---|
| 일반 문장 | Codex 읽기 전용 질의 |
| `/mode chat` | 일반 대화 모드로 변경 |
| `/mode autoresearch` | 자동연구 모드로 변경 |
| `/research 20` | 20세대 Codex 자동연구 실행 |
| `/status` | 대시보드 상태 JSON 출력 |
| `/help` | 도움말 출력 |
| `/exit` | 터미널 종료 |
| `/stop` | 중지 요청 상태를 출력; 실행 중인 동기 작업을 강제 종료하지는 않음 |

현재 `/repeat`와 `/backtest`는 명령 파서에는 등록되어 있으나 REPL 실행 명령으로는
연결되어 있지 않습니다. 반복 백테스트와 단일 백테스트는 아래의 직접 CLI 명령을
사용하세요.

#### 4. Codex 없이 반복 백테스트 실행

```powershell
python cli.py repeat-research `
  --source strategies\normalized\golden_cross.json `
  --data data\daily.parquet `
  --series-data data\external-series.parquet `
  --method random `
  --count 8 `
  --generations 20 `
  --min-trades 10 `
  --min-annual-trades 30 `
  --min-qqq-cagr 0.10 `
  --state-dir state
```

`--domain`을 지정하지 않으면 기준선 후보 1개만 반복합니다. 실제 파라미터 탐색을
하려면 도메인을 하나 이상 추가해야 합니다.

```powershell
python cli.py repeat-research `
  --source strategies\normalized\golden_cross.json `
  --data data\daily.parquet `
  --method grid `
  --count 9 `
  --generations 20 `
  --min-annual-trades 30 `
  --min-qqq-cagr 0.10 `
  --domain '{"name":"indicators.sma_fast.period","values":[5,10,20]}' `
  --domain '{"name":"risk.position_size_pct","values":[25,50,75]}' `
  --state-dir state
```

#### 5. 진행 중 확인과 중지

다른 PowerShell 창에서 상태를 확인합니다.

```powershell
python cli.py status --state-dir state
Get-Content state\system\autoresearch.json
Get-Content state\llm\status.json
```

현재 터미널에서 실행 중인 연구를 즉시 끝내려면 해당 창에서 `Ctrl+C`를 누릅니다.
중단된 세대까지의 상태는 `state\system\autoresearch.json`에 남습니다.

#### 6. 대시보드 함께 실행

대시보드는 별도 PowerShell 창에서 실행합니다.

```powershell
python cli.py dashboard-refresh --state-dir state --env-file .env
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
```

브라우저에서 [http://127.0.0.1:8080/](http://127.0.0.1:8080/)을 엽니다. 연구 상태,
Champion·Frontier, 평가 기록, Codex 연결 상태를 확인할 수 있습니다.

#### 7. 안전상 실행하지 않는 명령

`paper-order-smoke`는 연구 터미널과 별개의 주문 명령입니다. 현재 시스템의 기본
상태는 `selected_mode=paper`, `orders_enabled=false`이며, 자동연구·일반 대화·
대시보드 새로고침은 주문을 실행하지 않습니다. 주문 테스트가 필요할 때만 별도의
명시적 확인 절차를 사용하세요.

인디케이터는 이름만 선택하지 않습니다. Strategy IR에 canonical feature ID,
입력 시계열, 시간봉, lag, lookback, parameters가 함께 기록됩니다. 예를 들어
`US10Y.close`의 주봉 RSI는 등록된 RSI calculator에 `timeframe=1w`,
`lookback=14`를 지정하는 방식입니다. VIX·금·DXY·QQQ·NASDAQ과 미국·일본·한국
2년·10년·20년물도 같은 방식으로 선택할 수 있으며, 전략마다 필요한 항목만
사용합니다. 계산은 로컬 as-of 엔진이 수행하고 feature lineage는 백테스트 원장,
Knowledge, 대시보드에 전달됩니다.

## Codex Desktop connection

Codex Desktop can connect to the local stdio MCP server using the credential-free
example in `.codex/config.toml.example`. Copy its section into the trusted Codex
configuration or register the same command in Desktop MCP settings:

```powershell
python -m integrations.codex_mcp_server --state-dir state --project-root .
```

The exposed tools cover sanitized research/workspace status, feature and strategy
catalogs, static strategy validation/import, deterministic generation planning,
validated intent submission, evaluation, and managed system lifecycle. Strategy import
is static and defaults to dry-run. There is no order, live-account, credential,
arbitrary-code, raw-market, or sealed-OOS tool.
For an unattended/local subprocess call, use `research-intent`; it invokes the
installed `codex exec` command and revalidates its structured output locally. The
interactive Desktop conversation is not implicitly reused by a separate `codex exec`
process. Codex CLI authentication is taken from its own saved login; KIS secrets are
removed from the child environment.
The CLI adapter accepts `QUANT_CODEX_MODEL` for a model supported by the installed
CLI; the example uses `gpt-5.4-mini`.

The local pipeline is callable through `orchestration.pipeline.GenerationPipeline`. It
executes candidate generation, IR backtests, metrics, robustness checks, validation,
selection, and abstract knowledge extraction. Parquet datasets must carry
`dataset_version` and `data_zone` metadata. The Docker runner mounts input read-only,
disables networking, drops capabilities, and writes only to the run output directory.

### 반복 백테스트 실행

`run-generation`에 `--domain`을 반복 지정하면 Strategy IR의 파라미터를 변경해
후보를 만듭니다. 도메인을 지정하지 않으면 `--count`와 관계없이 기준선 후보
1개만 실행합니다.

```powershell
python cli.py run-generation `
  --source strategies\normalized\golden_cross.json `
  --data data\daily.parquet `
  --series-data data\external-series.parquet `
  --method grid --count 9 --seed 7 --min-trades 0 `
  --domain '{"name":"indicators.sma_fast.period","values":[5,10,20]}' `
  --domain '{"name":"risk.position_size_pct","values":[25,50,75]}' `
  --state-dir state
```

`--series-data`는 `ParquetDataProvider.write_series` 계약을 따르는 외부 시계열
파일입니다. VIX·금·DXY·각국 2년/10년/20년 금리와 같은 전략 입력을 제공할 수
있습니다. QQQ와 NASDAQ 시계열이 모두 있으면 동일 기간 벤치마크 비교가 추가되고,
매크로·금리만 있으면 벤치마크 없이 전략 입력으로만 사용됩니다. 외부 데이터는
관측 시각과 `available_at`을 기준으로 as-of 정렬하여 미래 공개값을 차단합니다.

External price, macro, rate, and benchmark series use the same versioned Parquet
contract through `ParquetDataProvider.write_series/read_series`. The optional Feature
Registry exposes VIX, gold, DXY, QQQ, Nasdaq, and US/Japan/Korea 2-year, 10-year, and
20-year rate candidates. Any registered series can receive any registered transform on
`1m`, `5m`, `15m`, `1h`, `1d`, `1w`, or `1mo`; for example, `US20Y.close@1w:rsi(period=14)`.
A strategy selects
only the features it declares; no macro feature is implicitly mandatory. `list-features`
reports the current selectable catalog, and the dashboard exposes it at
`/api/features/catalog`.

The four audited indicator sources are represented by canonical FeatureSpecs with
aliases and semantic duplicate groups. `pythonpine` is treated as AGPL-3.0 and is not
vendored; its formulas are independently reimplemented. Profile, TPO, and tick
order-flow indicators require explicit data contracts. Account, order, network,
downloader, and plotting functions are never feature calculators.

Generation evaluation keeps the existing Fast/Full, robustness, walk-forward, OOS,
CSCV/CPCV, cost, and complexity checks. When benchmark data is supplied, it adds QQQ
total return and Nasdaq Composite comparison plus excess-return fields. Strategy risk
appetite and daily-loss behavior are recorded separately from the immutable system
emergency cutoff.

Paper trading is available only after an exact Champion-hash paper approval. The live
KIS order capability is intentionally absent from the research package; a live deployment
also needs a real account, data provider, calendar, image digest, and human approval.
