# Quant Autoresearch V02 / 1-2 — QQQ 공급자 공개 시각·과거 데이터 증거

기준: 2026-10-15 UTC / 2026-10-16 KST. 코드 `feat/v02-publisher-availability-matrix-20261016`, 기능 `4c62d0d` 원격 Push. **운영 MCP da2331d 불변**.

## Moon 실데이터 평가

- 실제 보존된 Nasdaq QQQ 2020-01-02~2025-12-31 원본 3본(각 1,508봉)의 raw JSON·Parquet·매니페스트 각각 무결성 재검증 **3/3 PASS**.
- 실제 발행자 서명 `PUBLISHER_PROOF_MISSING` **3/3**. 입증된 과거 거래 시점의 공급자 발행/수신 시간 **0건**. 배치 상태 `INDEPENDENT_HISTORICAL_PUBLICATION_PROOF_MISSING`, 보고 SHA `3d633431d8b5ab36105333807102caa8df695324730aa9fa2a1c94221ccff9a2`.
- Databento 읽기 전용 과거 metadata probe 실제 호출 결과 **AUTH_REQUIRED**. 라이선스/권한·진짜 과거 timestamp를 확인하지 못했으며, 유료 데이터 수집·견적·계정 변경 없음.
- `docs/operations/evidence/quant-validation-20261016/v02-publication-coverage-audit.json`에 기존 3본 출처해시·원본 수집시각별 부족한 증빙과 실제 metadata 상태를 보존. 원본 가격 파일과 API 자격 증명은 GitHub에 올리지 않음.
- SHA-256·로컬 수집시각, 공급자가 지금 내놓은 수정본, 당일 조건상태는 해당 역사적 의사결정 당시의 공개가격을 입증하지 않는다. Historical PIT/봉인 OOS/실거래 승인 금지.

## 실제 기능 변경

- `research/indicator_engine/publication_evidence_matrix.py` 신규: 기존 Nasdaq archive 무결성 감사 + 외부 발행자 콘텐츠 서명 intake를 모든 보존 원본에 적용. 선택적인 `*.publisher-claim.json`/`*.publisher-claim.sig`가 불완전/변조/임의키면 fail closed; 로컬 수집시간이 결정 시각보다 늦으면 별도로 차단. signed claim과 독립 역사 시각을 혼동하지 않음.
- `research/indicator_engine/cli.py`: `audit-qqq-publication-coverage --archive-root state/vintages --from-date 2020-01-02 --to-date 2025-12-31 [--decision-at ISO8601]` 신설. 오프라인 읽기 전용. 신뢰키 임의 승격, OAuth/32 MCP 도구 변경 없음.
- `tests/research/test_publication_evidence_matrix_v02.py` 신규 **7개**: 빈·다중 원본, cutoff 미래정보, 불완전 proof, 임의 자체 서명키, 원본 변조, CLI 오류 민감내용 비노출. 기존 공급자/빈티지/Databento 관련 테스트 합계 **51 PASS**, Ruff/Mypy 변경파일 PASS.

## 외부 증거가 없어서 남은 수락 조건

1. 공급자가 공식적으로 지정한 키·실제 원본의 과거 발행 및 투자자 수신/가용 시각 기록과 독립 검증 권한.
2. QQQ / 2020~2025 / 구체 venue·schema의 이용권과 가격·보존권. 계정 인증은 현재 AUTH_REQUIRED.
3. 틱 `ts_event`와 수신 `ts_recv`·symbology/instrument ID/수정 빈티지의 검증된 원본. 데이터셋 `last_modified_date`는 특정 과거 거래시점의 공급 시각 인증으로 사용하지 않음.
4. 공식 참고: https://databento.com/docs/api-reference-historical 및 https://databento.com/docs/standards-and-conventions/common-fields-enums-types.

**V02 BLOCKED_EXTERNAL_EVIDENCE. 다음 V03(배당·분할·가격 수정 as-of 검증).** V01 신규 두 번째 UTC 수집은 2026-10-16 00:00 UTC 이후 별도 가능. 운영 MCP URL·OAuth·연구원장·실주문 비활성 모두 그대로.
