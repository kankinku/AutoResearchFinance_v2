# V01 / 1-1 실제 Nasdaq QQQ 원본 UTC 날짜 빈티지 — 현재 검사 결과

**점검:** 2026-10-15 UTC (한국시간 2026-10-16 새벽). 기존 Quant MCP URL, OAuth, 리서치 DB, 주문 비활성 정책 모두 보존. 이 단계에서 새 코드·서버 배포 없음.

## 진짜 Moon 데이터로 실행한 내용

- 보존 경로: 개발 연구 Worktree의 `state/vintages` (원본 JSON·Parquet·manifest; Git 기록에 원본 시세/개인 키 미포함).
- 실행: `python -m research.indicator_engine.cli audit-nasdaq-archive --archive-root state/vintages --from-date 2020-01-02 --to-date 2025-12-31`.
- 실제 결과: `capture_count=3` / `verified_capture_count=3` / `distinct_collection_days=1` / `first_captured_at=2026-10-15T11:09:47.343891Z` / `last_captured_at=2026-10-15T13:55:09.030650Z`.
- 모두 동일 수집범위: Nasdaq QQQ 2020-01-02~2025-12-31, 원본별 **1,508일봉**. 연속 2개 비교쌍 `total_compared_bars=3016`, 가격 수정 관측 `total_revised_bars=0`, 인벤토리 상태 `INSUFFICIENT_COLLECTION_DAYS`. 해시 `5297994a0c8fcff855437c84d12aa6c5e7bd530f5bd30dc1709dabf92752362c`.
- 동일 일에 실제 운영진입점 `collect-nasdaq-qqq-daily` 실행, 결과 `ALREADY_COLLECTED_TODAY` / `receipt=null` / 기존 3본 보존. 중복 HTTP fetch 없음. 과거 타임스탬프로 가장해 새 독립 수집본을 생성하지 않았다.
- 사용 중인 Moon 서버 UTC 날짜는 **2026-10-15**. 신뢰 가능한 *다음* 서로 다른 UTC 수집일은 2026-10-16 00:00 UTC 이후(Asia/Seoul **2026-10-16 09:00 이후**). 그 전 4번째 수집은 V01 최소 2개 수집일 조건을 충족하지 않는다.

## 오인 방지 및 검증

- 진짜 같은 업체에서 서로 다른 날짜에 수집한 두 빈티지는 아직 없음. 관측 수정 0건은 2026-10-15의 동일 일중 안정성을 보여줄 뿐, 2020~2025 과거 시점 정보 공개·실제 체결가능 가격을 입증하지 않는다.
- `point_in_time_verified=false`, `independent_historical_publication_verified=false`, `broker_executable=false` 고정. 임의 날짜 조작/원본 데이터 복제로 2일 조건을 통과했다고 표현하지 않음.
- 기존 archive/collector/inventory/vintage pair **4개 테스트 파일 총 29 PASS**, Ruff·Mypy 대상 코드 PASS. `docs/operations/evidence/quant-validation-20261016/v01-qqq-collection-day-gate.json`은 실데이터 감사 결과에서 생성한 출처·수집시각·무결성 요약(원본 바이트는 첨부/커밋하지 않음).

## 지속 작업 / 다음 진행 가능 순서

1. **V01 날짜 블로커:** 2026-10-16T00:00Z(한국 09:00) 이후 같은 아카이브에 동일 기간을 새로 `collect-nasdaq-qqq-daily` 1회 수행. 그 후 `audit-nasdaq-archive`를 재실행해 `distinct_collection_days>=2`와 변경 OHLCV 날짜·수량을 확인. 공급자 403/429 또는 네트워크 실패 시 오류로 기록하고 원본 덮어쓰기 금지.
2. 다른 UTC 수집일 확보 후에도 이는 **2개의 실제 로컬 수집 스냅샷**이지 역사 공개 시각을 증명하지 않는다. 더 긴 수집·공급자/발행자 독립 릴리스 증빙이 별도 필요.
3. 아직 UTC 날짜가 바뀌지 않았으므로 V01을 `BLOCKED_UTC_DATE`로 보존하고, **다음 실행 가능한 검증은 V02**(과거 발행/공급자 데이터 공개 시각 및 이용 권한 증빙). D08 운영 URL/OAuth, 실주문 disabled 유지.

이 단계는 일정/백그라운드 수집 자동화를 설치하지 않았다. 2일째 원본은 미래에만 얻을 수 있으므로 현재 완료로 주장하지 않는다.
