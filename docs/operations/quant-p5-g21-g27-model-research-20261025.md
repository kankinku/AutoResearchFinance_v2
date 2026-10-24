# Quant AutoResearch P5 — G21~G27 직접 GPT 연구 재개 및 운영 감사

- Date: 2026-10-25 KST
- Stage: **T4** (Q02, Q06, Q07, Q08, Q09, Q15, Q17, Q20)
- Session: `3b44e05e52b3497db6fa035681ed0a5d`
- State: `/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024`
- Research root: `/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021`
- Current **27/100, G28 `AWAITING_PLAN`, 73 NOT RUN**. No worker left running; no model API added or OAuth replaced.

## 실제 GPT 작성 판단과 정식 원장 측정

이번 작업은 **채팅 GPT가 직접 각 연구 계획과 실측 결과별 진단을 작성하여 연결된 Moon 도구로 제출**한 것이지 자동 GPT provider, Work 지속 작업 또는 결정적 로컬 모델의 7회 반복이 아니다. *별도 모델 공급자 서명 영수증/P4-2 독립 검증은 없다*. 매 세대 `submit_plan` costed canonical S2→`submit_diagnosis` GPT 거래/실패 근거·대안 가설→S7 control→counted commit을 실제 실행했다.

| Gen | 개입 및 GPT 진단 | Dev 비용후 총수익 | MDD | 종료 거래 | 노출 | Counted evidence SHA |
|---|---|---:|---:|---:|---:|---|
| **21** | G14 기준 고정 노출 100→80%; 위험/수익비례 관계, 70% 배분으로 S7 | **+29.0408%** | 12.9329% | 56 | 45.42% | `745a37bd72e4b2745c8cd03e7b49955f376f146458164ecb4bc2b27bd88369d4` |
| **22** | G13 진입에 range-low-reclaim pulse AND 추가 → **0거래**, 비체결 decision ID 기반 S7 조건 제거 | **0.0000%** | 0% | 0 | 0% | `64b0f0076cd3c21c79115761cc37d059e9b484ef33cedd62db0243bb75b5dad2` |
| **23** | G20 70%-자본, EMA 진입 유지, 252일 모멘텀 청산 → 거래 5건·MDD 악화, SMA20 청산 S7 | **+45.4962%** | 19.3597% | 5 | 64.79% | `3f6962a630e290fd2be966ba50e8d0e71e002affbe2681707a72d5d6cce7f53c` |
| **24** | G14 `plan_vote_score>0.6` 진입 과도 제한 → **0거래**, audited non-fill decision ID와 원진입 원복 S7 | **0.0000%** | 0% | 0 | 0% | `4f2ffc4ba599148c029f0ce884c453ec1333ffac74b764ca78242fe2c7d98cde` |
| **25** | G13 + 신규 정식 등록 Schaff Trend Cycle STC<=25 청산 → **360회 과잉거래**, EMA20 청산 S7 대조 | **-40.8598%** | 41.0542% | 360 | 23.94% | `f9cfa90d430741ab18f4b60b3952de13f423ce3b5fc67acf9f345046b35eeff6` |
| **26** | G20에 STC>50 진입 추가 → **0거래**, STC 실제 출력 범위가 0~1이라는 단위 불일치 실측, 조건 제거 S7 | **0.0000%** | 0% | 0 | 0% | `f959e7d10b211efe7758b3a1e50979c9d2e3ea63292ca57f470f682d1e29a848` |
| **27** | G14에 실제 **0~1 범위 STC>0.5** 진입 확인 필터 추가, STC 0.25 민감도 S7 | **+26.2972%** | 13.8738% | 40 | 38.33% | `3b02826f47ba317dc64dd694c68621af01cb2f2eafe35b73119308df232d4514` |

### 명시적으로 거절한 후보

- G21: 부모 StrategyIR에 정의되지 않은 `dual_sma_trend_50` 청산 alias → `INTENT_MUTATION_INVALID` 사전 거절.
- G22: 이미 무의미한 SMA20-positive 진입 확인 → `UNCHANGED_CANONICAL_FILLS` 사전 거절.
- G24: 4% stop 단독 변경으로 실제 entry/exit/regime 실행신호 변화 없음 → `DUPLICATE_EFFECTIVE_INHERITED_SIGNALS` 사전 거절.
- G26: EMA20 음수 청산 AND STC<=25 조합도 실제 fill에 변화 없음 → `UNCHANGED_CANONICAL_FILLS` 사전 거절.
- 거절 사례는 **세대 미계수**. 유효 승인 7세대 G21~G27만 추가.

## 확인한 핵심 결함/연구 학습

**G25/G26 STC 단위 불일치:** 직접 확인한 canonical audited `stc_cycle`의 대표값은 `0.0714`, `0.2857`, `0.5`, `1.0`. GPT가 통상적 oscillator **0~100** 척도로 `STC<=25` 청산 및 `STC>50` 진입을 구상해 각각 **청산 과다/진입 불능**. 이는 시장 예측력 실패가 아니라 **FeatureRef 컴파일 결과의 단위·정규화 메타데이터가 GPT의 전략 작성 컨텍스트에 충분히 표현되지 않은 인터페이스 취약점**. G27 올바른 0.5 threshold로 40거래를 실제 회복했지만 G14 대비 수익률도 하락. **다음 연구 품질 개선에서 feature value-domain, unit, normalizer를 구조화하고 0거래 후보는 counted 이전에 가급적 검증/재설계**하도록 해야 한다. 단, 사용자 변경 승인 없이 기존 S7 품질 게이트 완화/원장 소급변경은 금지.

G22/G24/G26은 **0거래이지만**, 각각 실제 비체결 decision ID 기반 진단 + 유의미한 실제 체결 회복 S7 실험을 통과하여 정식 원장에는 남음. 이는 실제 무거래 백테스트를 묘사한 것이며 경제적 성공/투자 가능 전략이라는 뜻이 아니다. 7개 중 3개가 거래 0건인 것은 미래 자동 루프의 **유효 세대 예산 낭비 문제**를 보여준다.

G23 장기 청산의 높은 개발 수익률은 5거래 표본이므로 부모 적격성/일반화 입증이 아니다. G25 폭락은 비용상 오버트레이딩의 직접 실측 사례다. 모든 비교는 **같은 QQQ 2020~2025 RAW 비-PIT DEVELOPMENT 1,508 bars**를 반복 사용했다. 동기간 QQQ 단순보유 +187.77%보다 수익률 낮음. 독립 OOS, PIT, live economics, causal proof 모두 **NOT ESTABLISHED**.

## 무결성·서비스 확인

`AcademicMCPCheckpointService.get`에 기반하여 **정식 27/100, 27개 고유 StrategyIR hash, 27개 연속 previous_evidence SHA, S7 approved 27, inherited 세대 14** 검증 PASS. SQLite `cycles.sqlite`, `gateway.sqlite`, `catalog-s6-v2.sqlite` **PRAGMA quick_check=ok**. `orders_enabled=False`, `independent_oos_approved=False`. 과거 68/100 cohort 분리 유지.

대시보드 HTTP:
- `http://127.0.0.1:8082/api/status` HTTP200, **27/100, proof_chain_ok=true**.
- `http://127.0.0.1:8082/api/status?cohort=prior_mcp` HTTP200, **68/100, proof_chain_ok=true**.
- **`http://127.0.0.1:8081/api/status` RemoteDisconnected** (이번 보고의 운영 미해결, 재부팅·배포·원본 URL 변경 미실행).

## 다음 고정 단계

실제 무인 호스트/인증 제공자 여전히 미연결(별도 Work 실행도 시작되지 않음). 직접 ChatGPT 대화도구로 연구 7세대 실제 추가했고, **G28~G100 73세대는 NOT RUN**. GPT 호출 독립 signed proof/P4-2 미존재. 기존 Git 브랜치/중앙 원장 저장 및 대시보드 8081 운영 복구, STC units/zero-trade precommit 연구품질 개선 순으로 처리하되 주된 고정 목표는 T4 실제 GPT 100세대 완결, 이후 V01~V04 봉인 PIT/OOS, V06 paper-only, V07 독립 GO/NO-GO다.
