# Quant Autoresearch — [1-1 / 전체 5단계] Nasdaq 원본 수집 이력 감사 (2026-10-15)

## 이번 개선

QQQ의 보존된 원본을 읽기 전용으로 검사한다. 최초 legacy flat 트리플과 새 UTC 시각 폴더의 원본 JSON, 매니페스트 SHA256, Parquet을 모든 캡처마다 다시 검증한다. 캡처를 시간순으로 배열해 날짜 누락과 이전 스냅샷 대비 수정된 가격 행을 보고한다.

- 파일 변조, 심볼/기간 혼합, 보관 경로 심볼릭 링크, 개인용이 아닌 접근 권한 및 불완전한 트리플 차단
- 같은 날짜 2번 수집을 2일 연속 수집으로 잘못 표기하지 않음
- UTC 달력 날짜 누락 검출 (거래일이 아니라 자료를 수집한 날짜)
- 인접 캡처별 가격 변경 및 로컬 해시를 검증해 비교 결과를 재현 가능하게 기록
- 증빙 상태와 PIT/브로커 승인 여부 분리

## 실제 Moon 수집본 감사 결과

- Scope: QQQ 2020-01-02~2025-12-31
- Capture count: 2 / replay-integrity verified: 2
- Distinct UTC collection dates: 1
- First captured: 2026-10-15T11:09:47.343891+00:00
- Last captured: 2026-10-15T11:15:44.630719+00:00
- Consecutive comparisons: 1; total compared bars: 1,508; revised bars: 0
- Missing UTC collection dates between first and last: 0
- Status: INSUFFICIENT_COLLECTION_DAYS
- Inventory hash: 47575af75e9f8a482ff2d57c61a86df477556b2ab8984e9aa6c8d6a66cf58edb
- Historical PIT verified: false; independently signed publication time: false; orders enabled: false

두 실수집본은 약 6분 간격이다. 관측된 수정 0건은 당시 수집본 사이의 무변경을 뜻할 뿐, 과거 2020~2025년 원본 가격의 시점별 공개 여부는 인증하지 않는다.

## 실행 명령

    .venv/bin/python -m research.indicator_engine.cli audit-nasdaq-archive --from-date 2020-01-02 --to-date 2025-12-31 --archive-root state/vintages

기존 2026-10-16 저녁(한국 시간) 일회성 추가 수집 일정은 그대로 유지한다. 추가 수집 성공 후 다시 동일 명령으로 서로 다른 날짜의 보존 여부와 수정 이력을 확인할 수 있다. 최초 다른 UTC 날짜 수집본 확보 전까지 1-1단계는 진행 중이다. 1-2단계의 역사적 외부 시각 인증은 별도 필수 과제다.

기존 MCP URL/OAuth/연구 원장/실거래 비활성 상태는 변경하지 않았으며 새 코드는 운영 배포하지 않았다.
