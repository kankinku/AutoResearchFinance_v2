# Quant V3 Track1 — 나머지 68개 후보 4차 이식 및 중복 감사
2026-10-28 · research/v3-strategy-evolution

## 범위·결과
- 기준: 이전 연구 지표 **321개**, 마지막 전수 분류에서 **68개 보류**. 이번 변경은 연구 브랜치만 수정, Frozen main / G1–150 원장·부모 계보·해시 / OAuth·MCP URL / 독립 OOS / 주문 비활성 유지.
- 추가 수식 기반 **13개 scalar 출력**: TA-Lib BSD-3 원본 공식을 참고한 `talib_ibs`, `talib_si`, `talib_asi`, `talib_frama`; Stock Indicators Apache-2.0 원본을 참고한 `stock_gator_upper`, `stock_gator_lower`, `stock_pmo`, `stock_pmo_signal`, `stock_roc_wb_upper`, `stock_fcb_upper`, `stock_fcb_lower`, `stock_stddev_channel_upper_now`, `stock_stddev_channel_lower_now`.
- Pandas TA MIT `pta_amat`의 단일 등록 결과가 누락했던 **숏런 출력 `pta_amat_short` 1개**를 별도 output index=1로 이식. 총 **14개 추가, 연구 카탈로그 321→335개**.
- 출처 pin: TA-Lib C `4334163d3a1f5019aa9051342316b936a4dfb994` BSD-3; Stock.Indicators C# `da428182d0e222339b662bc8ac645596102260bd` Apache-2.0; pandas-ta-classic `7c669b033582d53b70aa68b6388796d19ce33979` MIT.
- `core/features/source_remaining.py` 구현, `core/features/catalog.py` / `calculators.py` 통해 기존 StrategyIR 계산 경로와 연결. Pinned 소스/인덱스 전환 금지. 14개 feature id가 모두 유일하도록 검증.

## 수학적·시차 처리
- `talib_si`는 Wilder swing index의 당일 고저·전일 종가·몸통 기반, `talib_asi`는 그 누적 변화량. `talib_frama`는 인과적 반기간 극값 기반 가변 평활, `talib_ibs`는 당일 종가의 전체 고저 범위 내 위치.
- Stock Gator는 이전 이식된 **미래 이동 없는 Alligator 평균** 3개의 차이로 생성하고, 원본 그래프의 미래 표시(plot shift)를 전략 입력으로 쓰지 않음.
- PMO/시그널은 ROC → 2회 EMA, 주기 고정(35/20/10)으로 구현. ROC-WB는 ROC의 RMS 범위 상단 출력.
- Fractal Chaos Bands는 양측 **확인에 필요한 2개 바가 모두 종료된 시점**에서만 해당 극값을 관찰. 전후 확인된 과거 위치로 새 신호를 소급 기록하지 않음.
- 원본 Stock StdDev Channels의 윈도우 완성 시 과거 출력 소급 수정은 재도색 위험. 별도의 `_now` 구현으로 **그 시점 회귀와 표준편차 밴드만** 출력함. 원본과 모든 시점의 값이 동일하다고 주장하지 않음.
- 합성/유한값/충분한 warmup/prefix 테스트 통과 범위만 Registered 처리. C/C# 원본 바이너리와 전 기간 ULP/숫자 parity, 실제 거래/경제성/독립 OOS는 **검증 전**.

## 중복·미완료
- 원래 68개에서 신규 구현한 **9개 원본 후보 그룹(13 출력)**, 기존 ported Pandas TA AMAT에서 별도 scalar **1 출력** 추가. 나머지 원본 후보 **59개는 아직 추가 이식 완료가 아님**.
- 예: `crsi`는 기존 `connors_rsi`와 지표 정의가 겹치므로 중복 등록하지 않음; `hl2`, `hlc3`, `kurtosis`, `skew`, `mcgd`, `wilders`, `mass` 등의 기존 수학 계열 후보와 표준 `cdl` 패턴 래퍼는 별도 수치 동치 확인 전 추가하지 않음.
- 그중에 TA-Lib의 `wavetrend`, `dosc`, `sqzmom`, `swak_*` 등은 C 수치 parity 및 소스 빌드/룩백 검증이 필요해 Pending; Stock의 `renko_atr`은 이벤트 기반 벽돌 구축의 시차 조건 검증 필요; LGPL Tulip 전용 포트는 라이선스 검토 전 보류.
- **미이식=중복이라는 뜻이 아님.** 사용자 요청의 "중복 아니면 모두"는 이 차수까지 완료되지 않았고, 사용 가능한 새 14개와 미검증 항목을 구별한다.

## 검증
- `tests/core/test_v3_remaining_indicator_ports.py`에 개별 13개 finite, 동일 prefix, flat IBS, 확정시점 FCB, 악의적 lookback 변경 차단 확인.
- `pta_amat_short`는 기존 `test_v3_pandas_ta_bulk_source.py` 전체 whitelist 테스트에 포함.
- 전수 이름 후보 330개 원장 `scripts/v3_audit_330_source_names.py` / `quant-v3-330-source-full-disposition-20261028.json` 업데이트. full-history regression/OOS/실거래 없음.
- 릴리스 요구 `uv` 명령은 Moon 호스트에서 아직 해결되지 않았음. 개발 venv의 Ruff/MyPy/pytest는 별도 진단임.

**후속 조건:** TA-Lib C 원본 수치 oracle과 신규 68 전체의 중복 수식 parity 결과 확인 후 남은 비중복 후보 이식/등록. 개발 checkout만 변경하며 운영 활성화하지 않음.
