# Quant Autoresearch — [1-2 / 전체 5단계] 공급자 데이터 범위·견적·수정 이력 검증 (2026-10-15)

## 공급자 선정

2020-01-02~2025-12-31 QQQ 시점별 원본을 검증할 우선 기술 검토 후보는 Databento XNAS.ITCH / QQQ / trades, 비교 보완 후보는 LSEG Tick History / PCAP이다. 모두 실제 원본 수령·서비스 계약·PIT 인증 전이며, 선택만으로 승인된 것이 아니다.

| 구분 | 확인된 공식 설명 | 실제 도입 전 확인 |
|---|---|---|
| Databento QQQ XNAS.ITCH | QQQ 상품 페이지에 2018-05-01 UTC부터 상품 데이터, 나스닥 거래소 직접 캡처, ts_recv(수신시각), ts_event(이벤트시각) | Nasdaq 외 거래소는 포함하지 않는 원본 데이터라는 한계, 실제 계정/스키마/기간별 이용권 |
| Databento historical 메타데이터 | metadata.get_dataset_range (계정별 스키마·기간), metadata.get_cost (USD 예상 비용), metadata.get_dataset_condition (서비스 수정일·가용성) | 실제 본인 계정의 QQQ 2020~2025 사용 비용, 권리·데이터 품질 |
| Databento 2026 수정 공지 | 2026-09-30 공지에서 2026-10-31 XNAS.ITCH 전체 과거 데이터 소급 업데이트(2023년 이전 instrument ID, EST 시간외 누락 복구, 자정 스냅샷) 발표 | 업데이트 전후 버전·증거 보존, 수정으로 영향을 받는 거래일/신호 재검증 |
| Databento EQUS.SUMMARY | 별도 데이터셋의 일봉 최종 요약은 20:15 ET 발표에 기반. 임시 통계는 16:15, 17:00 ET 발표됨 | 단순 16:00 ET 장 종료를 모든 데이터 이용 시각으로 인정할 수 없음. XNAS.ITCH의 타임스탬프와 혼동 금지 |
| LSEG Tick History / PCAP | 30년 이상 tick archive 및 GPS 동기식 nanosecond PCAP 옵션 설명 | QQQ 2020~2025 실제 venue/기간·타임스탬프·정정 원본·비용·계약 견적 미확보 |

공식 근거:
- https://databento.com/catalog/us-equities/XNAS.ITCH/etf/QQQ
- https://databento.com/docs/api-reference-historical
- https://databento.com/docs/venues-and-datasets/equs-summary
- https://databento.com/blog/nasdaq-historical-data-changes-2026-09
- https://databento.com/pricing/
- https://www.lseg.com/en/data-analytics/market-data/data-feeds/tick-history

## 추가 구현한 계정 인식 사전검사

새 연구 전용 research/indicator_engine/databento_metadata_preflight.py 와 CLI probe-databento-qqq-metadata는 XNAS.ITCH/QQQ/trades 기간을 2020-01-02T00:00Z부터 2026-01-01T00:00Z(exclusive)까지 고정한다.

인증정보가 명시적으로 제공된 경우에만 세 개의 읽기 전용 메타데이터 GET를 실행한다. 호출 가능 endpoint는 metadata.get_dataset_range, metadata.get_cost, metadata.get_dataset_condition이며, 대량/유료 시세 다운로드·batch job·구독·거래 주문 API 호출은 전혀 없다. 모든 데이터는 응답만 보고, 인증정보와 에러 본문을 화면, Git, 원장에 저장하지 않는다.

기간 미달, 권한 거부, 가격 비정상, 불량 provider condition, 네트워크 실패는 모두 해당 사유로 차단. 메타데이터의 마지막 수정일이나 가격 견적은 실제 원본 historical PIT 서명·발표 시각 증빙과 별개이며 true로 승격될 수 없다. XNAS.ITCH는 Nasdaq venue만 설명하며 미국 통합 가격의 독립 인증은 아니다.

2026-10-15 실제 Moon 실행 결과:

    status: AUTH_REQUIRED
    schema_coverage_verified: false
    quoted_cost_usd: null
    condition_records_inspected: 0
    licensing_verified: false
    publisher_release_authentication_verified: false
    historical_pit_verified: false
    broker_executable: false

Databento API 키가 현재 연결된 개발 실행 환경에 없으므로 API 비용 견적은 아직 조회하지 못했다. 테스트 예시의 가짜 USD 값은 실거래 견적이 아니며, 공개 $199/월 같은 일반 요금도 이 데이터 요청의 실제 비용으로 취급하지 않는다.

읽기 전용 명령:

    .venv/bin/python -m research.indicator_engine.cli probe-databento-qqq-metadata

## 남은 1-2단계 수락 기준

1. 공급자 계정으로 실제 스키마별 이용 가능 범위와 get_cost를 확인하고, 회사 라이선스/상업적 이용 조건을 검증한다.
2. LSEG에 QQQ 동일 범위의 주문/거래 이벤트 시각, 원본 캡처, 역사적 수정 이력, 가격 및 최소 계약 조건을 확인한다.
3. Databento에서 2026-10-31 소급 변경 **전후** 수신/이벤트 필드·instrument_id를 버전별 고정하며 지표 결과 변화 감사. preview를 운영 baseline으로 소급 덮어쓰지 않음.
4. 실제 거래 판단별 필요한 원본 발표·수신·정정 기록을 재구성, 외부 검증 가능한 신뢰 체계를 확인. 별도 기업행동·OOS·거래비용 평가 전까지 순수익/실거래 인증 불가.

기존 Moon MCP URL/OAuth/보존된 원본·sealed OOS/실거래 비활성 상태 변경 없음. 2026-10-16 한국 시간 저녁 QQQ 원본 추가 수집 예약을 유지했으며 새 코드는 운영 배포하지 않았다.
