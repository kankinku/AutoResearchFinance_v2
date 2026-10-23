# Quant AutoResearch V3 — C 교배 S2/P2/S7 + D 국면별 공용 현금 백테스트 2차 구현 (2026-10-23 KST)

상태: **코드 및 격리 개발 샘플 회귀 검증 PASS; 정식 체크포인트 연결 / 외부 LLM 자율 실행 / 실제 성과 개선 실험은 NOT DONE.**

## 변경 사항

### C. 복수 부모 교배의 검증 경로
- `research/indicator_engine/inherited_decision_audit.py`: 기존 정확히 100%인 진입 비중 제한만 완화해 StrategyIR의 고정 `position_size_pct`(0~100%)를 원본 canonical 수수료/체결과 대조할 수 있게 했다. `stop_loss_pct`, `take_profit_pct`, `trailing_stop_pct`, `daily_loss_action` 등 아직 독립 감사가 불가능한 위험 모듈은 계속 fail closed. 기존 핵심 BacktestEngine 수정 없음.
- `research/llm/composite_validation_v3.py`: 신규 개발 전용 진단 경로. 교배 부모 각자의 **실제 costed S2 audited replay**, donor role component hash 및 **자식의 실제 entry/exit/risk와 일치 여부**, 각 부모 feature/indicator alias 일치, signal vector registration 및 source replay/data 검증 → 자식 canonical S2 → `assess_child_risk`의 P2 → `compare_inherited_experiments`의 동일 데이터 S7 비교. 위험 심사 실패 시 통과 결과를 반환하지 않는다.
- 서로 다른 원본 feature replay를 가진 donor를 다룰 때 **각자의 S2 검증 신호 벡터를 충돌 검사하여 union**, 정렬 시점/다음 봉 간격과 새 replay hash로 자식 IR에 결합. 단일 재생 벡터에서 온 부모인 경우 기존 hash를 유지해 구형 S7 diagnostic receipt를 깨지 않는다. 위조된 자식 entry가 donor hash만으로 통과하지 못하도록 regression 추가.
- `research/llm/composite_crossover_v3.py`: G68/G192처럼 **서로 다른 counted 세대인데 legacy StrategyIR.id / StrategyIR.generation이 같은** 경우, counted generation과 strategy hash를 부모 ID에 포함해 합성 계보 손실 방지. 단위 사례에서 동일 기반 ID를 가진 서로 다른 3개 source가 자식에 모두 보존됨.
- **검증 한계**: `VerifiedDonor.replay_verified`의 boolean 및 제출된 `evidence_hash`/S7 `report_hash`는 이 adapter 자체가 original SQLite에서 조회해 재검증하지 않는다. caller가 ledger-bound verified sources로 전달해야 한다. 이번 tests는 재현 가능한 **작은 개발 fixture** + audit/S7/P2를 실행했지만 실 G452 데이터에 기반한 3개 donor를 이용한 전체 실험이나 counted generation commit을 증명하지는 않는다. 최종 GPT 모델 호출·공급자 증명 없음.

### D. 국면별 독립 전략과 하나의 공유 현금계정
- `research/llm/regime_portfolio_v3.py` 신규: **오직 development / 1-symbol / long-cash** 연구. 각 route는 독립 StrategyIR entry, exit, approved fixed-size risk, state/peak close, pending execution을 가지며 close(t) 신호를 **open(t+1)**에 실행한다.
- `RegimeRouterSpec` exclusive/weighted; **하나의 공용 cash**에서 신규 진입 예산을 계산, 100% 초과 또는 기존 포지션 때문에 부족한 cash는 예산 축소하고 마이너스 현금·레버리지는 금지. 국면 전환 시 `flatten_on_switch` 또는 `hold_previous_until_exit`, 국면 미일치/결측 신호에서는 신규 진입 금지.
- 같은 종목·같은 시가에 한 슬리브가 청산하고 다른 슬리브가 진입할 경우 **virtual subposition 내부 상계** 후 외부 **순주문 한 번에만 비용 부과**. 동시에 같은 방향 두 슬리브 진입 시 하나의 aggregated 순매수 주문 비용을 각 자식에 배분. 실제 거래가 아닌 계산용 가상 포지션 이동을 외부 체결이라고 주장하지 않는다.
- `research/llm/regime_ledger_audit_v3.py` 신규 독립 연구 장부 재구성: 연구 fill signal bar index=t, fill index=t+1, sleeve cost attribution 합계=단일 external net fee, 현금 흐름·재고·종가 NAV, leverage 없음, 각 외부 비용 CostModel 일치 및 전체 hash 증명.
- **검증 한계**: 이 adapter는 기존 AcademicMCPCheckpointService의 counted S2/진단 메모리/정식 S7/gen parent 승격과 **아직 연결되지 않았다**. 시장 신호 `values`를 신뢰 가능한 선행 생성기가 공급해야 하며 완전한 PIT 입력 공급 검증 및 이상국면 hysteresis가 없다. 1개 종목 공유자본, 동적 cash scaling과 내부상계는 샘플에서 시험. 다종목/실거래/OOS 승인 없음.

### C+D 최소 통합
- 교배된 자식 `StrategyIR`을 D 국면별 route의 실제 전략 중 하나로 투입하고, **40% risk donor**가 전체 공유자본 내에서 실제 체결금액(4000/10000 초기자본)을 제한하는 회귀 PASS.
- 샘플은 6~8개 개발봉으로 구성되고 직접적으로 실제 G452 연구 1508개 QQQ 봉을 사용한 실험은 이번 변경 범위에서 수행하지 않았다. 수익률 상승이나 전략 발견을 주장하지 않는다.

## 시험 증거 / 불변조건

- `tests/research/test_v3_composite_development.py`, `tests/research/test_v3_regime_portfolio.py`, 기존 `test_v3_crossover.py`, `test_v3_inherited_audit_warmup.py`, `test_v3_regime_router.py` 및 부모/P2/정책 회귀를 함께 **36 PASS**.
- 신규/수정 소스 5개 Mypy PASS, 해당 변경 전체 Ruff PASS, Git `diff --check` PASS.
- 기존 G453–G552에서 이전에 오류가 났던 실제 IR 서명 50개를 읽기 전용 원본 G452 데이터를 일시 복제해 다시 감사: **50/50 PASS**, `verify_v3_p0.py` 결과.
- 기준 원본 G452/452 final evidence `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`; 격리된 과거 G552/552 final evidence `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`. 두 SQLite `PRAGMA integrity_check=ok`; 데이터 원장 복구/덮어쓰기 안 함.
- Moon, OAuth issuer, dashboard fixed URLs, trading credential, 실거래 비활성, 봉인 OOS 불변; no Docker or paid model API call. `state/logs` 기존 untracked 파일은 건드리지 않음.
- 이전 전체 저장소 Mypy에는 미수정 파일 13개·기존 41개 타입 오류가 있었음. **이번 검증은 변경 소스 범위**이며 모든 테스트 통과·전체 repo Mypy clean/브로커 실행 가능으로 해석 금지.

## 다음 게이트

1. `VerifiedDonor`의 source_generation·evidence SHA·S7 report SHA를 immutable gateway/cycles SQLite와 read-only로 결합하여 독립 검증하는 trust boundary 구현; **각기 다른 real G68/G192/G248의 원본 진입·청산 컴포넌트 교배**를 G452 실제 1508 QQQ 봉에서 검증.
2. C+D의 signal/portfolio ledger를 **정식 AcademicMCPCheckpointService precommit/S2/S7/parent selection** 경로에 feature flag로 통합. 원본 DB는 불변으로 두고 새로운 격리 클론만 변경할 것. Risk max MDD30%, parent 대비 <=15pp, >=30 closed trades.
3. D 실제 국면 선택에 대한 **독립 decision/fill 감사와 full unlagged/lagged PIT** 검증, one-ticker shared NAV 적합성 평가; 다음 단계로 10-gen model-verified crossover/regime trials.
4. 진짜 GPT 세대별 plan·evidence-grounded diagnosis·수정·계승 영수증을 별도 검증. 고정 정책의 synthetic test나 deterministic cohort를 GPT 10세대라고 표기하지 말 것. V05→T4→V01~V04→V06→V07 승인 순서 유지.
