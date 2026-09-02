# MCP 전체 시스템 기동

## 최초 준비

Codex Desktop의 신뢰된 MCP 설정에 `.codex/config.toml.example`의 서버 섹션을
등록한다. `cwd`는 이 저장소 루트로 지정한다. MCP 서버 자체는 Codex Desktop이
필요할 때 시작하므로 별도 터미널에서 계속 실행할 필요가 없다.

Docker 격리 백테스트 이미지는 저장소 루트에서 한 번 빌드한다.

```powershell
docker build -t quant-autoresearch-worker:local -f runtime/Dockerfile.worker .
```

연구 방향 탐지 워커는 로컬 `codex` CLI를 사용한다. 다음으로 로그인 상태와
설정 파일을 확인한다.

```powershell
codex login status
```

`state`가 새 디렉터리라면 한 번만 초기화한다.

```powershell
python cli.py init --state-dir state
python cli.py set-mode --state-dir state --mode paper
```

## Codex 명령

Codex에서 다음처럼 요청한다.

```text
전체 시스템을 시작해줘.
전략 소스는 strategies/example.py,
데이터는 data/qqq.parquet을 사용하고,
random 방식으로 후보 32개, seed 7, 최소 거래 10회로 실행해줘.
시작 전에 모든 사전조건을 검사하고, 문제가 있으면 시스템을 시작하지 말고
필요한 조치를 먼저 알려줘.
```

Codex는 MCP의 `start_system`을 호출한다. 이 도구는 먼저 다음을 검사한다.

- Python과 Paper-only 상태
- 전략 소스와 Parquet 파일의 프로젝트 루트 제한
- Parquet 메타데이터와 `development`/`validation` 데이터 영역
- Codex CLI와 `.env` 연구 설정
- Docker CLI, Docker Desktop 엔진, worker 이미지
- 대시보드 포트

실패하면 `BLOCKED`와 함께 “Docker Desktop을 실행하세요”, “worker 이미지를
빌드하세요”, “전략·Parquet 파일을 준비하세요”처럼 항목별 조치를 반환하며
프로세스를 시작하지 않는다.

## 기동되는 구성요소

사전점검을 통과하면 다음 세 구성요소가 병렬로 시작된다.

- `dashboard`: `127.0.0.1:8080`의 로컬 대시보드
- `research_worker`: 로컬 Codex CLI로 검증된 `ResearchIntent`를 생성하고 기록
- `backtest_worker`: 네트워크 차단·capability 제거·읽기 전용 파일시스템의 Docker 컨테이너

대시보드와 상태 확인은 `http://127.0.0.1:8080/`, 백테스트 이력은
`http://127.0.0.1:8080/backtest`에서 확인한다.

## 상태와 중지

```text
전체 시스템 상태를 보여줘.
```

→ MCP `get_system_status`

```text
전체 시스템을 중지해줘.
```

→ MCP `stop_system`

상태 파일은 `state/system/` 아래에 기록된다. 연구 의도는
`state/llm/intents.jsonl`, 백테스트 결과는 `state/test-records.jsonl`에
기존 안전한 원장 형식으로 기록된다.

## 현재 경계

- KIS 계좌 조회와 주문·실전투자는 기동하지 않는다.
- `sealed_oos` 데이터는 사전점검에서 차단된다.
- Docker 이미지가 없으면 자동으로 인터넷 빌드하지 않고 빌드 명령만 안내한다.
- 연구 탐지와 백테스트는 병렬로 시작되지만, 현재 생성된 `ResearchIntent`의 구조 변경을
  같은 실행에 자동 반영하는 mutation 큐는 별도 후속 작업이다. 현재 백테스트는 사용자가
  지정한 검증 전략·데이터 입력으로 실행된다.
