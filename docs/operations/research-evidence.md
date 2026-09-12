# 실행별 연구 증거와 실패 Knowledge

`run-generation`, `repeat-research`, `autoresearch`의 로컬 평가가 실행별 증거를
저장한다. 같은 세대 번호와 후보가 반복돼도 독립 실행은 섞이지 않는다.

```powershell
python cli.py research-evidence --state-dir state
python cli.py research-evidence --state-dir state --run-id <research_run_id>
python cli.py research-evidence --state-dir state --output evidence.json
```

HTTP는 `GET /api/research-evidence?run_id=<research_run_id>`, MCP는
`get_research_evidence`와 선택 인수 `research_run_id`를 사용한다. 정적 대시보드
홈의 연구 증거 영역도 같은 함수를 조회한다. 조회는 증거를 생성하거나 수정하지
않는다. 원장 손상은 `INTEGRITY_ERROR`이며 HTTP 503, CLI 종료 코드 1로 전달된다.

## 저장과 복구

- `state/system/research-evidence/evidence.sqlite`: run, manifest, attempt,
  generation, end 이벤트를 저장하는 추가 전용 원장. SQLite 트랜잭션과
  이벤트 ID·종류·내용 체크섬으로 부분 쓰기, 충돌, 내용 변경을 구분한다.
- 같은 ID·같은 내용의 재전송은 중복 저장하지 않는다. 다른 내용은 오류다.
  원장 UPDATE/DELETE는 트리거로 거부한다. 종료된 실행에 새 이벤트를 붙일 수 없다.
- `knowledge.json`: 원장에서 복원 가능한 누적 보기. 기존 known_good/known_bad/
  unexplored와 확장 필드를 유지한다. projection 쓰기가 중단되면 다음 연구
  context 조회에서 원장으로 다시 채운다. 새 반복 연구 실행 자체는 새 run ID를
  받으며, 중단된 루프를 자동으로 재개하지 않는다.
- 다음 제안에는 최대 20개의 실패 패턴을 최근 발생 순으로 전달한다. 동일 비교 조건,
  후보 hash, 실패 게이트 조합은 한 항목으로 묶고 전체 발생 횟수를 제공한다.
  관측된 게이트 실패를 원인 확정으로 바꾸지 않으며 `causal_status=UNKNOWN`이다.
- 원장과 실행 결과는 로컬 전용이다. Git에는 가격, 공급자 오류 원문, 자격증명,
  계좌 식별자를 저장하지 않는다. `runs/` 아래의 별도 상태 디렉터리도 사용할 수 있다.

## 비교와 분모

manifest에는 원본 IR·데이터·시계열 hash, 기간, zone, 평가 설정, 실제 비용 모델,
평가 코드 hash, Python/주요 라이브러리 버전을 기록한다. seed와 탐색 설정은
실행/시도 기록에 별도로 보존한다. 같은 실행에서 데이터나 평가 조건이 바뀌면
중단하고 새 실행을 요구한다. `memory.research_evidence.compare_runs`는
comparison_key가 다른 실행을 한 비교로 합치지 않는다.

| 필드 | 의미 |
| --- | --- |
| completed_generations | 최종 세대 이벤트 수. 전략 통과 수가 아님 |
| fallback_rate | 최종 fallback 세대 / 최종 세대 |
| candidate_count | 최종 선택된 평가 시도들의 후보 수 |
| all_attempt_candidate_count | repair 등 모든 평가 시도의 후보 수 |
| unique_candidate_count | 최종 평가 후보의 고유 hash 수 |
| pass_rate | SURVIVOR 또는 FRONTIER 후보 / 실제 최종 평가 후보 |
| repeated_failure_rate | 같은 실행 내 이전 후보 hash·게이트 조합의 재실패 / 실패 수 |
| validation_survival | fold 평가가 실제 있는 후보만 분모에 포함한 walk-forward 통과율 |
| generations | 세대별 best_attempt와 best_passed를 구분한 성과 자료 |

분모가 없으면 null이다. 실패한 평가 시도는 빈 후보 목록과 오류 종류만 저장한다.
주입한 외부 evaluator가 검증된 후보 자료 없이 집계 숫자만 반환하면
`UNVERIFIED_EVALUATOR`로 기록하고 후보 통과율을 만들어내지 않는다.

sealed OOS는 메타데이터 단계에서 차단하며 일반 연구 프로세스로 행을 읽지 않는다.
`validation_survival`의 범위는 manifest의 입력 zone 안에서 수행한 walk-forward다.
sealed OOS 생존율, 가설 성공률, branch extinction, 실행에 귀속된 Champion 개선율은
해당 검증 이벤트가 없어 `NOT_MEASURED`이다. Frontier 분포는 현재 저장 상태의 별도
스냅샷이며 특정 연구 실행의 개선으로 귀속하지 않는다.

기존 `test-records.jsonl`은 유지한다. 새 행에는 research_run_id와 attempt_id를
추가하고 기존 대시보드 타입이 이를 허용한다. 실행 ID가 없는 과거 행은
`LEGACY_UNSCOPED`로만 집계한다. 과거 100세대 요약과 누적 원장을 임의로 결합하지 않는다.

## 2026-09-12 development 데이터 연결 검증

기존 QQQ 가격 4,190행, QQQ/Nasdaq 시계열 8,380행의 development 데이터를 사용해
golden_cross 기준 전략 3세대와 fast SMA 기간 5/10 탐색 3세대를 실행했다.
두 실행은 같은 comparison_key를 가졌다. 기준은 3회 평가·고유 후보 1개,
탐색은 6회 평가·고유 후보 2개였으며 모두 REJECT였다. 두 실행의 반복 실패율은
각각 2/3이다. 비용/benchmark/실패 게이트와 Knowledge 저장 경로를 검증한 결과다.

이 결과로 알파 생성, 가격 공급원 정확성, sealed OOS 일반화는 입증되지 않는다.
다음 작업은 별도 Failure Analysis 브랜치의 계약 검토와 데이터 provenance 확인이다.
그 이후에 정상 제안과 fallback을 분리한 장기 실험으로 확장한다.

## 구현 검증

2026-09-12: 전체 pytest 572 passed, Ruff 통과, mypy 136개 source file 오류 0.
변경 파일 비밀정보 검사 통과. 보호된 아키텍처 문서는 Git 원본과 바이트 일치.
Streamlit 테스트는 운영자 상태 파일 의존을 제거하고 독립된 세대 fixture로 검증한다.
