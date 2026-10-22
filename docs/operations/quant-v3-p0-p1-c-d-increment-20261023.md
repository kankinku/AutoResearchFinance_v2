# Quant AutoResearch V3 — 첫 구현 증거 기록 (2026-10-23 KST)

## 범위 및 상태
- 작업 범위: P0 S2 감사 오류 수정, P1 복수 부모 선택/위험 심사 실체결 2세대 검증, C typed 다중 부모 교배 최초 코어 및 D 시장 국면 신호 라우터 최초 코어.
- Q02/Q05/Q06/Q07/Q08/Q09/Q10/Q11/Q14/Q17/Q18/Q20 관련 종속 구현. **본래 승인 순서 V05 → T4 실제 모델 10/100 → V01~V04 PIT/OOS → V06 paper-only → V07 유지**.
- **코드 수준 완료는 실제 GPT 자율 연구 10/100 또는 투자 알고리즘 검증 완료가 아님.** 런타임의 결정론적 컨트롤러가 복제본에서 2세대 실행; 외부 GPT 모델 호출 0회.
- 기존 학술 G452/452·별도 연구 G552/552·기존 GPT 보조 G453 복제 원장, Moon/Quant OAuth/URL, 브로커, 주문 OFF, 봉인 OOS는 변경 없음.

## P0 — S2 감사기 WARMUP 판정 버그 수정 (실제 근본 원인)
- 대상: `research/indicator_engine/inherited_decision_audit.py`.
- 이전 로직은 `incomplete = any(feature_value is None for entry+exit+regime)`를 우선 처리해, 실행 가능한 OR 진입 신호가 이미 TRUE더라도 미완성 **청산** 특징값 하나 때문에 `WARMUP`을 출력했다. canonical 백테스터는 그런 신호를 실제로 다음날 시가에 체결 → `inherited fill has no valid close decision` 잘못 거부.
- 수정: 보유 중이면 원래 청산 판정 유지. 미보유이며 `gate_entry and gate_regime`이 TRUE면 `REQUEST_ENTRY`를 먼저 기록; 불완전한 다른 보조/청산 지표가 이를 무효화하지 못하게 함. 신호 부재의 WARMUP/필터 로직은 유지. **core/backtest 엔진과 기존 위험·비용 모델은 변경하지 않음**.
- Regression TDD: `tests/research/test_v3_inherited_audit_warmup.py`, 먼저 2개 실패, 수정 후 2개 PASS. 참조 features `fast=1.0`·`slow=None`인 OR 진입이 t0 TRUE가 되어 t1 시가 매수, 느린 청산 신호 준비 후 정상 청산하며 원장 Fill과 감사 Decision 1:1 일치.
- 실측 원장 기반 재현: `state/moon-http/quant-moon-bounded-100-20261023/verify_v3_p0.py` (ignored 상태, Git 미추적). 이전 100세대 연구의 **실제 감사 오류 기록 50개 signature 전부**를 동일 G452 부모 S7 IR·동일 원시 시장자료·동일 컨트롤러 ops로 재구성, 격리 SQLite 원장에서 백테스트/S2 재실행. **50/50 PASS**, 모든 체결 수 일치. 원본 G452는 변경 없음.
- 제한: 이는 관찰된 50건 오류 원인 해소를 증명하며 모든 미래 합성 전략과 위험 관리 경로의 S2 자동 지원을 증명하지는 않음. 특히 stop-loss·risk sizing을 가진 새로운 C/D 전략의 S2 감사는 여전히 범위 밖.

## P1 — 동적 복수 부모 선택/실행 2세대 실험
- 기존 `research/llm/parent_portfolio_v2.py`·`application/academic_checkpoint_service.py`의 opt-in `parent_portfolio_v2=True`, `child_risk_budget` 및 `precommit_child_risk_budget` (MDD ≤30%, 부모 대비 증가 ≤15%p, 완료 거래 ≥30), `p3_semantic_preflight=True`로 격리 실행.
- `state/moon-http/quant-moon-bounded-100-20261023/verify_v3_p1.py`가 G452/452 세 가지 SQLite 원본을 tempfile 복제하고 **G453~G454만 실제 원장에 기록**, S7 보고서 및 부모 증명해시를 재검증, 실행 끝나면 tempfile 정리.
- 측정 G453: **선택 부모 G68, +73.0338% / MDD27.9092% / 103 closed trades**.
- 측정 G454: **선택 부모 G192, +38.4386% / MDD23.0772% / 78 closed trades**.
- 상태 `454/454 COMPLETED`, 부모의 세대와 selection hash가 실제 `inherited_parent` 필드 및 counted S2/Fills/Evidence/S7 일치, SQLite source G452/452의 evidence head `e620bfec...` 보존. 실거래·OOS OFF.
- 중요: **복수 부모 2개를 순차적으로 사용**한 검증이다. 두 부모 성분을 하나의 자식에 동시 교배한 C 검증과 구분. 실험 제안/진단은 scripted deterministic controller, 실제 모델 독립 판단이 아니다. 두 세대 수익률은 별도 후보의 동일 개발 데이터 성과이며 상호 복리 연결이 아니다.

## C — 진입·청산·위험 유전자 실제 결합의 첫 구현
- 신규 `research/llm/composite_crossover_v3.py`: `VerifiedDonor`, `CompositeCandidate`, `compose(entry=…,exit=…,risk=…,regime=…)`, `mutate_composite(…,typed ResearchIntent)`.
- 다른 부모의 실제 `entry RuleSet / exit RuleSet / RiskConfig`를 복사한 새 정식 `StrategyIR` 생성. 부모 세대/원본 evidence SHA/S7 보고서 SHA/각 성분 hash 포함 `composite-genome-v3` lineage 및 합성 hash를 기록. 같은 alias 아래 정의가 다른 feature/indicator는 **fail closed**, strategy hash mismatch·replay_verified=False·동일 단일 부모만 제안된 경우 reject.
- 실제 canonical costed BacktestEngine regression: 서로 다른 risk donor의 50% position sizing → 매수 notional 감소; 다른 exit donor 규칙 → 매도 시점 변경; 체결/최종자산 차이 확인. `ResearchIntent` post-crossover AND/OR 변경 검증.
- **제한:** verified=True 플래그는 독립 검증 그 자체가 아니다. 호출자가 기존 부모 selection 및 저장된 evidence/replay를 대조한 뒤 이 객체를 생성해야 함. alias 이름 충돌 자동 리네임/충돌 해결, 실제 다중 부모 IR의 S2·S7·P2 counted checkpoint 통합, risk donor의 stop-loss/가변 sizing 감사 등은 아직 미구현. 새 합성 전략을 정식 세대에 커밋했다고 주장 금지.

## D — 시장 국면 라우팅 계약의 첫 구현
- 신규 `research/llm/regime_router_v3.py`: 타입 검증된 `RegimeRouteSpec`, `RegimeRouterSpec`, `resolve_regime_routes`(완료된 bar index).
- **exclusive** 첫 일치 국면, **weighted** 여러 일치 국면의 지정 가중치(합계 ≤100%), 국면 미일치/None→현금/진입 없음. route ID 중복, 불완전 signal, 유효하지 않은 시점, 이상 allocation 등 거부. 전환 정책 `hold_previous_until_exit`/ `flatten_on_switch`를 버전드 표현으로 준비.
- **제한:** 이 함수는 신호 선택기만 구현, 아직 실제 next-open 주문·상태별 청산/리밸런싱·전략별 포지션·공동 NAV·슬리피지 할당/계좌 장부 및 독립 S2 감사가 연결되지 않음. 완전한 D multi-strategy engine NOT IMPLEMENTED.

## 테스트·추적 가능성
- 신규 3개 테스트 파일 `test_v3_inherited_audit_warmup.py`, `test_v3_crossover.py`, `test_v3_regime_router.py`.
- 신규 코드와 해당 부모·core·governance 관련 **22 PASS**, 전체 Ruff PASS; 신규/변경 소스 범위 mypy PASS.
- 저장소 전체 mypy는 새 소스가 아닌 13개 기존 파일에서 **41 오류로 FAIL** (예: `research/llm/precommit_rejection_feedback.py`, `application/academic_checkpoint_service.py`, `scripts/`의 옛 미완성 annotation). 별도 기초 부채로 남기되 V3 새 파일 문제로 오기하지 않는다.
- 저장소 전체 `pytest -q`: 광범위 회귀 실행을 약 5분 수행, **624 passed, observed failures 0, KeyboardInterrupt로 INTERRUPTED** (exit code 2). **전체 스위트 완료 PASS 아님**. 후속 통합·배포 전 남은 전체 테스트를 별도 실행해야 한다.
- 프로그램 코드·테스트는 브랜치 `feat/quant-parent-portfolio-20261021` 작업트리. 원본 staged `docs/operations/autoresearch-master-progress.md` 및 `quant-moon-100-cohort-complete-g453-g552-20261023.md`는 작업 시작 전부터 남아 있었음. 타인 staging·무관 `state/logs/` 삭제/리셋 금지.

## 다음 개발 게이트
1. C composite compiler를 `AcademicMCPCheckpointService`가 검증한 donor DB에서만 받아들이도록 연결, parent-components hash와 실제 백테스터 fill 영향 기록. 복합 risk 정책에 대한 독립 S2 verifier, P2 통과 및 S7 ablation 후에만 **counted** 승격 가능.
2. D 국면별 독립 exit·risk·position 상태, switching/overlap/unknown 정책, 공유자본/거래비용의 단일 장부 및 next-open execution + S2 감사 연결. 시점 누출·자본 중복 배분·아비트리지 사전 차단.
3. 재검증 가능한 실제 GPT 모델 호출/계획·진단 영수증 기반 10→100세대 비교. 외부 모델 자동 과금/운영 MCP 교체 금지; 미승인 봉인 OOS 접근 금지.
4. V05 → T4 → V01~V04 → V06 → V07 승인 순서 유지. 연구 엔진 기능 검증, 모델 진화 효과, 독립 투자 수익성을 분리 판정.
