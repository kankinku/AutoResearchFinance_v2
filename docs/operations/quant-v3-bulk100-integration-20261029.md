# Quant V3 — +100개 연구 지표 출력 일괄 이식 결과 (2026-10-29)

Branch: research/v3-strategy-evolution. Q05/Q10/Q11/Q12/Q18, S6/S9/T1-02.

## 집계

- 이전 연구 등록: 335개. 신규 **100개 scalar 출력**. 등록 총 **435개**. 신규 분류: pandas-ta-classic MIT에서 **43개 추가 보조선·상하 밴드·신호선**, Bukosabino/ta MIT에서 **57개** 자체 계산 출력.
- **중요:** 100개는 서로 다른 numerically distinct scalar 시계열 출력이지, 반드시 100개 수학적으로 독립된 지표 종류가 아니다. 같은 지표의 상하단, 빠른/느린 신호선, 히스토그램은 개별 기능이지만 기초 수식은 공유한다.
- 정규화된 기존335 + 신규100의 480-bar 개발용 합성 시계열에서 기본값 출력이 서로 같은 신규 항목 **0개**. 다만 모든 데이터 국면에서 수학적 동치성을 증명한 것은 아니다.
- 선별 과정에서 124개 nonconstant causal distinct numeric 후보 중 단순 기간 변형 및 중복 우려 24개를 보류. 후보·제외 로그는 quant-v3-bulk100-source-screen-20261029.json에 보존.

## 원본 출처

1. pandas-ta-classic MIT, Git SHA 7c669b033582d53b70aa68b6388796d19ce33979. 기존 라이선스 및 vendor 원본 유지, 43개 secondary output column을 개별 research FeatureSpec으로 등록.
2. Bukosabino/ta MIT, Git SHA a890410710a6e483c9ba08da7f3dd5089e4b9dff. ta/ 디렉터리에 원본 Python 소스/라이선스/고정 pin 복제. 57개 whitelisted output names만 호출. 다른 외부 LGPL 소스 코드는 이식하지 않음.

## 핵심 실행 경로

- core/features/bulk100_manifest.json — 100개 원본 소스, output index, family, license, version pin.
- core/features/pandas_ta_manifest.json — 추가 43개 MIT secondary scalar.
- core/features/bulk100_ta.py — 새 소스의 허용된 57개 출력만 계산, 각 family 입력·컬럼 whitelist, 잘못된 파라미터 및 룩백 변경 거부. 동일 OHLCV일 때 원본 family의 계산 결과를 메모리 내 bounded cache로 재사용; 외부 거래/인터넷 API 없음.
- core/features/catalog.py 와 core/features/calculators.py — 전체 등록과 실제 StrategyIR inherited FeatureRef 연결.
- 57개 Bukosabino/ta 지표는 업스트림 source-default 기간(지표별 상이)을 **고정**한다. FeatureSpec의 lookback=1은 source_defaults_fixed 표식이며, 룩백을 임의 조절할 수 없다. GPT 탐색에는 기본형 입력으로 사용 가능하나 기간 최적화는 별도 이식 후 사용.
- 기존 pandas-ta rainbow 원본은 최소 200바가 있어야 계산을 시작하므로, 값이 거꾸로 초기 바에 나타나지 않도록 최소 history 200바가 확정되기 이전에는 None 처리한다. 새 rainbow secondary output과 기존 주 출력 모두 적용.

## 검사

- scripts/v3_validate_bulk100_cohort.py: 신규 100/100 verified, 0 rejected. 합성 480바, 각 feature의 finite nonconstant 값, 140/280/420/479 multi-prefix 인과성, 기존 335+신규 100 default-vector signature 중복 배제, inherited StrategyIR 값 일치. 결과 JSON은 docs/operations/quant-v3-bulk100-cohort-gate-20261029.json.
- scripts/v3_audit_435_features.py: **435개 등록 중 409개 OHLCV scalar 기본값 계산·StrategyIR replay 가능**, 26개는 외부 PIT 가격·금리·지수나 session/orderflow/profile 전문 입력 미연결, 기본 계산 실패 0. 결과 quant-v3-435-feature-usability-audit-20261029.json.
- scripts/v3_audit_435_edge_cases.py: 409개 대상으로 flat-price/zero-volume/missing bars 각 상황 계산 예외 0. 기본 출력 동치 22개 그룹(기존 cohort), 신규분은 동일 서명 없음. 결과 quant-v3-435-edge-duplicate-evaluation-20261029.json.
- 로컬 scoped pytest 및 Ruff/MyPy는 별도 실행. Moon 정식 release 도구의 uv 미설치 문제는 여전히 별도 게이트 블로커.
- 미검증: 원본 구현과 외부 수치 oracle 전 기간 일치, 실제 2026 sealed OOS, PIT 외부 series, 백테스트 경제성과 실거래 안전성, 임의 룩백 튜닝 성능.

## 변경 경계

기존 Quant/main/배포, OAuth/고정 MCP URL, G1~G150 원장·SHA·부모 계승, 독립 OOS 및 orders OFF 유지. 연구 공식 V05→T4→V01~V04→V06→V07 순서 그대로 보존. 후속 100개/배치도 source pin→중복 제거→prefix+StrategyIR→edge→tests→이력 Push 순서로 심사한다.
