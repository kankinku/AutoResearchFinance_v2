# T4 P0-4 — 수량 조절에 의한 기계적 리스크 감소와 실제 체결·신호 변경의 경제성 구분

기준 2026-10-19 KST · 기존 20문답/개발 단계 순서 변경 없음 · 동일 QQQ non-PIT 개발자료의 **읽기 전용 재해석** · 운영 미배포

## 1. 재작업 방지 및 수정 원인

- 기존 `research/llm/economic_feedback.py`는 실제 원장 SHA/원본 증거·S7 후속 자식의 비용 포함 equity, 4개 회고적 개발 창의 drawdown, 체결 수를 검증하고 `return_better/worse/unchanged`와 비용·회전율·시장노출·QQQ의 **후속 확인 필요성**을 이미 명시했다. `adaptive_direction.py` 역시 `SIZE_ONLY_CHANGED`와 `SIGNAL_TIMING_CHANGED`를 분리했다.
- **재발 간극:** 경제성 `review_candidates`에는 수량만 줄여 기계적으로 MDD가 낮아진 자식도 높은 development-equity 값 때문에 섞일 수 있었다. GPT는 이를 실제 매매 신호 개선 후보로 잘못 사용할 수 있었고, 동일한 QQQ buy-and-hold와의 구체적 gap은 해당 S7 자식 요약에 없었다.
- 기존 S7·경제성 계산기·MDD 통제 실험·부모 선택·원장 구조/지표 레지스트리를 재구현하지 않고 **경제 피드백의 읽기 전용 후보 분류만 보강**했다.

## 2. 변경 사항과 계약

- `build_economic_feedback()`에 선택형 `qqq_total_return` 입력. 현재 `AcademicMCPCheckpointService._context()`의 같은 pinned 데이터/동일 비용 모델로 계산한 `benchmark_comparison.qqq_costed_buy_and_hold.total_return`을 전달한다. 타 종목에서는 `None`이므로 QQQ 비교를 창작하지 않는다.
- 기존 해시 확인이 끝난 S7 `execution_delta`를 재사용해 `SIGNAL_TIMING_CHANGED`(실제 추가/삭제된 체결 또는 시점 변화), `SIZE_ONLY_CHANGED`(수량만 변화), `UNCHANGED_EXECUTIONS`(변화 없음)를 **서로 배타적**으로 분류한다. 기존 `review_candidates`는 수익 개선 + 최소 활동 + 실제 신호 변화가 확인된 자식만 표시하고, 수량만 바뀐 자식은 별도의 **작고 비승격적인** `mechanical_size_risk_reviews`로 분리한다.
- 같은 원장 안에서 비용 포함 거래금액, 수수료, 변경 이벤트 수, 회고적 4구간 각각의 수익/낙폭 개선·악화, 수익률 편차(%p), costed raw-QQQ 단순 보유 상대 gap을 제공한다. `signal_review_candidates`는 중복 장문 StrategyIR 없이 요약만 제공해 MCP 컨텍스트 증가를 제한한다.
- 전체 기간 MDD는 해당 S7 실험의 검증 metric이 `max_drawdown`일 때만 제공한다. **자식 시장 노출률은 기존 S7 요약에 측정값이 없으므로 `child_exposure_verified=false`**, 승격 전 기존 replay의 전체 검증이 필수다. `fill_count / 2`는 닫힌 거래 수 *추정*이므로 최종 거래 수 증명도 아니다.
- 기존 `gate_research_direction()`에서도 수량만 변경되면 `TEST_HYPOTHESIS`, 거래 시점·수량 모두 변화가 없으면 `EXPLORE`로 강등한다. 일반 전략 가설에서 실제 신호가 바뀌고 economic 방향이 긍정인 경우에만 과거처럼 개발용 검토 후보를 유지한다. 원장 증거·S7 실험 점수 자체는 소급하여 다시 쓰지 않는다.
- 운영 배포/자동 계승/실주문/OOS 승인/모델 출처 인증은 이 절편에 포함되지 않는다.

## 3. 실제 53세대 해시 일치 연구원장의 현황

`c1eadd67bad94d7ea182dc274224dbce`, 각 `gateway.experiment_reports` 53건을 다시 검증. 해당 임의·템플릿 기반 연구 루프의 실패를 성공으로 재해석하지 않았다.

| 실측 체결 분류 | S7 수 | 개발 수익 개선 | 개발 수익 악화 | 불변 |
|---|---:|---:|---:|---:|
| 실제 진입/청산 시점 변경 | 19 | 8 | 11 | 0 |
| 포지션 크기만 변경 | 29 | 6 | 23 | 0 |
| 실제 체결 변화 없음 | 5 | 0 | 0 | 5 |
| **총계** | **53** | **14** | **34** | **5** |

- G53 수량 축소 S7: costed parent +44.7472%, child +32.5198% (−12.2274%p), 부모 MDD 8.6496%→자식 6.5628%, **실제 신호/시점 변경 없음**. 부모 거래 수는 40회(80 fills), 비용은 부모 약 $792.67, 자식 약 $564.49. 동일 기간 QQQ 단순 보유 raw price+일회매수 비용의 누적 수익률 +187.7724%, G53 자식의 gap −155.2526%p.
- G17, G21, G25 등은 실제 시점/거래 변동을 보였으며 개발기간 costed equity의 개선도 관찰됐다. 그러나 일부 회고적 창에서 MDD가 악화됐고 동일 구간 QQQ보다 수익이 작다. **8건을 독립적 초과수익 발견으로 인정하지 않는다.**
- QQQ raw-price는 배당 재투자 포함 총수익률 데이터가 아니므로 장기 투자 경제성의 절대 기준이라고 과장해서도 안 된다. 이 비교는 기존 데이터와 비용 모델의 같은 구간 기술 비교에 한정된다.

## 4. 테스트와 남은 작업

- 신규 단위 및 실운영 53세대 읽기 전용 테스트 `tests/research/test_t4_p0_4_signal_economics.py`: 수량만 줄인 S7 개선의 신호후보 제외, 실제 체결 시점 변경의 분리, 수익 갭/비용/위험/윈도 집계, 음수 수수료/허위 이벤트/위변조 거부, 기존 원본 53세대 재해석.
- 기존 `tests/research/test_economic_feedback_p0.py`의 측정 증거와 기존 MCP·계승·P0-3 provenance 테스트를 함께 회귀. 정적분석 Ruff/MyPy 및 회귀 결과는 커밋 기록과 마스터 진행 원장에 갱신.
- **P0-5**는 이미 존재하는 `fixed_budget_arms.py` 및 과거 GPT/랜덤/국소 변형 동일예산 10세대 비교 코드를 재사용하여, `SIGNAL_TIMING_CHANGED` 후보의 비용·drawdown·시장 노출·QQQ 상대 격차를 비교하고, GPT가 실제 자유롭게 매 세대 판단하는지 출처 제한을 명시할 것. 인공 템플릿 50세대를 자율 GPT 대조군으로 오인하지 않는다.

현재 목표 세션은 53/100 유지, 남은 47세대 실행하지 않음. 기존 32 MCP·OAuth URL·주문 off·운영 체크아웃 SHA `54a515f` 불변.

## 5. P0-4 종료 검증·배포 경계

- 새 분류 경제성/실제 53세대 read-only 검증 및 기존 S7/연구방향/계승/P0-3 근거 추적/MCP/범위잠금 관련 회귀 **55 PASS / 0 FAIL (63.06초)**.
- 저장소 전체 Ruff PASS, Mypy **278 source files PASS**, 두 운영 SQLite 원장 `PRAGMA integrity_check=ok` (시행 전후 read-only 재확인). 전체 Pytest(1,700여 개)는 이번 작업에서 재실행하지 않아 전체 스위트 성공으로 주장하지 않는다.
- 단계 종료 코드 커밋은 개발 브랜치 `feat/quant-t4-p0-4-signal-economics-20261019`에만 반영한다. **운영 MCP 런처/컨테이너/URL/OAuth/32개 도구 및 원본 53/100세대 연구 DB에는 변경 없음.** 사용자에게 별도의 운영 배포 또는 수익성 검증 완료라고 알리지 않는다.
