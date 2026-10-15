# Quant Autoresearch — NYSE 공식 휴장 공지 기반 거래일 완전성 점검 (2026-10-15)

## 판정

**보유 중인 QQQ·SPY 네 데이터셋의 2020~2026년 일봉 날짜가 NYSE/ICE가 발표한 휴장 일정과 일치한다.** 차이를 발생시키는 결측 거래일 및 휴장일 유사 봉은 발견되지 않았다. 이는 *공식 발표 일정에 근거한 거래일 완전성 검증*에 한정된다. 주가의 과거 공개 시점(as-of/PIT), 시세 수정 기록, 배당·분할의 독립적 정확성, 시장수익 전략의 진짜 독립 OOS 성과는 **검증되지 않았다**.

현재 Champion 0, 주문 비활성, 개발용 전략 결과 NOT_VALIDATED.

## 공식 출처 및 규칙

NYSE/ICE의 아래 네 가지 날짜가 명시된 공적 공지의 **전일 휴장일 표**를 교차 대조하고, 일정에 존재하는 평일을 일반 세션으로 구분했다. 예정된 조기 폐장일은 실제 개장일이므로 일봉 누락으로 취급하지 않는다.

1. 2019-12-09 발표, NYSE 2020~2022: https://ir.theice.com/press/news-details/2019/NYSE-Group-Announces-2020-2021-and-2022-Holiday-and-Early-Closings-Calendar/default.aspx
2. 2021-12-27 발표, NYSE 2022~2024: https://ir.theice.com/press/news-details/2021/NYSE-Group-Announces-2022-2023-and-2024-Holiday-and-Early-Closings-Calendar/default.aspx
3. 2023-11-10 발표, NYSE 2024~2026: https://ir.theice.com/press/news-details/2023/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar/default.aspx
4. 2024-12-30 **추가 특별휴장**(지미 카터 전 대통령 국가애도일 2025-01-09): https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx

**시기별 예외:** 2021년 6월 18일은 NYSE 일반 개장일이다(당시 Juneteenth NYSE 휴장 전). 2022년 6월 20일은 Juneteenth 대체 휴장일, 2022년 1월 3일은 1월 1일이 토요일이었으므로 NYSE 규정상 일반 개장일이다. 2025년 1월 9일은 위 별도 공식 공지에 의한 특별휴장일. 2026년 7월 3일은 독립기념일 대체 휴장일이다.

검증 범위는 UTC 자정으로 표시된 미국 주식/ETF 1일봉, 한 심볼, **2020-01-01~2026-12-31** 내 공표된 NYSE Group 현물 주식 일정이다. QQQ는 Nasdaq 상장 ETF이므로 NYSE 공휴일 일정 일치만으로 Nasdaq의 모든 개별 시장운영 이벤트까지 검증한 것은 아니다. 시세에 개별적으로 기록된 종가·거래량을 공식 NYSE와 대조하는 검사도 아니다.

NYSE 공식 공지에서 사람이 전사한 JSON을 로컬의 버전 고정 참고자료로 저장했으므로, 스캔 중 제3자 API를 호출하지 않는다. 참고자료 SHA-256이 소스에 고정된 값과 다르면 **검증 실패(조용히 무효화하지 않음)**. 출처 URL은 감사 시 확인 가능한 추적 정보이고, 공급자가 서명한 원본 데이터나 일별 거래소 시세 기록은 아니다.

- 참고자료: `research/indicator_engine/nyse_public_closures_2020_2026_v1.json`
- SHA-256: `1a43f51dd026d0ca46ec48c3752d8fe58996d1e8972ae542f28007ae8d2a8f9a`
- 검사기: `research/indicator_engine/nyse_public_calendar.py`
- 사용처: `application/market_data_audit.py`의 기존 관리형 데이터 검사, `research/indicator_engine/validation_gate.py`의 보수적 승인 차단 사유. 기존 MCP URL/툴 스키마/세션 DB, OAuth, 주문 코드 변경 없음.

## 기존 시세 실제 검증

| 자료 | 공식 발표일 기준 예상 세션 | 확인된 일봉 | 결측 거래일 | 비정상 휴장일 기록 |
|---|---:|---:|---:|---:|
| QQQ 2020-01-02~2025-12-31 원시 | 1,508 | 1,508 | 0 | 0 |
| QQQ 2020-01-02~2025-12-31 조정 | 1,508 | 1,508 | 0 | 0 |
| QQQ 2026-01-02~2026-09-30 원시 | 187 | 187 | 0 | 0 |
| SPY 2020-01-02~2025-12-31 원시 | 1,508 | 1,508 | 0 | 0 |

네 시세 파일은 모두 `MATCHED_PINNED_NYSE_PUBLIC_SCHEDULE`이고, 실제 파일명의 **요청 시작·종료일** 내 기대한 모든 개장일을 포함한다. 이는 데이터 내 첫 관측일부터만 계산할 경우 놓칠 수 있는 기간 양끝의 누락도 탐지한다.

그러나 모든 데이터가 `revisions_not_as_of` 상태로 유지되고, 원시 시세는 `corporate_action_adjustment_unverified` 사유도 유지된다. 조정 가격도 **독립적 기업행동 내역 및 시점별 수정 기록의 검증 완료가 아니다**. `independent_historical_as_of_snapshots_missing` 사유는 언제나 남는다.

감사 증거 파일: `docs/operations/evidence/quant-validation-20261015/official_nyse_calendar_evidence.json`

- SHA-256: `a1872466dc1611b38d5d1057299c1cc81c758206a85d7d81c8f53437a0a31c33`
- 회귀 테스트는 공식 공지에서 추출한 특별휴장·Juneteenth·새해 예외, 거래일 누락과 휴장일 잘못된 가격, 비교 구간 초과, 자료 변조, 0 매매 권한을 검증한다.

## 의미와 잔여 리스크

과거에 사용하던 **주말/중복/8일 초과 관측 간격** 검사는 명시적 NYSE 휴장일을 모르기 때문에 평일 개장일 누락 여부를 놓칠 수 있었다. 이번 변경은 고정된 공식 일정의 전일 휴장·특별휴장 자료를 대조해 그런 허점을 보완한다.

공식 공휴일 발표를 기초로 계산한 예상 거래 세션 목록은, 거래소가 사후 제공한 **매 일자별 체결/호가 또는 비상 휴장 전체 감사 원장**과는 다르다. 따라서 참고자료의 출처가 공적인 것은 사실이지만, 모든 임시 정지나 공개되지 않은 일정 변경까지 독립 인증한 것은 아니다. 기준표가 누락된 특별 공지를 놓치면 그 날짜는 결측으로 잘못 탐지될 수도 있으므로 기록·해시·버전을 유지해야 한다.

실제 투자 검증의 필수 잔여 단계: 독립 시점별 시세/기업행동 기록 확보 및 출처 공개 시점 검증 → 충분한 미사용 기간/시장과 거래 건수에서 비용/벤치마크 보수적으로 평가 → 명시적 OOS 승인 이전 `NOT_VALIDATED`와 Champion 승격 차단 유지.
