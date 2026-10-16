# T4 — 세대별 벽시계 소요시간·평균 및 예상 표시

일자: 2026-10-16 KST. Q15/Q16/Q17에 따른 기존 연구 대시보드의 작고 독립된 가시성 개선. 원래 20문답과 범위잠금, 기존 ChatGPT MCP URL/OAuth/32개 도구, 논문/전략 원장, 주문OFF·NON-PIT 정책에 변경 없음.

## 기존 데이터에서 확인한 사실

- 기존 MCP `cycles.sqlite.generations`는 원본 hash/계측결과만 있고 `created_at`, `started_at`, `completed_at`가 없었다. `gateway.sqlite.stages/experiment_reports`에도 해당 타임스탬프가 없다.
- 그러므로 과거 1~36세대 소요시간은 *알 수 없다.* 파일 수정시각, 서버 로그의 응답시간, 고정 시각 또는 세대 간 추정으로 재구성하지 않는다.
- 기본 ChatGPT MCP는 외부 모델 입력이 있어야 다음 세대가 진행된다. 해당 시간의 ETA는 자동 학습기의 진행시간으로 오인하지 않도록 **추정 불가**로 표시.

## 새 기능과 집계 정의

- `application/academic_checkpoint_service.py`: 기존 Gateway DB 내 별도 보조 `generation_timings` 테이블. 정상 `submit_algorithm_plan` 접수 시 해당 세대 `start_utc` 1회 기록, 원본 G + S7 통제실험의 DB 기록 검증 후 `end_utc` 및 완료된 G `evidence_hash` 저장. 원본 evidence/StrategyIR/가격/체결/DB 변경 없음. 재제출·재조회 시 시간 값 불변. 무결성/중복 오류에서는 새 레코드를 만들지 않는다.
- `dashboard/academic_timing.py`: 읽기 전용, 완료 세대 원본 SHA와 보조 시간의 SHA 일치, 유효한 timezone-aware ISO 시각·시간 역행·범위 벗어난 세대 거부. 보조 테이블 없는 과거 원장은 호환 표시(측정 개수 0, 평균 없음). 정상 측정한 완료 세대만 평균에 포함한다.
- **단위:** `start_utc`는 GPT가 Plan을 작성하기 시작한 시각이 아닌 MCP Plan 접수 완료시각; `end_utc`는 진단+S7 저장 완료시각. 사이에 모델 대기·재개가 있으면 포함되는 **벽시계 경과시간**, 순수 CPU/GPU 계산시간이 아니다.
- 기존 진행 카드 **바로 아래** 3개 값: `이번 세대 경과시간`(plan staged 이후), `완료 세대 평균 소요시간`(실제 측정 개수 표시), `다음 세대 예상 남은시간`. 현재 기본 GPT가 입력 대기라면 예상 남은시간을 허구로 산출하지 않고 **예측 불가**로 명시한다. 역사 테이블에는 각 세대 소요시간 열 추가; 과거 측정 전 세대는 `기록 없음`.
- 대시보드는 원래대로 읽기 전용 API(3초 polling)이며 주문/Start/Stop 쓰기 엔드포인트 추가 없음.

## 테스트·운영 적용 기준

- 테스트: 실제 ScriptedResearcher의 plan→diagnosis→S7 기록에서 시각·원본 세대 SHA 바인딩, 기존 완료 G의 시간 미기록 대응, 보조 테이블 위조시 fail closed(HTTP 503). 기존 대시보드·MCP 복구/도구·20문답 거버넌스 회귀 검사, Ruff/Mypy(스코프)·Node 정적 검사.
- 기존 세션 36/100 및 S7 36/36 유지; 계측은 **운영 MCP 코드 적용 이후 제출되는 G37부터 시작**. `generation_timings`는 원래 gateway DB에 추가되는 보조 테이블로 운용. 운영 배포 중 URL/OAuth/시세/실주문 권한 변경 금지.
- 시간 평균이 실측으로 채워지기 전까지 분·초를 임의 생성하지 않으며, 사용자/모델 대기로 다음 세대 완료시각을 약속하지 않는다.
- 고정 잔여 순서: T4 G37~100 GPT 진화/랜덤 비교 → V01~V04 외부 PIT/OOS → V06 Paper-only → V07 GO/NO-GO.
