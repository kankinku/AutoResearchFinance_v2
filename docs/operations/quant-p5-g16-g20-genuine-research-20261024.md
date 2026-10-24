# Quant AutoResearch P5 — G16~G20 실제 연구 재개 및 20/100 감사

**2026-10-24 KST | T4 (원래 Q02·Q06·Q07·Q08·Q09·Q14·Q15·Q17·Q18·Q20)**

## 요청 대비 실제 완료

- 사용자의 "나머지 진행" 요청에 따라 기존 P5 세션 `3b44e05e52b3497db6fa035681ed0a5d`에서 **G16~G20 5세대를 이번 세션에서 실제 작성·백테스트·원인진단·S7 측정·세대 커밋**했다.
- **현재 20/100, 남은 80세대 미실행**. `AWAITING_PLAN` G21, 검증된 부모 후속 연구 경로 준비. 백그라운드 세대 실행 중이라고 주장하지 않는다.
- GPT 연구에 해당하는 모델 작성 각 세대의 inherited ResearchIntent와 측정 손실 trade ID 기반 대안/기전/실험 계획을 직접 생성해 `AcademicMCPCheckpointService.submit_plan/submit_diagnosis`로 제출했다. 단순 배치/ScriptedResearcher/OfflineProvider를 GPT 세대로 계수하지 않았다.

| 세대 | 부모·주제 | 실제 비용 반영 누적수익 | MDD | 종료 거래 | 노출 | 세대 원장 evidence SHA |
|---|---|---:|---:|---:|---:|---|
| G16 | 검증 G14 부모, breakout 이벤트 소멸을 종료 조건으로 테스트 | **-37.74%** | **38.65%** | **313** | 26.92% | `6acbf8c172a9658e3705efb7727ce7ec392ea7e1f96e9e2655407ae735f91cdd` |
| G17 | 검증 G13 S7 부모, 자본 비중 100→70% 위험 통제 | +32.76% | 11.82% | 54 | 45.76% | `36bba0fc0e2765ad8bf5bc39b6f9f9c3bc7dd01c8ae78875ba7dd593d689f34a` |
| G18 | 검증 G14 부모, EMA20 양의 값 추가 매수 조건 | +34.63% | 13.80% | 55 | 45.16% | `d54500e46e5aef1ea30e698d29782f85b5b7bb28a8266b01901c5e4c8b03795e` |
| G19 | 검증 G13 S7 부모, EMA20 양의 값 추가 매수 조건 | +43.29% | 16.07% | 52 | 45.42% | `f640919c806c878c1d9694b7a870e2219a8c5fa432379e79637514ce662cb7f5` |
| G20 | 검증 G17 부모(70% 비중), EMA20 매수 필터 재현 | +30.03% | 11.53% | 52 | 45.42% | `f514f9c2d907d0fc27b9e0a906bd91e4ebf4f44fb16a866dbb826264edf48316` |

## 확인된 연구 지식

- **G16 실패가 의미 있는 negative evidence**: 순간적인 돌파 신호 소멸을 청산 지표로 사용하면 거래 313회·비용/회전 급증, 누적 손실 37.74% 및 MDD 38.65%. S7에서 EMA20 지속 상태 종료를 대안으로 비교. 변동성/위험 필터가 동일 체결을 만드는 두 번의 시도(G16 long-momentum overlay, G19 long-momentum entry filter)는 `UNCHANGED_CANONICAL_FILLS`로 사전 거부되어 연구 세대 미계수.
- G17: 기존 G13 S7 부모 +47.36%, MDD16.46% 대비 70% 크기로 +32.76%, MDD11.82%. 명목 drawdown 감소는 배분 감소에 기인하며 별도 전략 초과성과 근거가 아님.
- G18(부모 G14) EMA 매수 필터 +34.63%, MDD13.80% 대 G14 +36.18%, MDD15.90%. G19(부모 G13 S7) +43.29%, MDD16.07% 대 부모 +47.36%, MDD16.46%. **동일 개발기간에서 위험 감소와 수익 하락이 동반**.
- G20 위험 예산 70%로 G19의 진입 필터 구조를 재현하니 +30.03%/MDD11.53%. 같은 데이터를 반복 사용한 **development sensitivity**, 독립 OOS 복제는 아님.
- 전체 20개 모두 비용후 2020~2025년 RAW 비-PIT QQQ DEVELOPMENT 가격 자료 재사용. QQQ 비용후 단순보유 약 +187.77%, 초과 없음. 실주문, 2026 독립 봉인 OOS, 시점별 PIT, 3자 모델 호출 영수증 모두 미승인.

## 증거 및 운영 검증

- `AcademicMCPCheckpointService.get`: counted **20/100**, 20개 고유 StrategyIR hash, 1~20 세대 번호·이전 evidence 연결 **PASS**, **S7 승인 20** 및 기존 no-effect 거절1, `inherited_strategy_ir=True` **7개(G14~G20)**. `orders_enabled=False`, `independent_oos_approved=False`.
- 원장 세 SQLite `cycles.sqlite`, `gateway.sqlite`, `catalog-s6-v2.sqlite`의 `PRAGMA quick_check=ok` 모두 확인.
- 대시보드의 원본 UI 유지: localhost 8081·8082 `/api/status` 실제 HTTP200 / **20/100** / evidence chain true, 이전 MCP 68/100 별도 URL도 HTTP200, 보호된 `/academic/` 무인증 HTTP401 유지. 인증/OAuth/MCP 등록, 운영 URL·주문 설정 변경 없음.
- 이 작업에서 정식 배치 80회 미실행. Moon `research/llm/provider.py`가 GPT HTTP/CLI 호출을 내장하지 않으며, 허용된 기존 연결은 ChatGPT MCP 외부 작성 Plan/Diagnosis 단계 제출뿐이다. 외부 모델 호출 인증을 신규 발급하거나 기존 OAuth를 변경하지 않았다. 진화 규칙 없이 백테스트 80회 반복을 80개 실제 GPT 연구 세대라고 주장하지 않는다.

## 상태 및 다음 게이트

**T4 개발 연구 진전 20/100; 사용자 요구의 잔여 85 중 5개 실측, 80개 NOT EXECUTED**. 불변 원장·대시보드 보존. 세대 G21 `AWAITING_PLAN`에서 GPT 작성 전략/진단을 이어가되, 80개를 무인으로 수행하려면 실제 ChatGPT 제공자의 인증/호출/서명 영수증과 본래 MCP 주도권 정책을 만족하는 자동 실행자가 먼저 필요하다. 기본 MCP를 별도 외부 API로 교체하는 것은 원래 20Q scope-lock의 별도 명시 승인 전 금지한다. 연구 진행이 사용자 승인 없이 백그라운드에서 지속된다고 말하지 않는다. 전체 repo 검사/독립 OOS/실거래 승인은 이 작업에서 실행하지 않았다.

**검증 보강:** GPT/S7 품질 게이트·부모 일반화·모델 출처·범위 거버넌스 회귀 `pytest` **21 PASS** (16.46초), 저장소 `ruff check .` **PASS**. 전체 저장소 pytest/mypy, 별도 PIT/OOS·운영 체결 검증 **NOT RUN**. 사용자 요구인 80개 추가 완결도 **NOT ACHIEVED**.
