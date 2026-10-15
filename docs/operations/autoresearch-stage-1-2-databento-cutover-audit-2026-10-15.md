# Quant Autoresearch — [1-2 / 총 5단계] Databento 소급 수정 전후 증빙 감사 (2026-10-15)

## 검증한 사실과 작업 범위

Databento의 2026-09-30 공식 공지에 따르면, 2026-10-31에 XNAS.ITCH 역사 데이터가 소급 수정된다. 2023-11-28 이전 instrument_id, 겨울철 EST 시간외 00:00~01:00 UTC 범위, 00:00 UTC 스냅샷 등이 대상이다. preview endpoint는 2026-09-30부터 사용 가능하지만 **공개 공지상 기존 historical 요청과 동일한 과금·plan 적용**이다. 본 작업에서는 preview/production 원본 데이터를 다운로드하거나 유료 요청하지 않았다.

공식 근거:
- https://databento.com/blog/nasdaq-historical-data-changes-2026-09
- https://databento.com/docs/api-reference-historical?historical=http
- https://databento.com/datasets/XNAS.ITCH

## 새로운 연구용 기능

research/indicator_engine/databento_cutover_audit.py는 **Databento dataset condition JSON 메타데이터**를 로컬에서 별도 파일로 저장하고,
원본 SHA-256, UTC 캡처 시작시각, environment(production/preview), 요청 기간/데이터셋 식별자를 소형 매니페스트와 함께 남긴다.
기존 파일에 덮어쓰지 않고 timestamp로 디렉터리를 새로 예약한다.
다시 읽을 때는 원본 SHA, 날짜/범위, 현재 시점보다 미래에 캡처된 주장, 미래에 수정됐다는 condition, 자료가 누락된 정규 거래일,
중복·비정상 날짜, 허용하지 않은 환경/데이터셋, 경로/파일의 개인용 접근권한을 재검증한다.
두 날짜의 요청 범위와 실제 로컬 캡처 시점이 비교 가능할 때만 변경 condition 기록을 보고한다.
preview→production과 production→production 전환은 혼동하지 않으며, 변경 기록이 없더라도
실제 Nasdaq ITCH 시장 패킷/호가/체결/기록된 instrument_id의 변경이 없었다는 뜻은 아니다.

정형 출력: changed_days, changed_dates, environment_pair, 소스 해시와 비교 해시.
항상 historical_pit_verified=false, post_cutover_production_verified=false,
market_packet_revisions_verified=false, broker_executable=false.
로컬 해시나 로컬 수집시각은 외부 시각 인증이 아니다. 사용자가 작성한 JSON을 Databento 진짜 응답이라고 보증하지 않는다.
현재 이 검증기는 계정 없이 사용할 수 있는 **오프라인 준비 단계**이며 테스트 입력에는 합성 예시만 사용했다.

### 저장 파일이 실제로 준비된 뒤 실행

    .venv/bin/python -m research.indicator_engine.cli compare-databento-condition-vintages --earlier <earlier-folder> --later <later-folder>

이 명령은 외부 API 연결/구매/예약 작업 변경 없이 로컬 두 스냅샷의 해시·기간·수정 상태를 검사한다.
향후 실제 조건 응답은 Databento 계정과 적법한 권한을 확인한 뒤,
preserve_condition_snapshot(...)에 진짜 반환된 원본 JSON을 전달하는 코드 경로로 보존해야 한다.
실제로 획득하지 않은 과거 데이터를 합성하여 저장하거나 두 수집일을 소급 입력하는 것은 승인 불가다.

## 실제 Moon 실행 환경

- state/vintages/ 아래의 과거 Nasdaq 공개 QQQ 저장본은 보존됨.
- XNAS.ITCH Databento condition 증빙 파일: **0건 확인**.
- Databento 계정 API 인증: 앞 단계에서 AUTH_REQUIRED; 실제 공급자 가격 견적, preview 자료 및 라이선스 확인 전.
- 2026-10-31 이후 production 데이터는 2026-10-15 현재 미래 자료이므로 아직 확보 불가.
- 테스트 통과는 합성 데이터의 검증기 동작만 입증하며 상품의 historical PIT를 입증하지 않음.

## 1-2단계 종료 전 필수 단계

1. 실제 Databento 이용권·계정별 기간/비용과 시장 데이터 라이선스를 확인한다.
2. 공식 시점별 QQQ event/receive 데이터의 원본/출처·해시·수정본을 당시 가용 시각과 연결한다.
3. 2026-10-31 수정 전후 실제 동일 기간 XNAS.ITCH 자료와 instrument_id/정규장+시간외 변경을 별도 비교한다.
4. 공급자의 서명·발행시각 또는 신뢰할 수 있는 과거 시점별 전송/수신 기록이 검증될 때까지 PIT 승인·브로커 주문 금지.

다음 개발 우선순위는 외부 서비스 계약이 필요한 1-2의 증빙 확보와 병행하여
기존 시스템 핵심 목표인 [2-1] ChatGPT MCP 연구 도구의 실제 End-to-End 호출 및 상태 검증으로 이동할 수 있다.
1-1단계의 기존 2026-10-16 저녁(한국 시각) QQQ 캡처 예약은 유지한다.
원래 등록된 MCP URL/OAuth/운영 원장, 봉인된 OOS, 거래 비활성 상태와 배포 프로세스는 변경하지 않았다.
