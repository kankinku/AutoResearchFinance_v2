# Quant Autoresearch — [1-2/5] Databento 공급자 상태 범위 검증 강화 (2026-10-15)

## 실질적 오류 수정

기존 Databento historical metadata.get_dataset_condition 2020-01-02~2025-12-31 응답에서는 2일치 available 데이터만 받아도 전체 기간이 정상인 것처럼 METADATA_QUOTED_NOT_PIT으로 판정하는 false green 가능성이 있었다.

개선 기능은 기존 SHA-256 pinned NYSE 공개 휴장일 자료(2025-01-09 특별 휴장 포함)를 사용하여 전체 1,508개 정규 거래일 상태가 있는지 검사한다.

- DATASET_CONDITION_INCOMPLETE: 2일 응답 시 1,506 정규 거래일 누락을 별도 카운트
- DATASET_CONDITION_CONFLICT: 중복 날짜, 범위 밖 날짜, 정규 거래일 degraded/pending/missing 또는 잘못된 수정시각
- METADATA_QUOTED_NOT_PIT: 정상 상태가 전체 정규 거래일에 보고됐을 때만 응답 구조 통과. **PIT 또는 종목 QQQ의 날짜별 가격/스키마 정확성 승인 불가**
- 토요일/일요일·거래소 휴장일의 missing / last_modified_date=null은 허용
- 추가 보고: expected_regular_sessions, covered_regular_sessions, missing_regular_session_count, condition_full_regular_session_coverage, condition_scope=dataset_level_not_symbol_or_schema_specific

Databento [공식 historical API 문서](https://databento.com/docs/api-reference-historical?historical=http)에서 get_dataset_condition은 종목별이 아닌 **dataset 전체** 일자별 quality/availability를 보고한다.

실제 Moon 환경에서 Databento 계정 인증은 AUTH_REQUIRED로 확인되어 실제 범위·비용·상태 API 조회는 수행되지 않았다. 테스트의 $28.75 등은 가짜 HTTP 응답이다. 이 단계는 외부 계정·계약·독립 timestamp가 확보되지 않아 미완료다.

## 테스트·다음 수락 장벽

관련 테스트 8개에서 14개로 확장하여 전체 상태 정상, 한 날짜 누락, 2일만 응답, 중복, degraded, 범위 밖, 주말/휴장일 missing, 비밀번호 유출 차단을 검증했다. Ruff·Mypy 통과. 전체 테스트 결과는 해당 커밋·작업 결과에 기록한다.

다음 필수 사항: 실제 데이터 계정으로 이용권/비용 조회, 2026-10-31 소급 수정 전후 원본 비교, QQQ trades의 ts_event/ts_recv·종목 ID/수정 내역·역사적 배포시각 검증. LSEG 데이터 범위·라이선스 견적 확인도 필요.

원본 보존 데이터, 봉인 OOS, MCP URL/OAuth, 실거래 차단, 2026-10-16 추가 수집 예약 일정 변경 없음. 운영 배포하지 않은 개발 브랜치의 연구 전용 검사다.
