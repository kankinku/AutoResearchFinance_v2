# Quant AutoResearch — 다음 세션 복구 및 100세대 재개 인계서

기준: 2026-10-21 KST. 사용자 요청으로 새 대화에서 바로 이어 진행할 수 있도록 작성한 현재 상태 및 도구 이용 안내.

## 0. 핵심 요약 / 안전한 현재 판정

- 사용자 확정 총 목표: **공식 G500**. 이번 승인된 작업: **새 정식 100세대 시작**. GitHub 이전 기록상 마지막 완료 G350이 서버의 현재 마지막 세대임이 검증되면, 예정 범위는 **G351~G450**이다. G451~G500은 이번 100세대 범위 밖이다.
- **실행 상태: BLOCKED_NOT_STARTED. 실제 신규 정식 세대 0/100, 배치 Job ID 없음.** 이번 세션에서 새로운 백테스트 100회를 실행했다고 주장할 수 없다.
- 기존 **Quant AutoResearch 전용 MCP 도구**가 내부 오류를 반환한다. **Moon 기본 서버 건강 상태와 Quant 별도 연구 서비스/체크포인트 정상 상태는 별개**다.
- 운영 G350 세대 원장, 부모 ID와 검증 해시, 시장 데이터 Parquet 및 공식 연구 실행 세션에 현재 접근할 수 없었다. 이전 GitHub 문서는 최신 운영 상태를 대체하지 않는다. 운영 최신 상태가 G350이라는 것도 아직 미확인.
- 기존 OAuth/MCP 주소 재등록·초기화, 데이터/계보/세대 카운터 덮어쓰기, 보호 코어 수정, 봉인 OOS 개봉, 실주문 활성화 **금지**. 복구 전 임시/합성 데이터를 정식 세대로 세지 말 것.

## 1. 참조할 저장소·고정 문서

- GitHub: https://github.com/kankinku/AutoResearchFinance_v2
- 작업 브랜치: **feat/quant-same-session-350-20261019**
- 이 인계서 작성 직전 확인 HEAD: **6687e62784fba40a6cebdce6b10a6f90639eecee**. 실제 새 대화에서는 git fetch와 remote HEAD를 먼저 읽어 최신 여부 검증.
- 저장소 내:
  - AGENTS.md — 필수 프로젝트 보안/개발 원칙 및 테스트 게이트
  - docs/decisions/2026-10-14-autoresearch-interview-20q.md — 원본 20문답, 원본을 수정하지 말 것
  - docs/decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md — 고정 작업 순서와 세대 완료 정의
  - docs/decisions/2026-10-20-pinecode-internalization-5q-user-confirmed.md — Pine 원리 이식 5문답
  - docs/decisions/2026-10-21-quant-500-generation-target.md — **G500·첫 100세대 사용자 요청 확정**
  - docs/operations/autoresearch-master-progress.md — 공식 진행 기록. 이 인계서와 함께 읽을 것.
  - docs/operations/autoresearch-pine-p5-shards-2026-10-21.md — Pine 7개 분할 회귀 검증 실측
  - docs/operations/autoresearch-pine-p5-external-reference-2026-10-21.md — Pine 기준 출력 동등성 비교 조건
- Moon에서 실제 접근된 개발 저장소:
  /shared/moon-workspace/AutoResearchFinance_v2-pine-internalization-20261020
- 이전 세대 실험 운영 작업 폴더로 기록된 다음 경로는 현 Moon 공간에서 ENOENT:
  /shared/moon-workspace/AutoResearchFinance_v2-same-session-350-20261019
- 종전 기록상 /quant 역시 현재 Moon 공간에서 ENOENT. 단순히 경로가 없다는 사실만으로 영구 삭제나 운영 서버 중단을 단정하지 말 것.
- 별도의 /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory 디렉터리 존재가 확인됐으나 연구 state/data/실행 원장이 확보된 것은 아니다.
- 현재 개발 clone의 state/champion.json, frontier.json, knowledge.json 등은 **운영 G350 체크포인트라고 검증되지 않았으므로 절대 그 상태에서 정식 100세대를 새로 출발하지 말 것**.

## 2. 지금 보이는 도구 — namespace 및 실제 용도

### A. Quant 연구 전용 연결: mcp__Qaunt_Autoresearch__*

정확한 namespace 철자는 **Qaunt_Autoresearch** (Quant가 아니라 Qaunt) — 도구 검색 시 이 이름으로 검색.

읽기/진단 관련 도구 (기본 호출 인수가 빈 객체인 경우가 많음):
- get_workspace_status({}): 연구 workspace 부팅/상태
- get_dashboard_status({}): 운영 대시보드
- get_research_batch_status({}): 마지막 bounded batch 작업 현황; job_id가 확인된 경우 그 ID로 조회
- get_research_brief({}): 연구 Frontier·실패 기억/원인 진단 문맥
- list_market_data({}): 존재하는 원본 Parquet 경로·데이터 소스 설정
- get_research_batch_report({job_id?}): 완료 배치의 후속 평가/실제 세대 결과
- get_research_evidence({research_run_id?}): 해시·연구 원장 자료
- get_algorithm_research({session_id}), get_guided_research({session_id}): 기존 세대 세션 checkpoint 재개/검증

실행 관련 도구 — **위 읽기 호출과 원본 데이터를 확보하기 전 절대 호출하지 말 것**:
- preflight_research_batch: source_path/data_path/부모/ResearchIntent/세대 수 검증, worker 시작하지 않음
- start_research_batch: 1~100 bounded 배치 실행, 단 **도구 명세상 별도 로컬 LLM을 호출하지 않음**. GPT의 매 세대 원인 분석과 다음 계획이 정말 실행되는지 검증해야 사용자 정의 정식 세대로 인정 가능.
- start_algorithm_research: 1~100세대 GPT AlgorithmPlan 입력 대기 세션 시작
- submit_algorithm_plan → submit_algorithm_diagnosis: GPT의 계획과 실제 측정에 기반한 진단을 분리 제출하여 정식 세대 완결
- resume_algorithm_research, reconcile_algorithm_research: 기존 checkpoint에서 유효하게 재개
- start_guided_research, submit_guided_generation: 기존 GPT-directed workflow (실제 외부 GPT 참여와 lineage 확인 필요)
- resume_research_batch: 기존 일치하는 중단 batch만 재개, 임의 재시작 금지

현재 확인된 장애 (2026-10-21 재검증):
- get_workspace_status, get_dashboard_status, get_research_batch_status, get_research_brief, list_market_data: **각각 'The tool failed internally.'**
- 이 응답만으로 근본 원인을 확정할 수 없다: 플러그인 backend/OAuth/라우팅/서비스 비가동/마운트 불일치 등을 별도로 구분할 것.
- 이번에는 start_research_batch / start_algorithm_research를 **호출하지 않았음**.

### B. Moon 원격 개발환경: mcp__moon__*

**읽기**: list_directory, stat_path, read_file, list_processes, read_process.
**작업**: run_script / exec_command, task_start, task_context, task_validate, 기타.
Moon 관리 세션 상태를 확인하는 list_processes의 빈 목록은 **모든 OS/원격 Quant 서버의 프로세스가 0이라는 증명이 아니다**. 개발 서버나 runtime host는 서로 다를 수 있다.

관찰된 사실:
- Moon host /shared/moon-workspace 디렉터리 열거 성공.
- Moon 기본 건강 확인은 이전 점검에서 /health HTTP 200, service project-moon, OAuth enabled 보고됨.
- Quant 전용 운영 endpoint의 정확한 현행 경로, 접속 권한 및 live checkpoint는 이 건강 확인만으로 알 수 없다.
- 예전에 몇 가지 추정 /quant/... 경로에서 404를 봤으나 그것이 정식 등록 URL이라는 뜻이 아니다. **경로를 추측해 새 MCP URL을 만들거나 OAuth를 재등록하지 말 것**.
- 개발용 Git clone만 보이는 경로에서는 공식 G350 스냅샷 매니페스트와 실제 market-data Parquet를 찾지 못했다.

### C. GitHub 커넥터: mcp__GitHub__*

- fetch / fetch_file: 현재 branch, docs, AGENTS, 코드 및 정확한 파일 내용 확인.
- 변경이 필요할 때 파일 create/update 또는 Moon Git commit/push로 동일 branch 기록 가능.
- GitHub에 저장된 G350 분석 문서는 **원본 런타임 증거/시장데이터 자체가 아님**.
- 복구 결과는 master-progress와 별도 incident 기록에 갱신. 새 인계서의 이전 상태를 정정해야 할 때 관찰 시각과 증거를 남길 것.

## 3. 재개 전 '읽기 전용' 진단 순서

1. 기존 연결된 Qaunt_Autoresearch 플러그인 도구의 get_workspace_status({})와 get_dashboard_status({})를 호출. **내부 오류가 지속되면 새 배치를 생성하지 말 것.**
2. 같은 연결에서 get_research_batch_status({}), get_research_brief({}), list_market_data({})를 시도. 실제 response의 session/job ID를 얻으면 기존 동작 중 배치 또는 checkpoint가 있는지 확인.
3. Moon에서 배포 설정, 서비스 라우팅, 기존 인증 설정 **읽기만** 수행하고, 운영 Quant MCP 프로세스와 저장소/볼륨 경로를 정확히 확인. Moon 기본 /health 200은 Quant 상태와 별개.
4. 실제 원격 Quant runtime 및 mount가 다른 서버/컨테이너라면 그 차이를 문서화. 데이터 이동·권한 재설정·서버 재배포/복제는 원래 공식 데이터 위치와 변경 리스크 확인 후에만 추진.
5. 옛 공식 G350의 data snapshot SHA / source_path / parent lineage / candidate hash / last completed generation / 최근 running batch 유무를 읽어 교차 검증. 새 세대가 G350 이후 이미 있으면 **절대 G351부터 덮어쓰지 말 것**.
6. 기존 OAuth, endpoint, sealed OOS, live_orders_disabled, protected evaluator/cost/data/integrity 변경 없이 정상 연결이 확인되면 그제서야 **read-only preflight**.
7. 세대 정의: GPT가 다음 계획을 만드는 자율 알고리즘 연구를 실제 수행해야 함. 단일 intent를 100번 무작위 반복하는 배치로 GPT 진화 성공을 주장하지 말 것. run 결과의 거래/원인/후속 계획 및 부모 계승을 각각 증거로 확인.
8. 안전한 동일 계보에서 이번 100세대 시작이 가능한 것이 확인되면 승인된 범위에서 실행; job ID, 실 세대 수, 마지막 검증 세대, 중단 사유를 즉시 기록.

## 4. 안전 및 금지 항목

- initialize_research_state 등 **초기화 계열** 호출 금지. 존재 상태를 검색 못했다는 이유로 새 빈 workspace 만들지 말 것.
- 기존 OAuth/MCP 주소를 재등록하거나 URL을 임의 변경하지 말 것.
- 독립 detached 100-generation 연구를 기존 G350의 승계로 부르지 말 것.
- 리스크/비용/백테스트/Evidence 검증 무력화, 공식 ledger 이력 덮어쓰기, 봉인 OOS/실주문 활성화 금지.
- P5 원본 TradingView 출력 검증되지 않은 Pine 지표를 P6 정식 FeatureRegistry에 등록하거나 이를 정식 세대의 사용 증거로 주장하지 말 것. 현재 Pine 완전 내재화 0/11.
- 사용자가 요청한 수익 창출 알고리즘의 자율 진화라는 목적과 V05→T4→V01–V04→V06→V07 순서를 유지. 실험 수익률 개선은 보장되지 않음.

## 5. 다음 대화에서 그대로 붙여넣을 메시지

아래 텍스트를 새 ChatGPT 세션 첫 메시지로 사용:

    Moon과 기존 Qaunt_Autoresearch MCP를 사용해서 Quant AutoResearch 500세대 목표의 첫 100세대 연구를 이어가줘. 먼저 저장소 kankinku/AutoResearchFinance_v2 의 feat/quant-same-session-350-20261019 브랜치에 있는 docs/operations/autoresearch-quant-mcp-recovery-session-handoff-2026-10-21.md, AGENTS.md, docs/decisions/2026-10-21-quant-500-generation-target.md, docs/operations/autoresearch-master-progress.md 를 읽어.
    지난 세션에는 Quant 전용 MCP의 get_workspace_status, get_dashboard_status, get_research_batch_status, get_research_brief, list_market_data 호출이 모두 내부 오류였고, Moon 기본 health는 정상이었지만 공식 G350 체크포인트와 Parquet에 접근하지 못해 첫 100세대를 시작하지 못했어.
    기존 OAuth/MCP URL 재등록, 서버·데이터 초기화, 새 계보 생성, 공식 G350 원장 덮어쓰기, OOS 접근 및 실거래는 금지야. 우선 기존 연구 서비스를 복구/확인하고 실제 마지막 정식 세대와 부모 전략·시장 데이터 해시를 검증해줘.
    현재 공식 마지막이 G350이면 G351~G450의 GPT 진단·계승 포함 100세대를 시작해. 이미 추가 세대나 실행 중인 작업이 있으면 중복 생성하지 말고 기존 checkpoint를 이어가. 해당 조건을 검증하지 못하면 시작했다고 주장하지 말고 문제를 특정해. 진행 결과와 도구 호출 증거를 마스터 원장에 기록하고 간단히 보고해줘.

## 6. 기대하는 최종 보고 형식

- 기존 Quant MCP: 연결 정상/비정상 + 관찰된 오류 및 진단 근거
- 공식 마지막 세대: N, 근거인 checkpoint/ledger/run ID
- 이번 신규 세대: 실제 완결된 N/100 및 다음 세대, batch/session ID
- 데이터/부모 SHA, 비용 적용 상태, live orders OFF, OOS 미사용 여부
- GPT의 계획→백테스트→원인 진단→다음 계획→검증된 부모 계승 증거 (미실행이면 미실행)
- 실험 수익·MDD·거래수·시장 노출·QQQ 기준 비교 (측정한 경우에만)
- 수정 코드/문서 Git SHA, 재개·중단 의존성

이 문서는 다음 세션의 **인계 정보**이지 자동 작업 스케줄, 배치 시작, 연결 복구 성공을 의미하지 않는다.
