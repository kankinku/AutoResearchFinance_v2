# Quant Autoresearch T4 후속 — 사전고정 무작위 10세대·프로세스 복구·실 DB 집계 재생

기준: 2026-10-16 UTC/KST. 상위 잠금 [원본 20문답과 확정 범위](../decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md). 직접 대응 Q02 Q06 Q07 Q08 Q15 Q17 Q20. 기존 확정 순서 **T4 계속 → V01~V04/T5 → V06 → V07** 변경 없음.

## 1. 실제 연결된 Quant MCP에서 실행한 것

- 기존 인증된 `Qaunt Autoresearch` 앱과 **기존 OAuth/MCP URL/32 tools**, `orders_enabled=false` 유지. 과거 GPT 10세대 직접 실행(세션 `49d3033496844ea391f7bdc983da3fc9`)을 비교 대상으로 사용.
- 무작위 후보 생성기 `scripts/t4_preregister_random_control.py`에서 seed `20261016`를 사용하여 검증된 6개 지표의 합성 규칙으로 생성한 **10개 typed AlgorithmPlan**을 *해당 무작위 후보의 백테스트를 실행하기 전에* `735b88e` GitHub 커밋/Push에 고정. 선정된 10개 계획 cohort SHA-256 `1667fa8ca0fac203a2ffeeb4b5fc91131d080caaaa59e7ee25120eb43d41ee93`. 이전 GPT 10 결과를 이미 알고 있는 상태에서 만든 설계이므로 **두 연구군에 대해 완전 블라인드인 사전등록은 아님**.
- 실제 MCP `start_algorithm_research(10)`, 각 세대의 고정 Plan 제출, canonical 재무 백테스트·실거래 건별 감사, 구조화된 S2 Diagnosis, `submit_algorithm_diagnosis`와 `evaluate_algorithm_experiments`를 호출해 무작위군도 **10/10 COMPLETED**. 무작위 전략은 결과에 맞춰 변경하지 않음. S7 진단은 전 세대 `plan_vote_score > 0.9`로 고정된 통제 가설이며, GPT군의 적응적 세대별 가설과 **동등한 가설 품질/모델 추론비용 비교는 아님**.
- 무작위 MCP 세션 `bb06ec457ee443bd9fb22273457c054f`. GPT군/무작위군 모두 **서로 다른 전략 10개, 보존된 원본 plan·metric·체결과 S7 10개**. 양측 예산은 *부모전략 10회 백테스트 + 1세대당 S7 1회 = 각 10+10*을 맞춤. 단일 seed, 단일 자산, 같은 과거 개발 구간 재활용.

## 2. 같은 비PIT QQQ 2020~2025 개발 데이터의 관찰 비교

| 측정치 (재사용 DEVELOPMENT, non-PIT) | GPT 10세대 | 고정 무작위 10세대 |
|---|---:|---:|
| 실제 연구 세대 / 서로 다른 전략 | 10 / 10 | 10 / 10 |
| 원세대와 S7 원장 완전 해시 검증 | 10 / 10 | 10 / 10 |
| 누적수익률 평균 | 34.94% | 30.07% |
| 누적수익률 중앙값 | 33.34% | 23.55% |
| **최고** 단일 누적수익률 | 64.58% | **101.87%** |
| 최대낙폭(MDD) 중앙값 | 22.92% | 28.41% |
| Sharpe 중앙값 | 0.4663 | 0.3394 |
| S7 기대 방향 일치 | 8 | 9 |
| S7 기대 방향 불일치·무효 | 불일치 1, 무거래 퇴화 1 | 무효 효과 1 |

**해석:** 중앙값 차이는 측정됐지만 GPT의 장기 연구 우월성을 입증하지 못한다. GPT군이 먼저 존재했고, 무작위 대조 계획의 생성 방식과 S7 가설 품질·적응성이 다르다. 무작위군 최고 단일 전략이 GPT군보다 높다. 10+10 후보에 통계적 신뢰구간/다중검색 보정/복수 seed/완전 사전등록/독립 기간/PIT 자료가 없으므로 수익 우위나 원인을 추론하지 않는다. 두 군의 `orders_enabled=false`, OOS 미개봉, 실현 순수익 승인 false.

## 3. 운영 DB 원본 읽기 전용 SHA 재감사

- 실제 기존 운영 DB `state/moon-http/research/academic-gpt-checkpoints/{cycles.sqlite,gateway.sqlite}` 를 **SQLite URI mode=ro** 로만 열고, `AcademicCycleService._row_evidence_hash`의 연속 generation 해시와 `content_hash`로 S7 보고서, parent 세대, 가설 IDs, 중복/원본 계획(무작위 등록 SHA)을 재검사.
- 두 세션 각각 generation 10건/S7 10건·서로 다른 semantic hash 10건 모두 일치. 파일 `docs/operations/evidence/quant-validation-20261016/t4-gpt-vs-preregistered-random-10x10-readonly-audit.json`에 결과와 개별 증거 해시 보존.
- **운영 원본/인증/DB 작성·MCP 재시작/실주문 작업 없음.**

## 4. 실제 비정상 종료·복구 시험

- 신규 `tests/integrations/test_t4_abrupt_process_recovery.py`: 격리된 별도 `multiprocessing.spawn` 워커가 typed 1세대 연구 증거를 실제 파일 DB에 커밋하고 **`os._exit(91)`로 S7 게이트 수신 전 비정상 종료**.
- 새로운 서버 인스턴스가 고정 data/catalog/evidence hash를 검사해 `reconcile_algorithm_research`로 S7 복구, 복구 호출 재시도 멱등 확인. 2세대 추가 완료, 첫 세대 해시 불변, 2개 S7 보고서 SHA/원세대 대조, 운영 주문 off 검증.
- 첫 `fork` 시험은 PASS나 Python 멀티스레드 경고 발생 → `spawn`으로 변경해 **관련 복구/거버넌스 10 tests PASS**(신규 실제 abrupt 1, 기존 D02·범위 잠금 9), Ruff PASS. 별도 실제 운영 HTTP/OAuth 서비스의 강제 kill/재시작/롤백은 *실시하지 않음*.
- 해당 테스트를 위한 코드 commit `0552766`. 코드 변경은 사용자의 본래 요구(Q15 중단 재개)의 검증 범위이며 새로운 프로덕션 기능이 아니다.

## 5. 실제 DB 스냅샷에서 집계 수정 재실행

- 이미 개발 브랜치 `32e495e`에서 고친 최종 S7 집계 오류를 **실제 운영 DB의 SQLite 백업을 만든 임시 상태 디렉터리**에 적용해 안전 재실행. 원본 DB 변경·운영 서비스 재배포 없음. 원본 QQQ 파일은 읽기 전용.
- `AcademicMCPCheckpointService.get`의 새 `final_report`: GPT 10건·무작위 10건 모두 `tested_hypotheses=10`, `all_proposed_hypotheses_measured=true`, `gateway_s7_count_source=HASH_VERIFIED_IMMUTABLE_GATEWAY_REPORTS`. 백엔드 모델 자율성 `model_autonomy_verified=false` 그대로, 거래 주문 비활성 그대로. 증거 `t4-corrected-gateway-real-snapshot-readonly-replay.json`.
- 운영 서버는 **기존 고정 배포 `da2331d`에서 가동** 중이므로 사용자에게 노출되는 옛 최종 집계 `tested_hypotheses=0`은 재배포 전까지 변경되지 않는다. 이 사실을 숨기지 않고 별도 기록.

## 6. T4 남은 수락 기준 / 다음 단계

- **T4-10 통제 시연:** GPT 10 + 무작위 10 완료, 세대마다 실측 S7 1회·원장 결속 실증. 동일 예산의 제한적 비교만 시행. GPT 장기 우위는 검증 안 됨.
- **T4 운영:** 안전한 릴리스/전면 회귀 후 `32e495e`의 실제 운영 버전 집계를 확인해야 함. 이번 턴 미배포.
- **T4-100:** 아직 **0/100, 새 세션 없음**. 진짜 GPT 계획·체결 원인 진단·다음 계획 100개, 오류·재시도·예산·사용자 중지·실행 기간의 일관성, 복수 seed/확정 기준선 및 모델 호출 provenance 검증 필요. 백엔드 `real_model_connection_verified=false`를 임의 true로 승격시키지 않음.
- 독립 PIT·봉인 OOS·여러 시장 경제적 순수익·GO/실거래 허가는 계속 **BLOCKED**. 다음 작업은 **동일 T4의 기존 MCP 운영 집계 배포 게이트 검토 및 100세대 연결 실증**이며 새로운 지표/ETF 수동 수익 최적화로 방향을 바꾸지 않는다.
