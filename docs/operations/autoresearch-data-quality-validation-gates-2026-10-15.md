# Quant Autoresearch — 데이터 진단·전략 승인 사유 게이트 (2026-10-15)

## 결정

기존 데이터/전략 연구 계약을 변경하지 않고 **자료 관찰상의 이상과 독립 검증의 부재를 구별**한다. 이 단계에서 완전한 거래소 거래일 달력과 당시 공개된 가격 수정본을 독립 입수하지 못했으므로, 과거 결과에 대한 최종 투자 승인(PIT 또는 SEALED_OOS)을 할 수 없다. 현재 QQQ 2026년 고정 전략 3개 모두 **NOT_VALIDATED**다. Champion 승격도 없고 주문 허용도 없다.

## 변경 사항

- `research/indicator_engine/validation_gate.py` — 일일 미국 주식 자료에서 **주말 거래봉, 동일 종목·날짜의 중복 일봉, 연속 관측일 간 최대 날짜 간격**을 탐지한다. 이를 거래소 휴장일을 알고 있는 공식 캘린더로 오해하지 않도록 항상 `SESSION_CALENDAR_NOT_INDEPENDENTLY_VERIFIED`, `calendar_independently_verified=false`로 반환한다. 주말/중복이 없더라도 **실제 개장일 누락 여부는 알 수 없다**.
- `application/market_data_audit.py` — 기존 공급업체 비교, 파일 해시 고정, 원시/조정 가격 비율 검사와 함께 `exchange_session_observations` 및 `blocking_reasons` 항목을 반환한다. 별도 CSV/거래소 데이터를 조용히 만들어 넣지 않고, `independent_exchange_session_calendar_missing`을 항상 표기한다.
- `research/indicator_engine/forward_window.py` — 각 전략의 실제 성과를 재계산해 **누적수익 비양수, Sharpe 기준 미달, MDD 초과, 완료 거래 10건 미만, 검증 기간 252개 일봉 미만**, 자료 공급자 수정 이력/기업행동 품질, 거래일 이상, 독립 공개본/캘린더/OOS 승인 증거 부재의 개별 사유를 정렬·중복 제거해서 돌려준다. 해당 사유는 `evaluation_hash`에 포함되며 새 증거 스키마는 `academic-forward-window-v2`다. 이전 v1 증거는 변경하지 않는다.
- `validation_decision='NOT_VALIDATED'`, `independent_oos_approved=false`, `point_in_time_independently_verified=false`, `candidate_promotable=false`, `broker_executable=false` 고정. 외부 모델이 좋은 수익률을 보고 이 판정을 우회할 방법은 없다.

## 실제 보존 시세 검토

| 자료 | 일봉 | 주말 | 일자 중복 | 최대 일자 간격 |
|---|---:|---:|---:|---:|
| QQQ 2020–2025 raw | 1,508 | 0 | 0 | 4일 |
| QQQ 2026-01–09 raw | 187 | 0 | 0 | 4일 |
| SPY 2020–2025 raw | 1,508 | 0 | 0 | 4일 |

QQQ 2020–2025 raw와 adjusted 1,508봉에 적용한 기존 가격 조정 비율 검사 결과는 `PRICE_FACTORS_CONSISTENT`, 불일치 0건. **이 비율 검사는 배당금·분할일 또는 역사적 수정 이력의 독립 검증이 아니다.** 세 데이터 모두 `revisions_not_as_of`, `independent_historical_as_of_snapshots_missing`, `independent_exchange_session_calendar_missing`으로 승인 차단.

원본 2026년 QQQ 워밍업 구간 전략들의 수정 없는 재실행:

| 전략 | 누적수익 | 완료 거래 | 판정 |
|---|---:|---:|---|
| GPT G7 | +5.49% | 5 | NOT_VALIDATED |
| GPT G10 | +15.70% | 1 | NOT_VALIDATED |
| Random G10 | +5.88% | 8 | NOT_VALIDATED |

공통 차단 사유: 자료 수정본 `as_of` 검증 부재, 독립 역사적 가격 발표 증거 부재, 기업행동 검증 부재, 거래일 캘린더 독립 증거 부재, 봉인 OOS 승인 부재, 거래 수 10건 미만, 2026년 검증 구간 187봉(<252봉).

재검증 원본 경로: `docs/operations/evidence/quant-validation-20261015/chronological_validation_gate_results.json`. SHA256: `76d1428aa1bb53966986a9ad6ea1fd10d921296ec5860dbf59fd85587fac6863`.

## 보안·계약

- 모든 새 검사는 시장 데이터 확인과 연구 결과 상태 표시만 수행한다. 네트워크 시세를 임의로 수정하거나 덮어쓰지 않으며 브로커 주문 API는 호출하지 않는다.
- 기존 URL `https://project-moon.taild689f9.ts.net/quant/mcp`, OAuth 등록·키·연구 원장, 기존 MCP 도구 수를 유지한다.
- 개장일 공식 전체 목록이 없으므로 *모든 거래일을 확인했다*는 주장을 금지한다. `as_of`라는 공급자 자기 선언만으로 독립 PIT를 인증할 수도 없다.
- 향후 NYSE의 독립 거래 세션 목록과 기업행동·과거 수정본을 확보하면, 기존 관측 스캐너와 별도로 **출처·버전·기준 날짜가 증명 가능한 검증 입력**으로 연결해야 한다. 그 전에는 `NOT_VALIDATED` 유지.

## 테스트

- 관련 계약 검증: 날짜 중복 및 주말 탐지, 평일 장기 공백의 과잉 판정 방지, 가상의 우수한 전략도 PIT/OOS 자동 승인 불가, 실제 양호한 성과지만 표본 부족·품질 부족인 결과의 별도 차단 사유, 관리되는 Parquet의 주말/중복 관측 검출.
- Ruff, Mypy 및 전체 회귀 테스트는 배포 이전에 통과 확인한다.
