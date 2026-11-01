# Quant V3 Track1 — 오픈소스 기술지표·캔들 패턴 2차 확장 (2026-10-28 KST)

## 범위와 증거
- 기존 사용자 승인 요구 Q05/Q10/Q11/Q12/Q18, T1-02/S6/S9의 지표 구성요소 수집·추가 작업. 기존 전략 진화·부모 계보/해시·실험 원장·PIT/OOS 분리·실거래 비활성·Quant 고정 MCP URL/OAuth 유지.
- 작업: `research/v3-strategy-evolution` 개발 브랜치의 `core/features/catalog.py`, `core/features/calculators.py` 연결, 신규 `core/features/source_indicator_batch2.py`, 재현 가능한 유닛/StrategyIR 결합 테스트.
- 자료: Moon 격리 경로 `/shared/moon-workspace/_quant-indicator-sources/pandas-ta-classic` pin `7c669b033582d53b70aa68b6388796d19ce33979` (MIT), 이전 4개 전체 원본 pin 불변. 직접 소스 배포/원본 패키지 런타임 호출 대신 독립적인 scalar port를 작성. 원본 MIT 라이선스는 1차 작업에 이미 보관.
- **추가 신규 23개** (기술 15, 캔들 8) → 1·2차 누적 **41개**, 기존 173개 → 전체 연구 선택 목록 **214개**.

## 15개 신규 기술지표
| 분야 | 정식 Feature ID | 해당 소스 계산 계열 |
|---|---|---|
| 가격 이격 / 추세 | `bias_ratio`, `chande_forecast_oscillator` | BIAS, CFO |
| 이동평균 차이 / 상대차이 | `absolute_price_oscillator`, `percentage_price_oscillator` | APO, PPO |
| 추세·과열 | `psychological_line`, `kdj_j`, `pretty_good_oscillator` | PSL, KDJ(J), PGO |
| 매수·매도압력 | `brar_ar`, `brar_br` | BRAR(AR·BR 개별 출력) |
| 추세 전환 | `ttm_trend` | 이전 n개 종가 이전 완료 고저가 평균과 현재 종가 비교 |
| 변동성 및 가격 범위 | `acceleration_band_upper`, `thermometer` | ACCBANDS(U), Thermo |
| 거래량 / 수급 | `market_facilitation_index`, `williams_ad`, `price_volume_rank` | MARKETFI, WAD, PVR |

다중 출력 지표는 목적이 다른 출력만 별도 scalar Feature로 분리했다. 이름 정규화는 기존 registry 191종과 대조했으며 매매 신호 생성/평가에서 사용할 수 있는 `calculate_feature` 및 inherited `FeatureRef` 연결 경로를 통과한다.

## 8개 신규 캔들 패턴
`hanging_man`, `inverted_hammer`, `belt_hold`, `harami_cross`, `matching_low`, `high_wave`, `long_legged_doji`, `three_inside`.

모두 당일 완성된 바 및 과거 바에서 ±1/0 또는 warmup None 출력. **원본 TA-Lib 바디/그림자 동적 평균 임계치·전체 캔들 파라미터와 수치 동일성은 미검증**. 해당 단순화된 기하학 신호는 연구 탐색용 신규 feature이며 기존 원본 패턴을 구현했다고 과장하지 않는다. 허위 거래 실행이나 OOS 평가를 포함하지 않는다.

## 인벤토리 재생성
- 저장소 복제 4개 유지, 파일 기반 집계 711건, 정규화 후보명 442종.
- 이름 수준: 이미 이식된 출력의 소스 후보 그룹 40, 기존 이름/별칭 중복 검토 72, 미이식 **330개 후보 그룹**. 누적 신규 Feature 41개와 후보 그룹 40개의 차이는 BRAR처럼 소스 하나에서 2개 출력이 나오기 때문.
- 자동화된 JSON 출력: `docs/operations/quant-v3-opensource-indicator-candidates-batch2-20261028.json`. 앞선 배치 파일은 보존.
- 330개는 실제 이용 가능한 별도 수학적 기술지표 330종이 아니다. 수학 함수, TA-Lib 변형, 서로 다른 계산 파라미터, 외부 데이터 요청을 포함하므로 기능별/수식별 검증이 더 필요하다.

## 검증과 한계
- 신규 배치 지표·패턴 계산, 결측/flat, 현재바 뒤로 잘라도 같은 결과, 결정론, 독립 계산 기준값, FeatureRef 파이프라인 테스트 50 PASS.
- 전후 기존 선택 경로/1차 배치/범위 정책 포함 지정 총 85 PASS.
- Ruff 전체 PASS, 수정 모듈 mypy scoped PASS.
- 전체 단위 테스트·전체 mypy 릴리스 성공은 주장하지 않는다. 이전 배치의 전체 pytest는 개발 사본에 없는 런타임 상태 파일 때문에 수집 단계 실패했고 Moon 강제 릴리스 체크는 uv 부재로 실패했다.
- 유의성, 비용 반영 알파, 미사용 2026 OOS, 기존 운영 서비스의 핫리로드, Model 자율연구 세대는 이번 이식에서 실행하거나 확인하지 않았다.
- 필요하다면 다음은 동일 라이선스 출처의 추가 패턴 10~20개(패턴 경계 테스트 강화 포함) 및 다른 출처 BSD/Apache 공식의 **수식 검증된 신규 유형** 순서. 기존 승인된 V05→T4→V01–V04→V06→V07 전체 계획 유지.
