# Quant AutoResearch — 기존 세션 G251~G350 연구 완료 (2026-10-19 KST)

## 완료 판정과 운영 보안

- 동일 공식 세션: `72495cc59fc147e08f4b433b98676fca`; **350/350 `COMPLETED`**, 250개 원본 이후 G251~G350 **100개 정식 추가**.
- 원본 끝 G250 Evidence: `bb48e290f44d214d4d3c9544316434e7e6ff08adefca5326ea78775f17297f55` 그대로; 신규 G350 Evidence: `26647e424913125cee1ec1dd6333538938237fb7205f7fc5147519b9c6cb725d`.
- SQL 읽기 전용 독립 집계: 350개 Generation 행, **350개 서로 다른 Evidence 해시, StrategyIR 해시, Algorithm semantic 해시**. 저장된 Gateway S7 **350건**, Generation timings **350건**. Extension receipt `(50→150, 50), (150→250, 101), (250→350, 250)` 존재. 손실·실패도 그대로 보존하고 부적절한 Plan 제출은 정식 세대로 집계하지 않음.
- S2 계획/실측 진단→S7 동일 데이터/비용 통제→원장 커밋 완료; 공식 보고 `all_proposed_hypotheses_measured=true`, `tested_hypotheses=350`. `model_autonomy_verified=false`, `independent_profitability_verified=false`, `causal_status=NOT_ESTABLISHED`; 실거래 `orders_enabled=false`, MCP 주소 및 OAuth 정보 불변.
- 원장 변경 전 5개 SQLite 원본의 **별도 백업**: `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/backups/quant-session-pre350-20261019-72495cc5`; 완료된 상태의 원장 백업을 이전 시점으로 복원하지 않음.
- 코드 기능 브랜치 `feat/quant-same-session-350-20261019`, SHA `8d31e3c1a3a7244ed6d7df9097aececa8db34f99`, SHA-pinned read-only source runtime `/shared/moon-workspace/AutoResearchFinance_v2-runtime-same-350-20261019`; 배포 브랜치 SHA `868e80d`; URL/OAuth/실주문 변경 없음.

## 전략 성과 (같은 개발기간: QQQ 2020-01-02 ~ 2025-12-31, Tiingo raw parquet)

| 항목 | 누적 순수익률 | MDD | 샤프 | 완료 거래 | 시장 노출 |
|---|---:|---:|---:|---:|---:|
| 기존 전체 최고 G178 | **+87.9047%** | **7.0055%** | 1.2520 | 58 | 31.6313% |
| 신규 100세대 최고 G273 | +83.7802% | 8.8510% | 1.1269 | 66 | 34.0186% |
| 신규 주요 후보 G302 | +81.8583% | 7.0055% | 1.1836 | 61 | 32.0955% |
| 신규 주요 후보 G307 | +83.5804% | 8.8510% | 1.1389 | 61 | 33.4218% |
| 신규 G338 | +80.1059% | 10.8669% | 1.0686 | 40 | 36.5385% |
| 정식 마지막 G350 | +78.9824% | 8.6677% | 1.1409 | 61 | 32.8249% |

- G251~G350 전략 평균 누적 수익률 **+49.6354%**, 중앙값 **+56.3581%**, 평균 MDD **10.2958%**; 손실 전략 **1개** 포함. 이는 **같은 기간을 각 전략이 별도 백테스트한 횡단면 평균**이지 100회 복리 누적 수익률이나 독립 재현 확률이 아니다.
- 비용·데이터 조건을 같은 발전 구간에서 설정했지만 개별 전략이 QQQ 장기 단순 보유(**+187.7724%**)보다 수익률이 낮음. 최고 G178도 QQQ 대비 **−99.8677%p**; 이번 최고 G273은 **−103.9922%p**.
- 기존 최우수 G178에 비해 G273이 낮은 이유를 S7 가설 방향 일치만으로 인과적으로 귀속하지 않음. 가격 구간 반복사용, 검색 횟수 증가에 따른 과적합, 노출·거래비용 차이, 데이터 PIT 미검증이라는 한계를 유지.

## 실제 연구 과정, 검증 수준 및 다음 게이트

- 실행 종류: 외부 GPT가 설계한 **규칙보조 탐색 루프**. 반복 실행의 새 후보는 증거 우수 전략 및 계량 규칙에 따라 생성되었으며 매 세대 **독립 LLM 모델이 새 메커니즘을 직접 제안한 것은 아님**. S7은 측정된 개발기간 대조일 뿐 엄밀한 인과증거·검증된 부모자동계승·독립 OOS가 아님.
- 개발 변경: 기존 최대 300세대 upper bound에 대해 **400세대까지** 연속 세션을 안전하게 지원. 새로운 세션 시작 API 한도 `1..100`은 그대로 둠. 코어 변경 없이 범위 검증/스키마 조정. 이번 작업 별도 Shadow 250→350 **PASS**, Ruff **PASS**, Mypy 전체 **277 source files PASS**, 표적 테스트 **43 PASS**, `git diff --check` PASS. 저장소 전체 신규 Pytest **이번 변경 후 재실행하지 않음**; 이전 250 확장 때 전체 **1,741 PASS**였음. 검증 구분을 유지.
- 원본 SHA 고정 런타임을 새 code/worktree로 전환하기 전에 Gateway stop, 원본 DB SQLite backup, 과거 증거 head SHA 검사, 정식 완료 상태 `COMPLETED` 및 measured S7 확인, 원본 세션 확장 `250/250 → 250/350`, 재시작 후 MCP `AWAITING_PLAN 251` 확인; 연구 G251~G350 원장 commit 완료.
- **다음 우선순위**: G178 및 G273 실거래비용·체결 재생 검증, 진짜 GPT 세대별 근거·실패 진단과 검증된 S7 자식 → 정식 부모 계승 증명, 재사용 QQQ와 다른 데이터/시장 및 독립 PIT/OOS 실시. 실거래 및 OOS 승인 없이 계속 disabled.
- 20Q 계획의 T4 연구와 V01~V04 검증, V06 paper, V07 GO/NO-GO 순서를 바꾸지 않음.
