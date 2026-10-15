# Quant Autoresearch — [1-1 / 5] 실제 Nasdaq QQQ 원본 다중 수집 (2026-10-15)

## 검증된 실데이터 결과 (Moon 호스트)

Nasdaq 공개 QQQ OHLCV endpoint에서 동일 요청 구간 2020-01-02~2025-12-31의 원본 최신 수정 데이터를 독립 HTTP 요청으로 두 번 실제 수집했다. 두 데이터 모두 정확히 **1,508개 거래일**이며, 각 응답의 원본 JSON/Parquet/매니페스트를 보존하고 원본 바이트 SHA256과 JSON 재파싱·Parquet 데이터 해시 일치 검증을 통과했다.

| 지표 | 실제 결과 |
|---|---|
| 1차 수집(UTC) | 2026-10-15T11:09:47.343891+00:00 |
| 2차 수집(UTC) | 2026-10-15T11:15:44.630719+00:00 |
| 각 응답의 raw SHA256 | 6ede5c3b5b9926b9d820268aa607b41c3c0cfe60141a0ace13302a42f7193f40 |
| 각 응답의 거래일 | 1,508 / 1,508 |
| 공통 거래일·변경 거래일 | 1,508 / 0 |
| 두 수집본 비교 해시 | 18a45b498e5e7a4647fce2643811f6c18ae7749d9d050d1f3d4908f53946226c |
| 1차 검증 해시 | 2af182d3f7377fbb0641e444f3ade4f31e5dd797b0e8fa9dfa2c82d8d1cb8e93 |
| 2차 검증 해시 | 7a34a1eacc52a6742a6649d8de675f76782462592009c1fc1ff5448a221d6920 |

**중요:** 두 수집본은 약 6분 간격으로 확보한 같은 업체의 2026년 현재 수정본이다. 같은 내용은 해당 6분 사이 관측된 수정이 없다는 것만 의미하며 2020~2025년 당시 공개 가격·조정 이력·출처의 독립 서명된 시각을 입증하지 않는다. 따라서 historical PIT, 독립 issuer/custodian split, sealed OOS, 실거래 수익성은 모두 **미검증**이고 broker orders는 계속 **비활성**이다.

## 구현 내용

- 새 research/indicator_engine/nasdaq_append_only_archive.py: 실행할 때마다 실제 UTC 수집 시작 시각(마이크로초)으로 새 디렉터리를 배타적으로 예약하고, 원본 JSON·Parquet·매니페스트 작성 및 로컬 리플레이 무결성 검증 후 결과를 반환한다. 이름 충돌 시 기존 저장물을 건드리지 않고 실패한다. 수집 실패 시 해당 새 디렉터리만 정리한다. 0700 디렉터리와 0600 파일 권한. 기존 상위 저장 루트가 공개 권한이면 임의 chmod 대신 안전하게 실패한다.
- research/indicator_engine/cli.py 새 서브커맨드 archive-nasdaq-qqq로 재수집할 수 있다. 이전 수집본이나 MCP 운영 state에 덮어쓰지 않는다.
- .gitignore에 /state/vintages/를 추가하여 공급자 원본 시세·매니페스트·Parquet의 Git 추적을 방지했다. 첫 실제 수집본도 로컬에서 권한을 강화했다.
- 범위·중복·결함·개발 데이터 조건의 단위 및 CLI 통합 테스트. 이전 compare-nasdaq-vintages로 두 실제 수집본의 시점·가격 이력을 읽기 전용 대조했다.

## 다음 진척도 및 재수집

**1-1 단계는 최초 2개 실데이터 수집 성공, 장기 반복 수집은 미완료**로 유지한다. 이후 다른 날짜(가능하면 최소 24시간 후)에 새 저장본을 확보해 이미 보존된 첫 수집본과 비교해야 한다. 시간당·일별·주별 수집을 일정하게 유지하고 네트워크 오류·429/403·수집 범위 오류는 실패 기록으로 구분해야 한다. 다음 명령은 수동 재수집에도 사용할 수 있다. 별도로 ChatGPT 작업을 2026-10-16 저녁(Asia/Seoul) 한 번 실행하도록 등록했으며, 당시 Moon 접근 가능 여부와 실제 수집 성공은 그 시점에 확인해야 한다. 이 자동화는 Moon 호스트의 Cron/Supervisor 또는 기존 MCP 서비스를 변경하지 않는다:

    .venv/bin/python -m research.indicator_engine.cli archive-nasdaq-qqq --from-date 2020-01-02 --to-date 2025-12-31 --archive-root state/vintages

모든 수집본은 무조건 NON_PIT_SOURCE_CAPTURE / LOCAL_CAPTURE_BYTES_VERIFIED 단계이며, 장기 실측 수집을 진행해도 independent published PIT certification은 자동 부여되지 않는다. 원래 등록된 /quant/mcp URL, OAuth·원장·기존 런타임 프로세스는 변경하지 않았고 새 코드는 운영 배포하지 않는다.
