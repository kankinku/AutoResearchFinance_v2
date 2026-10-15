# Quant Autoresearch — [1-2 / 5] 과거 시점별 가격 공개시각 증빙 (2026-10-15)

## 현재 판정: PARTIAL / historical PIT STILL UNVERIFIED

Stage 1-1의 실제 Nasdaq QQQ 캡처 2개는 2026-10-15 UTC 같은 날 수집한 최신 수정본이다. 2020~2025년에 각 가격이 어느 시점에 공급·전달됐는지 증명하는 외부 발행사 서명과 역사적 발행시각 기록은 아직 없다.

새 research/indicator_engine/publisher_evidence_intake.py는 기존 보존 원본 JSON/Parquet/매니페스트의 바이트 무결성을 다시 확인한 뒤, 선택적 Ed25519 detached signature/원문 해시/기간 범위 및 claimed publication date를 검증한다. 실공급자의 검증된 public key를 모은 TRUSTED_PUBLISHER_PUBLIC_KEYS는 의도적으로 비어 있으며, 사용자가 임의 키를 승인할 CLI는 없다. 합성 테스트에서만 임시 키를 사용했다.

**서명된 주장과 과거 시각의 증거는 다르다.** 오늘 서명한 문서에 2020년 published_at를 적어도 그 날짜 당시 자료가 존재했는지 입증하지 못한다. 별도의 독립 인증 timestamp/그 시점의 원본 received-at·publisher sending 시각/과거 수정 및 지연 기록을 검증해야 한다. RFC 3161 TSA의 증명 범위는 존재시각이며 그 자체가 거래소 일반 공개시각의 증명은 아니다.

## 실제 Moon 저장 원본 판정

- Scope: QQQ 2020-01-02~2025-12-31, 1,508 daily bars
- Captured raw SHA256: 6ede5c3b5b9926b9d820268aa607b41c3c0cfe60141a0ace13302a42f7193f40
- local_capture_replay_verified: true
- status: PUBLISHER_PROOF_MISSING
- publisher_signature_verified: false
- publisher_available_at_proven: false
- independently_timestamped_historical_release_verified: false
- independent_historical_pit_verified: false
- broker_executable: false

## 공식 문서에 근거한 공급처 예비 조사

| 공급처 | 공식 문서 확인 사항 | 실제 도입 전 필수 질문 |
|---|---|---|
| LSEG Tick History | Historical tick, point-in-time updates, PCAP/S3 Direct 및 거래소별 원본 제공 안내 | QQQ/해당 거래소 2020~2025 실제 커버리지, original receive/publisher times, 원본 인증, 수정 기록·가격, 라이선스 |
| Databento Historical | ts_event / ts_recv / ts_in_delta 지원하는 기록 포맷 설명 | 해당 거래소와 기간 범위, EOD 재구성 가능 여부, 지연 데이터/수정 이력, 비용, 원본 공개시각 |
| RFC 3161 timestamp authority | 특정 원본이 어느 시각 이전에 존재했다는 증명 표준 | 검증된 TSA 신뢰 루트·토큰과 실제 거래소 공개 시점을 별도로 검증 |

공식 문서 URL:
- https://www.lseg.com/en/data-analytics/market-data/data-feeds/tick-history
- https://www.databento.tech/docs/standards-and-conventions/common-fields-enums-types
- https://www.rfc-editor.org/info/rfc3161/

이 업체들이 필요한 형태의 2020~2025 과거 시점별 빈티지·인증 파일을 실제 판매/제공하는지, 권한/가격은 확인 전이다. 새 Ed25519 signed manifest는 우리 쪽 증빙 검증 인터페이스일 뿐 업체별 제공 포맷을 주장하지 않는다.

## 다음 수락 조건

1. 공급처의 실제 QQQ 2020~2025 historical as-of 데이터, 과거 수정/지연 이벤트와 시점 필드·계약 비용·이용약관을 확인하고 데이터 샘플 확보.
2. 공급자 key identity와 출처 및 역사적 timestamp authority/실제 원본 수신 시점 검증. 자기서명·자가 제공된 key·새 timestamp는 부족.
3. 결정 시각별 bar·corporate action·상장/상장폐지 정보를 당시에 이용 가능했던 레코드만으로 재구성. coverages와 수정 이력 동시 감사.
4. 후속 Stage 1-3 기업행동·Stage 4 독립 OOS·경제성 통과 전까지 실제 거래 차단.

로컬 read-only 명령:

    .venv/bin/python -m research.indicator_engine.cli audit-publisher-evidence --output state/vintages/qqq_archive_20261015.parquet --raw state/vintages/qqq_archive_20261015.raw.json --manifest state/vintages/qqq_archive_20261015.manifest.json

기존 Quant MCP URL/OAuth/연구 원장/원본 보존/봉인 OOS 및 실거래 차단은 변경되지 않았고 운영 배포도 하지 않았다. Stage 1-1의 2026-10-16 저녁(Asia/Seoul) 예정 재수집은 유지한다.
