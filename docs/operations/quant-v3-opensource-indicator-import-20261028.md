# Quant V3 Track1 — 4개 오픈소스 지표 복제·중복 후보 대조·첫 이식 (2026-10-28)

## 범위와 격리
- 승인 Q05/Q10/Q11/Q12/Q18, Track1의 T1-02/S6/S9 연구지표 구성요소 확장. 원본 20문답과 V05→T4→V01–V04→V06→V07 단계 순서 불변.
- 코드 변경은 `research/v3-strategy-evolution` 브랜치의 `core/features` 및 테스트/문서/인벤토리 생성 스크립트에 한정. `main`, 실제 운영 checkout, Research Evidence/SQLite, sealed OOS, Quant MCP URL, OAuth, 주문 권한을 수정하지 않음.
- 클론 위치: `/shared/moon-workspace/_quant-indicator-sources/`. Git 추적 대상이 아닌 독립 스냅샷. **외부 소스는 실행하거나 무조건 포함하지 않고 수학식을 별도 구현·테스트**.

## 원본 4개 pinned SHA / 라이선스

| 소스 | SHA | 검출 항목 수 | 라이선스 |
|---|---|---:|---|
| [pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic) | `7c669b033582d53b70aa68b6388796d19ce33979` | 284 | MIT |
| [TA-Lib](https://github.com/TA-Lib/ta-lib) | `4334163d3a1f5019aa9051342316b936a4dfb994` | 238 | BSD-3-Clause |
| [Tulip Indicators](https://github.com/TulipCharts/tulipindicators) | `be18abb13e075ba866898dcc7cb52399603302a6` | 104 | LGPL-3.0 |
| [Stock Indicators](https://github.com/DaveSkender/Stock.Indicators) | `da428182d0e222339b662bc8ac645596102260bd` | 85 | Apache-2.0 |

파일명/디렉터리 기반 인벤토리 총 711건 → 정규화된 후보 이름 442개. **기존 이름/별칭 충돌 검토 72개, 이식한 18개, 아직 이식하지 않은 이름 후보 352개.** 출력 파일 `quant-v3-opensource-indicator-candidates-20261028.json`은 각 소스 원본 이름, 정규화 후보, 소스, 충돌상태를 포함. TA-Lib 인벤토리에는 수학 유틸리티 등이 포함돼 있으므로 238을 단독 지표 개수라고 주장하지 않음.

**중복 정책:** 출처 간 동일 함수명/공인 약칭/기존 별칭만 합치고, 출력 변형·매개변수·평활 방식이 다른 지표는 수학적 동일성이 검증되기 전까지 별개의 미결 후보로 남김. 따라서 이름 중복 제거와 실제 계산 수식의 의미적 중복 제거를 구분한다. 352개는 실제 신규 지표 확정 수가 아니다. LGPL 소스의 직접 이식·결합은 별도 배포 준수 확인 전 보류한다.

## 이번에 실제 등록·계산하는 신규 18개

| 범주 | 18개 계산기 |
|---|---|
| 추세/모멘텀/변동성(10) | `choppiness_index`, `squeeze_on`, `chandelier_exit_long`, `awesome_oscillator`, `kst`, `coppock_curve`, `efficiency_ratio`, `vertical_horizontal_filter`, `correlation_trend_indicator`, `balance_of_power` |
| 캔들패턴(8) | `harami`, `piercing_pattern`, `dark_cloud_cover`, `three_white_soldiers`, `three_black_crows`, `spinning_top`, `dragonfly_doji`, `gravestone_doji` |

- `pandas-ta-classic` MIT 공식과 패턴 명세를 참조하여 별도 구현. 코드는 `core/features/source_indicator_ports.py`; 출처·커밋·라이선스를 `FeatureSpec`에 기록. MIT 원문 `quant-v3-pandas-ta-classic-MIT-LICENSE.txt` 동봉.
- `core.features.calculators.calculate_feature`의 화이트리스트 분기로 연결. 기존 173종은 유지하고 등록 총수는 191종(개발 소스 카탈로그 177 + 선택적 외부 시계열 14); G1–150 연구 결과 불변.
- 파생값은 입력 길이만큼 출력, warm-up 시 `None`, 현재와 과거 바만 사용. inherited StrategyIR의 `FeatureRef`·`_new_feature_vector` 경로에서 실험 전략이 참조 가능. 현재 바의 최종 정보로 당일 거래하지 않고 기존 next-bar 결정을 유지.
- 캔들 패턴은 ±1/0의 단순화된 캔들 기하학 버전. 원본 TA-Lib 62개 패턴의 threshold/평균바디 설정 및 교차 라이브러리 출력과 완전 동일함을 주장하지 않음. 경제적 유의성·실거래 적합성·2026 OOS 검증은 하지 않음.
- 현재 패밀리별 성능, 다른 계산 버전 대비 수치 일치, 범용 임의 조합의 성능은 후속 테스트가 필요. **현재 첫 배치 구현은 전체 442개 이식 완료가 아님**.

## 검증 기록
- 새 단위/중복·causality/edge 및 inherited StrategyIR 연결: **16 PASS**.
- 기존 카탈로그/기능 테스트를 함께 포함한 지정 범위: **31 PASS**.
- 지정 파일 Ruff: PASS.
- 생성 카탈로그의 정확한 버전 pinned, 4개 소스가 존재하지 않으면 생성 스크립트가 오류를 반환.
- 전체 릴리스 테스트/독립 OOS/수익성 재연구: **별도 상태 기록**. 신규 18개를 무증거로 Champion에 등록하거나 기존 진화 부모를 교체하지 않음.

## 다음 작업
1. 수식/출력 표준화: 기존 지표와 72개 충돌 후보의 수학식·lookback·출력 차이를 직접 대조, 중복/동의어/다른 변형 세 가지로 분류.
2. MIT·BSD·Apache 소스의 신규 후보 중 유효한 계산기를 10~20개씩 테스트 우선 이식. 갭, 결측치, 보간/누수, 랙, 종가 시점 검사.
3. 이름만 등록되고 실제 계산 불가능한 기존 지표도 실행 가능 어댑터로 검증; S7 진화 연구는 원본 부모 계보·해시와 통제된 비교를 유지.
4. 독립 데이터 확보 및 외부 검증 이전에는 성능 우월성·PIT·실거래 승인 주장 금지.
