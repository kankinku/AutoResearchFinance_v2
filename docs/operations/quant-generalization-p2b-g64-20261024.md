# Quant AutoResearch 일반화 평가 — P2-B G64 실제 계승 StrategyIR 재생

**기준 시점:** 2026-10-24 KST
**상태:** 별도 개발 브랜치 구현/실제 QQQ 개발 기간 재생 완료, 운영 서비스 미배포, 미래 OOS 미검증.
**승계 계획:** [v2.0](quant-generalization-research-v2-implementation-20261024.md).

## 1. 구현과 경제적 동등성
- `research/indicator_engine/inherited_historical_robustness.py`: **원본 GPT 계승 StrategyIR**과 원본 감사 결과를 검증한 뒤 매 연도마다 시작 자본을 1만 달러로 초기화해 원본 `BacktestEngine`, 원본 비용 모델과 동일 기간 QQQ 유료 매수보유 기준으로 계산. 결과는 `INHERITED_IR_EX_POST_DEVELOPMENT_ONLY` / `independent_oos_approved=False` / `broker_executable=False` / `candidate_promotable=False`.
- 초안에서 G64의 `base_algorithm_plan`과 저장 IR을 직접 다시 결합하면 수익률·MDD·최종자본·40건 완료 거래는 **일치**했지만 `audit_hash`가 달라졌음. 실제 source vector는 S7 부모 체인에서 상속되므로, 단순 직접 recompute를 감사 성공으로 간주하면 잘못됨.
- 운영 DB의 `cycles.sqlite`, `gateway.sqlite`, `catalog-s6-v2.sqlite`를 SQLite **read-only source 백업 → isolated temp clone**으로 각각 복사. 원본 저장소 서비스 `AcademicMCPCheckpointService._inherited_from_evidence`에서 **선대 counted/S7 계보를 끝까지 감사**, 전체 감사 `audit_hash` 일치 확인. `AcademicCycleService.get`은 68/100 원본 chain 검증.
- 원본 전략: G64, StrategyIR SHA `197e0394ca384521203901691a82d0cc5537eafb99b5c017a37c33c27108d175`, full audit SHA `5a79ebcc29bd667890c0d0a1a51a81c087a5cc1906d10e7f92d13667c71a343e`, 개발 2020-01-02~2025-12-31, 전체 누적 +188.53%, MDD24.13%, 청산 40. 원본 Evidence chain의 G64 SHA `31844a04490312085bbed7e3c664f9bf93220c66366bd89edccedfa3ffe8fea3`.
- 로컬 QQQ RAW 비-PIT Parquet 1508개 일봉 SHA `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`, 이 데이터는 **매번 접근 시점에 수정될 수 있는 시장 데이터 공급본**이고 vintage/PIT 서명 아님. 2026 자료는 사용하지 않음.

## 2. G64 2021~2025 실측 연간 결과
연도마다 과거 바는 **지표 warmup에만 사용**, 그해 최초 완료 종가 이후부터 주문 생성/다음 거래일 시가 체결. 비용은 원본 `academic-research-cost-v1` (편도 commission 1bp + spread 2bp + slippage 5bp). 연도별 초기 현금 10,000 USD, 미청산 포지션 연말 강제 매도 금지. 비교 QQQ도 연초 첫 거래일 시가 매수가 아닌 **첫 날 완료 종가 다음 거래일 시가** 체결. 연도별 재설정 수익률의 합산/복리는 **원본 2020~2025 G64 전체 포트폴리오 수익률과 동일하지 않음**.

| 연도 | G64 비용후 수익률 | QQQ 비용후 가격 수익률 | G64 MDD | 체결 수 | 청산 수 | 지불 비용(달러) |
|---|---:|---:|---:|---:|---:|---:|
| 2021 | +9.80973% | +28.94733% | 9.73144% | 17 | 8 | 141.9107 |
| 2022 | -15.17971% | -33.85368% | 20.48286% | 16 | 8 | 112.9650 |
| 2023 | +43.30640% | +53.46249% | 7.34058% | 15 | 7 | 144.6574 |
| 2024 | +16.02608% | +27.72761% | 6.94434% | 17 | 8 | 146.2813 |
| 2025 | +15.68258% | +19.57116% | 7.21409% | 13 | 6 | 110.3798 |

- 결과 보고서 hash: `af6dc693f54c150a12366815e6b48134ba7238e2c386562db832e099804e89e1` (원본 DB의 불변 기록은 아님; 개발 도구 출력).
- 2021/2023/2024/2025 G64는 QQQ 대비 비용후 누적 연간 수익률 열위. 2022년 하락장은 G64 손실이 더 작았으나, 한 차례 방어 사례만으로 하락장 방어가 검증된 것은 아님. 장기 수익 최고와 강건한 시장 국면 성능 구별이 필요함.

## 3. 테스트와 누출 방어
- `tests/research/test_academic_inherited_historical_robustness.py`: 저장 G64와 동일 원리의 **감사된 StrategyIR fixture**로 테스트. 원본 전략 해시/자본/감사 해시/거래 건수 조작, sealed/validation 데이터, 없는 연도, 미래 가격 반영 불가.
- 후속 연도 변경 시 이전 연도 **경제적 수익·MDD·비용·체결 수**가 변하지 않음 확인. 단, 원본 전체 source dataset을 바꾸면 full audit/StrategyIR 출처 SHA가 바뀌므로 연도별 `evaluation_hash`가 다를 수 있으며, 이는 정상적인 원본 출처 인증 변화임.
- 전체 root 원장을 수정하지 않은 읽기 격리본에서 G64 원본 성공을 관측; prefix 연구와 실제 독립 시점별 GPT 재실행은 별개.
- 신규 기능 검증과 원본 source 코드 정적검사 PASS 여부는 개발용 pytest/Ruff/Mypy 기록에서 별도 확인.

## 4. 남은 작업
- **P3:** 이 리플레이 결과를 실제 부모 후보 선정에 연결하기 전 기존 68세대 전략 중에서 위험/성적 비교를 사전 고정한 점수/파레토로 통합. `ex-post` 강건성은 개발 참고 결과이지 OOS 승인 근거가 될 수 없음.
- **P4:** 실제 GPT 10세대 계획/진단/계승/중복 Evidence 검증, 이후 별도 연속 100세대.
- **P6:** 현재 2026 데이터는 도구에 등록되지 않았고, 사용자가 과거 2026 성적을 본 상태이므로 기존 2026 시기는 독립 미래 검증으로 승인하지 않는다.
