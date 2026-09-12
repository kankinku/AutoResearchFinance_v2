# Research Evidence 개선 설계 초안

작성일: 2026-09-12
상태: 사용자 승인 후 첫 구현 단위 구현 및 검증 완료
기준: master / faf8f08 및 현재 작업 디렉터리. 기존 dashboard/state.py 수정과 로컬 상태 변경은 사용자 작업으로 보존한다.

## 목적

보고서의 우선순위를 실제 실행 경로에 연결한다. 실행 완료, 가설 실행 성공,
전략 평가 통과, 검증된 성과 개선을 별도 지표로 기록하고 실패 경험이 다음
연구 입력으로 이어지게 한다. 기존 Strategy IR, 평가 기준, 주문 권한 경계를 유지한다.

## 현재 확인한 사실

- 기준 검사: python -m pytest -q → 546 passed in 18.81s;
  ruff check . → 통과; python -m mypy . → 131개 source file 오류 없음.
- state/system/autoresearch.json: requested/completed 100/100,
  COMPLETED_WITH_FALLBACKS, orders_enabled=false.
- 해당 실행의 세대 상태: COMPLETED 33, REPAIRED 14, FALLBACK 53.
  평가 요약의 REJECT 합계는 800이다. 이는 고유 전략 800개를 의미하지 않는다.
- 현재 Champion은 EMPTY, Frontier family는 0이다.
- 현재 test-records.jsonl 전체는 998행이며 dataset_hash가 모두 존재한다.
  실패 게이트는 robustness 998, validation 868, qqq_cagr_delta 820,
  annual_trade_count 972, fast 8이다. 한 결과에 여러 실패가 공존한다.
  이 998행을 위 100세대 실행의 800건과 같은 집합으로 취급해서는 안 된다.
- GenerationPipeline은 knowledge를 생성하지만 run_local_evaluation은
  test-records.jsonl만 저장하고 해당 knowledge를 저장하지 않는다.
  현재 knowledge.json의 known_good/known_bad/unexplored는 모두 비어 있다.
- build_research_context는 최근 테스트 관측을 읽으므로 연구 피드백이 완전히
  없는 것은 아니다. 다만 장기 실패 기억의 누적 저장 경로가 빠져 있다.
- dashboard/ledger.py의 run_id는 candidate_hash와 generation으로 구성되어
  독립 실행 간 충돌을 피하는 실행 식별자가 아니다.
- 기존 FunnelResult에는 데이터 hash, benchmark hash, 성과 지표,
  validation_folds, yearly_metrics, 게이트 판정이 이미 있다.
- runs/qqq-research-20260902-long에 가격 4,190행과 시계열 8,380행의
  development Parquet가 있다. 메타데이터 존재를 확인했으며, 공급원 정확성,
  조정가격 처리, 분할 설계와 sealed OOS 적격성까지 검증한 것은 아니다.
- codex/failure-analysis-root-cause-replay와 codex/failure-ledger-search에
  관련 구현이 별도로 있다. 현재 master의 구현으로 간주하거나 재작성하지 않는다.

## 접근 비교와 선택

1. 권장: 기존 결과 구조 위에 실행별 Evidence와 Knowledge 저장을 연결한다.
   비교 가능한 증거와 누적 피드백을 먼저 확보하며 기존 브랜치와 충돌 범위를 줄인다.
2. Failure Analysis 브랜치부터 전면 통합한다. 결정 추적과 replay를 빨리 가져올 수
   있지만 core/backtest부터 UI까지 46개 파일에 걸친 변경 검토가 선행되어야 한다.
3. 바로 100~500세대를 재실행한다. 실행량은 늘지만 fallback, 중복 평가,
   누락된 기억 저장의 영향을 분리하기 어렵다.

1번을 첫 구현 단위로 선택하고, 2번의 필요한 부분을 검토한 뒤 장기 실행으로 확장한다.

## 첫 구현 단위: 실행 증거와 누적 Knowledge

### 실행 계약

- runtime/research_loop.py에서 실행마다 독립 research_run_id를 생성한다.
- 최초 실행에 manifest를 기록한다. IR hash, 가격/시계열 hash, 기간과 zone,
  정책·비용 설정·실행 코드 식별자, seed, 탐색 설정과 요청 세대 수를 포함한다.
- manifest의 비교 조건을 comparison_key로 묶는다. 다른 key의 실험은 한 개선
  곡선으로 합치지 않는다. seed는 개별 실험의 재현 조건으로 보존하며 비교 조건과
  구분한다. 실행 도중 입력이나 정책 변경을 감지하면 새 실행을 요구한다.
- 새 산출물은 Git에서 제외한 state/system/research-evidence 아래 저장한다.
  원시 가격, 자격증명, 계좌 식별자, provider 원문 오류는 포함하지 않는다.

### 결과와 저장

- orchestration/evaluation_runner.py가 기존 FunnelResult에서 제한된 증거를
  구성하고 research_run_id, generation, attempt_id와 연결한다.
- 평가 시도와 확정된 세대 결과를 구분한다. repair/fallback 시도는 모두 기록하되
  최종 세대 수, 후보 통과율에 중복 반영하지 않는다.
- 같은 기록의 재전송은 멱등 처리한다. 같은 식별자의 다른 내용은 무결성 오류다.
  중단된 쓰기와 재시작 시 부분 기록을 식별하며 성공으로 집계하지 않는다.
- 세대별 정상 제안/수정/fallback/실패 수, 평가 건수와 고유 후보 수,
  게이트별 실패 수, 가장 좋은 시도와 통과 후보의 성과를 따로 기록한다.
- 기존 Knowledge 필드를 보존하면서 안정적인 실험 ID로 병합·중복 제거한다.
  누적 원장은 보존하고 LLM 입력만 최근성·빈도에 따라 제한한다.
- 실패 게이트는 관측된 실패로 저장한다. 비용 원인 배제나 국면 의존성 같은
  인과 해석은 실험 증거 없이 확정하지 않는다. UNKNOWN을 허용한다.

### 지표 정의

- 실행 완료율: 최종 기록이 존재하는 세대 / 요청 세대.
- fallback 비율: 최종 경로가 fallback인 세대 / 최종 기록 세대.
- 후보 통과율: 실제 평가되고 명시적 통과 판정이 있는 후보 / 실제 평가 후보.
  분모가 없으면 null과 사유를 반환한다.
- 반복 실패율: 같은 comparison_key 내에서 이전에 실패한 후보 hash와 게이트
  조합이 다시 실패한 건수 / 실패 건수. 원시 비율과 고유 후보 수를 함께 표시한다.
- 검증 생존율: 수행 완료된 validation 대상만 분모에 포함한다.
  development 내부 walk-forward를 sealed OOS 생존율로 표시하지 않는다.
- sealed OOS 생존율: 별도 승인된 검증 산출물이 없으면 NOT_MEASURED.
  반복 연구가 sealed OOS를 열거나 결과를 다음 가설 입력으로 사용하지 않는다.
- Champion 개선율은 실제 승격 기록과 비교 가능한 이전 Champion이 있어야 한다.
  초기 EMPTY에서 최초 승격은 초기화로 구분하고 best-attempt 개선과 분리한다.
- Frontier 다양성은 실제 저장된 적격 family 수와 분포로 계산한다.
  가설 성공률과 branch extinction은 가설·부모 ID의 충분한 기록이 없으면
  추정하지 않고 NOT_MEASURED로 남긴다.

### 소비 경로

- CLI에 research-evidence 조회/내보내기를 추가한다. 기존 명령의 기본 동작과
  test-records.jsonl 독자를 유지하며 새 필드는 추가 방식으로 제공한다.
- 다음 Research Director context에 허용된 누적 실패 요약을 전달한다.
  LLM은 요청만 출력하고 DB 쓰기·평가 수정 권한은 갖지 않는다.
- Dashboard와 MCP는 같은 읽기 전용 요약 함수를 사용한다. 대시보드 시각적
  재설계는 별도 작업으로 두고 기존 구조에 실행 증거 상태를 표시한다.
- 과거 원장은 LEGACY_UNSCOPED로 조회 가능하되 새 run_id를 임의로 부여하여
  재현된 실험으로 바꾸지 않는다. 현행 998행과 800건도 자동 결합하지 않는다.

## 연결 대상

| 계층 | 작업 |
| --- | --- |
| core/data, core/backtest, core/validation | 기존 hash·zone·평가 계약 재사용 |
| orchestration | 평가 결과와 run/generation/attempt 연결, 저장 완료 보장 |
| evaluation | 기존 게이트·fold 결과 요약, 관측과 인과 추정 구분 |
| memory/state | append-only 증거, 멱등 병합, 기존 Knowledge 보존 |
| runtime/Mimir | 실행 식별자, 최종 세대 상태, 다음 context 연결 |
| CLI | 읽기 전용 증거 조회와 내보내기 |
| Dashboard/MCP | 동일 요약 함수의 소비자 |

## 검증과 완료 조건

생산 코드를 수정하기 전에 아래 행위를 검증하는 실패 테스트를 작성한다.

1. 같은 데이터·같은 후보·같은 세대 번호의 독립 실행이 서로 섞이지 않는다.
2. repair 후 fallback도 최종 세대 하나로 집계하며 중복 쓰기로 수치가 늘지 않는다.
3. 모든 후보가 탈락해도 실패 Knowledge가 저장되고 다음 연구 context에 도달한다.
4. 기존 known_good/known_bad/unexplored와 미지의 호환 필드를 덮어쓰지 않는다.
5. 데이터나 정책이 다르면 개선 비교를 거부한다. 결측값은 성공이나 0으로 바꾸지 않는다.
6. walk-forward 증거를 sealed OOS로 보고하지 않고 인과 원인을 만들어내지 않는다.
7. 중단된 쓰기·충돌 ID·손상 레코드를 식별한다. 최신 실행 상태만으로 성공을 주장하지 않는다.
8. CLI/MCP/대시보드가 같은 원장에서 같은 숫자를 반환한다.

집중 테스트 후 전체 pytest, Ruff, mypy를 수행하고 변경 파일만 원자적 커밋한다.
기존 아키텍처 문서는 byte-for-byte 유지한다. 이 단계의 PASS는 구현 검증이며
알파 생성이나 수익성 입증을 뜻하지 않는다.

## 후속 순서

1. 위 첫 구현 단위를 완료하고 작은 고정 데이터 실행으로 저장→조회→다음 입력을 확인한다.
2. 두 기존 실패 분석 브랜치를 현행 코드와 대조하여 재사용할 계약과 충돌을 정리한다.
   특히 기존 데이터·백테스트 변경은 검토 및 검증 없이 가져오지 않는다.
3. 실제 데이터 provenance, benchmark 조정 방식, 비용과 기간, 개발/검증 분할을
   고정하고 소규모 실행에서 정상 제안과 fallback을 분리하여 측정한다.
4. 조건을 충족하면 100세대 실행으로 확대하고 대조 탐색과 동일 조건에서 비교한다.
   500세대로의 확대는 100세대 결과 및 실행 비용을 확인한 뒤 결정한다.
5. 검증된 failure attribution과 hypothesis/experiment lineage를 통해
   Observation → Hypothesis → Experiment → Knowledge를 확장한다.

보고서의 전체 방향은 유지하되 첫 구현 완료를 전체 개선 완료로 표시하지 않는다.

## 구현 결정

추가 전용 원장은 SQLite 트랜잭션으로 구현했다. ID/종류/내용 checksum과 UPDATE/DELETE 차단을 사용하며 JSONL의 부분 행 쓰기 위험을 피한다. 기존 test-records.jsonl은 호환용으로 유지한다. Knowledge는 원장에서 복원하는 projection이다. 상세 사용법은 docs/operations/research-evidence.md를 따른다.
