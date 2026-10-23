# Quant AutoResearch T4 — P0 신규 지표 replay 컴파일러 / P1 typed 변경 모드 1차 수정

> 날짜: 2026-10-24 KST. 범위: 앞서 **미달**로 평가한 기능만. 원래 G452/G552 연구 원장, 현 GPT 5/100, OAuth/고정 URL/대시보드, 시장 데이터, 비용·S2/S7 코어는 변경 대상이 아니다.

## 발견된 결함과 해결 구조

1. 계승 연구 `_stage_inherited_plan`은 GPT의 새 `feature_selections`를 StrategyIR에만 등록하고, `dataclasses.replace(parent, strategy=child)`로 기존 벡터와 replay를 재사용했다. 신규 normalized_atr_percent 별칭 `natr_pct_20`이 실제 계산되지 않아 G6는 `KeyError` 이후 보수적인 `INHERITED_FEATURE_BINDING_MISSING`으로 거절됐다.
2. 동일 재사용 가정은 `_materialize_inherited`, `_inherited_from_evidence`, `compare_inherited_experiments`, counted S7 child/replay, P0-3B core `advance_inherited`에도 있었다. S2만 계산하도록 고쳐도 세대 커밋 시 `inherited parent source signal replay mismatch`가 발생함을 **복제된 운영 G6**로 재현했다.
3. 두 계승 경로는 `ResearchIntent.mode != 'structure'`를 차단하여, 이미 선언된 `parameter` 및 `mixed` GPT 변경 모드를 사용할 수 없었다. 경제적으로 달라진 포지션 비중도 신호 해시만 보면 같은 전략으로 간주할 수 있었다.

## 실제 구현

- **신규** `research/llm/inherited_feature_compiler.py`: `bind_inherited_features(parent, child, market)`. 기존 지표는 증거에 서명된 벡터를 보존하고, 새로 등록되었거나 참조가 변경된 지표만 `research_feature_specs` → `calculate_feature`로 계산해 전체 replay 신호와 시점, 다음 캔들 실행일정, hash를 재구성한다. 개발용 미국 주식 1일봉·단일 종목·등록된 scalar·동일 자산 OHLCV 데이터로 범위 제한. 검증 없는 신규 제안/타임프레임/교차 시장·상용 라이선스 지표는 차단. `lag_bars`는 과거 방향으로만 적용, 결측 및 워밍업 값은 보존. 새 vector/replay/provenance 정체성은 hash로 증명된다.
- **수정** `application/academic_checkpoint_service.py`: inherited 계획 사전 검사, 재시작 및 커밋 materialization, 추후 원장 읽기 검증, P2 risk precommit이 동일 rebind를 사용.
- **수정** `research/indicator_engine/inherited_experiments.py`와 `research/llm/lineage_selection.py`: 후속 S7 자식과 정식 counted 부모·계보 재생도 동일 rebind 계약 적용.
- **수정** `research/llm/autonomous_cycle.py`: 기존 AlgorithmPlan과 같은 feature vectors/replay **바이트 동일성**을 강제하던 구제약을, `base + parent StrategyIR`에서 복원한 feature vectors, parent+child 재계산 replay/provenance 및 보호된 canonical S2 비용·체결 감사를 검증하도록 변경. 임의 모델 제공 벡터 신뢰/검증 우회 금지.
- **수정** `research/llm/inherited_execution_identity.py`: 포지션 사이즈가 기본 100%이면 종전의 동일 세대 해시 규칙 유지. 기본값과 다른 현금 비중일 때에만 실행 정체성에 크기를 포함해, 실제 비용·수량이 달라진 파라미터 변경을 신호가 같다는 이유로 거부하지 않도록 함.
- **허용** `structure/parameter/mixed` 모두 등록 타입·Risk/S2/S7·중복 방지·동일 토큰 보호를 거친다. 이것은 임의 Python 실행이나 모든 위험 모드 허용이 아니다. 기존 `stop_loss_pct`, `take_profit_pct` 등 지원하지 않는 실행 정책은 현행 audit에서 계속 거부.

## 진짜 G6 데이터 사본 기반 종단 검증 (운영 원장 변화 없음)

원본 세션 `14626d55fb2b461faa485df911920071`의 **복제 SQLite**에서 G6 `feature_selections: normalized_atr_percent` + 기존 trend/sma 신호 + 신규 ATR 20일 0.035 미만 필터를 `require_execution_change=true`로 제출:

- 신규 registered feature 포함 **S2 진단 체크포인트 진입 성공**. 비용 반영 S2 누적 +80.9519%, MDD 19.5497%, 71 closed trades, 63.9920% 노출. 단지 기능 검증이며 2020~2025 비PIT 개발 데이터로 독립 통계적 개선 아님.
- 같은 **복제본**에서 실제 체결 ID에 근거한 유효 `DiagnosticResponse`로, 새 ATR 필터 하나만 제거하는 **S7 대조**를 제출: 복제본 G6 커밋, hash `6917111bea2ce18bc9d5439eca425061a1ddc7fb07db71cbf1b845199fd1d6f8`; 동일 비용 S7 원래 최종 $18,095.19 vs ATR 필터 제거 후보 $18,435.32; fills 143 vs 147. 최종 같은 복제본에서 `completed=6, checkpoint=AWAITING_PLAN`, **G7 계승 문맥 재구성 성공**. 실 세대 G6 완료로 계수 금지. 시장 수익성/독립 검증 성공 주장 금지.
- 별도 복제본으로 `mode=parameter` + 75% 현금 비중 변경, `mode=mixed` + 비중/규칙 변경 모두 S2 진단 단계 진입 성공(각 +60.5042% 개발 수익률). 거절 위험조건 완화 없고 실거래 OFF.

## 회귀와 남은 작업

- 신규 단위·계승 회귀: 등록 ATR 실제 계산, lag/prefix 미래 데이터 유출 점검, 새 replay 증거·실제 S2 비용 감사, 기존 replay 무변경, 위조·미등록 지표 거부, 75% 사이징의 경제적 신호 해시·체결 차이.
- 확대 기존 계승·P3·MCP 시험에서 외부 과거 G33 감사 스냅샷 `.../phase1-20261017-1950/snapshot-manifest.json`이 현재 Moon 컨테이너에 존재하지 않아 테스트 1건 `FileNotFoundError`가 발생. 이것은 현재 패치 기능 실패가 아니며 **허위 스냅샷을 만들어 통과시키지 않음**. 환경 의존 건을 제외한 동일 테스트와 Ruff·Mypy 검증 결과는 작업 기록에 별도로 남긴다.
- P2: `parent_portfolio_v2`의 counted 원본과 S7 자식 비교는 이미 구현됐지만 **기본 False**. 먼저 G2(+91.12%) 대비 기존 G1 S7(+84.35%)의 실제 risk-aware replay 결과를 **복제본에서 검증한 뒤** 활성화할 것.
- P3: `AcademicCheckpointAutopilot`은 존재하지만 ChatGPT MCP OAuth가 서버로부터 모델 역호출 권한을 주지 않음. 대화 지휘 방식으로 GPT plan/diagnosis는 가능하나 **무인 100세대는 미완료**. 별도 모델 호출은 명시적 비용·승인 전 금지.
- 운영 중 실 GPT 세션은 **5/100 AWAITING_PLAN G6 그대로**, 기존 G452/G552 연구 계보는 그대로. 실제 서버의 새 코드 배포 및 G6 정식 실행은 후속 독립 검증 게이트로 남김.
