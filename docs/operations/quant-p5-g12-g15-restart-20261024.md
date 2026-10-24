# Quant AutoResearch — P5 G12–G15 재개 실측·미실행 세대 보고

**2026-10-24 KST | T4 / Q02·Q06·Q07·Q08·Q14·Q15·Q17·Q18·Q20**

## 실제 결과

사용자 요청 **"89세대 다시 시작 다 하고 보고"** 를 받고 이전 P5 세션 `3b44e05e52b3497db6fa035681ed0a5d`을 **G12에서 재개**했다. 기존 G1~G11은 그대로 보존. 실제 ChatGPT가 세대별 모델 컨텍스트를 확인하고 AlgorithmPlan 또는 inherited ResearchIntent를 작성·제출했으며, 실제 백테스트 이후 관측 손실 trade-id로 DiagnosticResponse, 가설 대안·S7 실험을 작성·제출하였다.

**결과는 15/100, 이번 작업 신규 4세대, 남은 85세대 NOT RUN.** 89개를 전부 실행했다는 주장은 금지. P5는 `AWAITING_PLAN` **G16**에서 안전하게 재개할 수 있다. 백그라운드 연구 프로세스/외부 GPT 모델 호출은 가동 중이지 않다.

| G | GPT 연구 접근 방식 | 비용후 개발 누적수익 | MDD | 완료 거래 | 노출 | counted evidence hash |
|---|---|---:|---:|---:|---:|---|
| 12 | SMA20 상승 추세 / 약세 돌파 예외 2-branch 신규 계획, 모멘텀 지연 청산 통제실험 | +51.70% | 21.40% | 57 | 54.24% | `86f3eee0075827b76112a224c61e7fcb9702f6b81bcdf8914001bf7001650be6` |
| 13 | SMA20 강세 속 장기 모멘텀/저가 재탈환, 약세 EMA/돌파 병행 신규 계획; EMA20 위험청산 S7 | +36.97% | 15.90% | 57 | 45.36% | `eb54807853592750415ea5b4c9f2cde3dbe68df8c09f256adeb586e4f1d5960f` |
| **14** | **G13 검증 자식 자동 부모선정 이후 실제 inherited ResearchIntent**: EMA20 종료→SMA20 종료, 연간 모멘텀 종료 통제실험 | +36.18% | 15.90% | 56 | 45.42% | `7d558e356754be26ac7a4bf0a1d1502227188ed3b58aefa83d62a3200774bb6a` |
| **15** | **G13 검증 자식 재계승**: EMA20 종료→연간 모멘텀 종료; 짧은 SMA 종료 반증 S7 | +71.50% | 24.32% | **5** | 64.85% | `d6c0e20e690074e5f042d20b5808afcfa6d0495919792c431278c23bb8dd71c1` |

S7 품질 원장 승인은 **15/15**, 기존 누적 `NO_OBSERVED_EFFECT` 1개 거절은 counted로 취급하지 않았다. G14에서 신규 AlgorithmPlan을 제출하려던 최초 시도는 계승 계약 전환으로 거절되어 미집계. G15의 SMA20 regime overlay도 실행 체결 변경이 없는 `UNCHANGED_CANONICAL_FILLS`로 거절되어 미집계; 이후 진짜 체결 변경을 일으킨 `REPLACE_RULE`로 정상 진입했다.

## 중요한 개선 및 실패 해석

- **P0-3B 부모 계승이 실제로 작동하기 시작함**: G13 S7 자식은 개발 +47.36%, MDD16.46%, 완료 거래54, 노출45.76%; 원본/자식/후속 StrategyIR·거래·비용·해시 replay로 G14용 부모로 선택되었다. `parent_portfolio_v2` 및 `p4_quality_gate_v1` 활성 상태 그대로였다. G14, G15의 `inherited_strategy_ir`가 **True**여서 실제 counted inherited 2개 검증. 마지막 G16도 적격 부모 존재(`source_generation=14`)를 확인.
- **문제: 더 높은 누적 수익이 반드시 좋은 전략은 아님.** G15 +71.50%는 고작 완료 거래 5건, MDD24.32%이며 거래 감소/노출 증가 효과에 크게 좌우된다. 5건 전략을 연구 품질 부모로 자동 승격하는 것은 금지; 실제 parent gate는 30건 이상 등 엄격한 기준 유지.
- 다른 11개와 마찬가지로 **2020~2025 QQQ RAW 비-PIT 개발 구간**이며 비용후 가격 기반 QQQ 단순보유 +187.77% 대비 새로운 4개 후보 모두 열위. 독립 OOS/실현 가능한 순수익 증거 아님.

## 감사·운영 보존

- 실제 `AcademicMCPCheckpointService.get`: `completed_generations=15`, `requested_generations=100`, `checkpoint_phase=AWAITING_PLAN`, 독립 해시 **15개 전부 중복 없음**, 1~15세대 순서·이전 `evidence_hash` 연결 PASS, `p4_s7_quality_audit.approved_count=15`, `orders_enabled=False`, `independent_oos_approved=False`.
- 새 P5 분리된 SQLite `cycles.sqlite`, `gateway.sqlite`, `catalog-s6-v2.sqlite`: `PRAGMA quick_check=ok` 3개. 원본 P4/과거 MCP 68세대/OAuth/대시보드 고정 URL/실거래 설정 변경 없이 사용. **실제 API 감사**: localhost 8081 및 8082 `/api/status` 모두 HTTP 200 / P5 **15/100** / evidence chain true, 이전 MCP 68세대 read-only HTTP 200 / chain true, 기존 `/academic/` unauthenticated HTTP 401 정상.
- 외부 실제 모델 호출 signed capture 영수증 P4-2 **NOT AVAILABLE**; P5는 사용자 대화에서 GPT가 각 제출을 작성한 근거는 있지만 독립 제공자 출처 검증은 미완료.
- `research/llm/provider.py`: embedded API model client 없음; `GPTIntentProvider`는 외부 GPT 요청을 받아 전달하기만 함. Moon 실행환경에서 `OPENAI_API_KEY`와 `OPENAI_BASE_URL`, `codex` CLI 부재. 이미 연결된 ChatGPT MCP가 각 계획·진단을 제출받는 구조일 뿐 `get_algorithm_research` 한 번으로 향후 85세대 모델 응답을 생성하지 못한다. **GPT 독립 호출 없는 규칙 기반 85회 반복을 GPT 진화로 가장하지 않았다.**
- 오늘 사용자 요청의 89개 전부 달성은 **FAIL (4/89 신규 실측 완료; 85 미실행)**. 서비스·원장·연구 성공과 실패를 분리한다. 새 모델 API/OAuth 계정 생성·수정 또는 주문 기능 활성화는 수행하지 않음.

## 이어서 실행할 작업

P5 **동일 세션 G16**: 해당 시점 `model_context.output_contract` (현재 `InheritedResearchIntent`)을 확인하고 실제 검증된 부모·손실 사례를 기준으로 한 모델 판단만 제출. 이후 real LLM 모델 호출을 수행할 수 있는 명시적·감사가능한 invocation bridge를 제공자 권한·비용/계승 증거 통제하에 확보해야 genuine 85세대를 자동 진행할 수 있다. 운영 기본 MCP를 새로운 API로 무단 변경하지 말 것. V05→T4→V01~V04→V06→V07의 기존 제품 개발 순서 및 PIT/OOS 차단을 유지.

**이번 단계 회귀 검증:** 부모 일반화·P4 S7 커밋·거버넌스·모델 영수증 단위 시험 **21 PASS** (15.79초), 전체 저장소 `ruff check .` **PASS**. 전체 저장소 pytest/mypy 및 실거래/독립 OOS는 **NOT RUN**. 원장·대시보드 서버는 기존 실행경로 유지, 운영 OAuth 재발급 없음.
