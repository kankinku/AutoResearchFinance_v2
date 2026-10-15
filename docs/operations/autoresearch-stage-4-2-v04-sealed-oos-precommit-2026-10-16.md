# Quant Autoresearch V04 / 4-2 — 개발 전략 동결 및 봉인 OOS 접근 차단

점검: 2026-10-15 UTC / 2026-10-16 KST. 코드 브랜치 `feat/v04-sealed-oos-selection-precommit-20261016`, Push된 기능 커밋 `25dc483`. 운영 MCP 고정 런타임 `da2331d` 불변, URL/OAuth/32개 도구/연구원장/실주문 비활성도 불변.

## 이번에 실제 수행한 것

- 기존 `core/validation/walk_forward.py`·학술 `forward_window.py`는 개발 데이터로 검증할 수 있으나 선발 전략을 OOS 개봉 **전에** 동결했다는 독립 기록이 없다. V04에서는 증거 수집/접근 권한이 충분하지 않아 진짜 SEALED_OOS 시장자료를 열거나 실제 수익률을 평가하는 대신 선발 가설 기록 절차를 구현했다.
- 신규 `research/indicator_engine/sealed_oos_precommit.py`: `AlgorithmPlan` 검증·학술 지표 정의 해시·학술 typed StrategyIR 해시·SignalReplay·훈련 데이터 및 공급자 lineage SHA를 **DEVELOPMENT 데이터에 한해서** deterministic receipt로 만든다. 단일 study용 JSON 파일은 atomic exclusive create와 기존 파일 거부로 덮어쓰지 않고 보존. verify 시 현재 계획·시장·지표 정의를 다시 컴파일해 바이트/내용 일치를 확인한다.
- 새로운 CLI `freeze-development-selection`와 `verify-development-freeze`는 개발 Parquet·typed JSON plan·catalog·receipt 파일만 받으며 봉인 OOS 파일/결과 경로를 입력으로 받거나 사용하지 않는다. `DataZone.SEALED_OOS`·`VALIDATION` 자료를 선언/오염된 개발 입력으로 제공하면 거부.
- 출력엔 `oos_access_performed=false`, `independent_custodian_signature_verified=false`, `historical_pit_verified=false`, `sealed_oos_approved=false`, `candidate_promotable=false`, `broker_executable=false` 고정. 미래 OOS 성과·수익률·승률·α를 만들지 않음.
- **제한:** 로컬 exclusive 파일 + SHA 해시는 제삼자가 서명한 신뢰 타임스탬프나 변경 불가능한 WORM 저장소가 아니다. 별개 프로세스가 봉인 파일을 열지 못하도록 OS/클라우드 ACL 전체를 강제하지 못한다. 실제 독립 감사용 lock이 아니라 준비 기능이고 외부 보관자 서명·시간 인증·분리된 계정이 별도 필요하다.

## 실제 테스트

- `tests/research/test_sealed_oos_precommit_v04.py` 신규 **9 PASS**: 동일 study 두 번째 후보 덮어쓰기 거부, 훈련 바/선택 계획 변경 후 re-verify 차단, 증거 상태/OOS 승인 플래그 변조 거부, sealed/validation 데이터 입력 거부, symlink/invalid ID 차단, 정상 CLI freeze/verify와 typed source 검증.
- 학술 typed AlgorithmPlan·walkforward/chronological warmup, D06 multi ETF, MCP session/public contract 포함 합계 **91 PASS**; 변경 파일 Ruff/Mypy PASS; Git diff --check PASS.
- 실제 사용자 연구 결과에서 어떤 후보가 *외부 PIT 자격까지 갖춰 선발됐는지* 알 수 없다. 따라서 **실제 QQQ 가격 데이터로 진짜 후보를 freeze하거나 임의의 '승자 전략'을 만드는 일을 하지 않았다.** 테스트는 통제된 개발 fixture로만 수행. 실제 OOS 원본 미개봉, 승률/수익률 보고 없음.
- 운영 이전 V01 원본 3본은 모두 UTC 하루에 수집, V02 독립 공급자 원본 공개시각 0건, V03 과거 배당 공지시각/분할 기록 불충분. V04 진짜 출고/봉인 OOS 평가 `BLOCKED_INDEPENDENT_PIT_OOS`. 상태 JSON `docs/operations/evidence/quant-validation-20261016/v04-sealed-oos-access-not-performed.json`에 V01~V03 SHA-256 근거와 사전조건을 기록.

## 다음 단계 / 향후 수락 조건

- V05(4-3): 개발 입력에서 수수료·슬리피지·거래 가능 용량, 유동성·여러 가설 탐색에 따른 우연을 검증하는 비용/통계 테스트. OOS/PIT 기반 수익 확인은 보류.
- V01~V03 입력의 독립 PIT·기간/시점 증빙, 별도 독립 custodian의 전략 사전 등록/서명·OS 접근 권한을 확보한 후에만 실제 OOS 접근 범위를 엄격히 승인하고 개봉/평가. 같은 모델이 반복 최적화한 OOS를 독립 OOS라고 주장하지 않는다.
- 금지 상태: `historical_pit_verified=false`, `independent_oos_approved=false`, `broker_executable=false`. 기존 MCP 운영/계정/주문/신규 API 모델 호출 없음.
