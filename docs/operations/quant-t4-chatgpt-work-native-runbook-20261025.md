# T4-P0 — 기존 ChatGPT Work + 연결된 Moon MCP 자율 연구 실행 경로

- 작성: 2026-10-25 KST
- 단계: **T4** (Q02·Q06·Q07·Q08·Q09·Q15·Q17·Q20)
- 상태: **NATIVE HOST PATH IDENTIFIED, WORK-TO-MOON CONNECTION NOT YET VERIFIED, 80 GPT GENERATIONS NOT RUN**
- 관련 원장: [T4 P1 상태 제어기](quant-t4-p0-p1-continuous-checkpoint-20261024.md), [P0 호스트 사전 검사](quant-t4-p0-host-readiness-20261024.md), [모델 API 변경 제안 — 미승인](../decisions/2026-10-24-t4-model-host-options-proposed.md)

## 1. 실제 병목 및 대안

기존 `GPTIntentProvider`는 외부 ChatGPT가 작성한 계획을 전달할 뿐 호스트로서 모델을 자체 반복 호출하지 않는다. 이 때문에 P1 Moon Python 제어기는 `TEST_ONLY` 외에 현재 실제 자율 실행을 하지 못한다. 이를 무리하게 우회해 `EXTERNAL_MCP_UNVERIFIED` 콜백을 운영에 제출하는 경로는 커밋 `4d3262c`에서 차단되었다.

**별도의 실행 위치가 있다:** ChatGPT **Work**는 GPT가 사용자 목표를 장시간 수행하며 연결된 플러그인을 호출하는 제품 실행 호스트이다. OpenAI 공식 도움말에 따르면 Work는 클라우드 컴퓨터/연결 앱·플러그인으로 여러 단계 과업을 수행하며 사용자가 대화를 떠나도 계속할 수 있고, 입력이나 권한 승인이 필요하면 일시 중단한다.

- https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex
- https://help.openai.com/en/articles/20001280-using-cloud-browser-in-chatgpt
- https://developers.openai.com/training/walkthroughs/getting-started

**허용된 기존 연결을 유지하는 우선 경로 A:** 별도 서버 API 키/LLM 계정을 만들지 않고, ChatGPT Work 자체가 GPT 작성자가 되어 **이미 연결된 Moon MCP 플러그인**을 반복 호출한다. 이 경우 Python 서버에 GPU/모델 SDK를 내장하거나 P1 `EXTERNAL_MCP_UNVERIFIED` 안전 장치를 해제할 필요가 없다. *Work가 기존 사용자 Moon 플러그인을 실제로 사용할 수 있는지, 작업 상한 없이 G21~G100까지 이어갈 수 있는지는 이 대화에서 확인되지 않았고 Work에서 입증해야 한다.* Work의 계속 실행도 서비스 사용 한도·권한·입력 요청에 의해 멈출 수 있다.

## 2. 실제 현재 P5 상태 — 2026-10-25 확인

- ROOT: `/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021`
- STATE: `/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024`
- SESSION: `3b44e05e52b3497db6fa035681ed0a5d`
- 완료/목표: **20 / 100**, `AWAITING_PLAN` **G21**.
- 마지막 counted evidence: `f514f9c2d907d0fc27b9e0a906bd91e4ebf4f44fb16a866dbb826264edf48316`.
- G21 `model_context.output_contract = InheritedResearchIntent`, `counted_parent_inheritance_ready=True`.
- `orders_enabled=False`, `independent_oos_approved=False`.
- 독립 provider 호출 서명 영수증/P4-2 enrolled **없음**. 따라서 ChatGPT Work에서 직접 생성하더라도 *외부 공급자 서명으로 검증된 provenance*라고 주장하면 안 된다.
- **운영 기본 Quant MCP / 기존 68세대 원장과 분리된 P5 STATE를 명시적으로 지정한다.** `mcp__Quant_AutoResearch__get_algorithm_research`의 기본 state가 P5와 같다고 추정하지 않는다. Work가 `@moon`의 명시적 파일/실행 도구로 이 경로에 접근할 수 있어야 한다.

## 3. Work에 전달할 단일 연속 실행 지침

아래는 **Work 작업 지침서**다. 이 저장소에서 실행한 실제 모델 호출이 아니다.

> `@moon` 연결을 이용해 Quant AutoResearch의 기존 격리 P5 세션 `3b44e05e52b3497db6fa035681ed0a5d`을 **G21부터 G100까지** 진행하라. 운영 Quant MCP 기본 세션/기존 68세대 및 P4 원장은 변경하지 말라.
>
> 사용되는 실제 ROOT는 `/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021`, STATE는 `/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024`이다. `AcademicMCPCheckpointService(project_root=ROOT,state_dir=STATE,parent_portfolio_v2=True,generalization_parent_v1=True,p4_quality_gate_v1=True,p4_s7_quality_v1=True)` 및 저장된 원본 session id로 매 단계 `get` 상태를 확인하라.
>
> **각 세대의 모델 판단은 Work의 GPT가 직접 작성해야 한다**. `AWAITING_PLAN`에서는 제공된 `model_context`와 부모·실제 이전 증거를 읽어 `output_contract`에 맞는 AlgorithmPlan 또는 `InheritedResearchIntent`를 새로 설계하고 `submit_plan`으로 제출하라. 검증된 부모 계승일 때 `require_execution_change=True`를 적용하고, G29 이후 신규 실험은 선택형 `require_trade_activity=True`도 사용해 비용 반영 청산 거래가 0건이면 같은 계획 토큰에서 수정하라. 신규 등록 지표의 임계치는 `model_context.feature_unit_guidance`의 검증된 계산기 출력 단위를 우선 확인하며, 범위를 확인하지 못한 지표는 임의로 0~100을 가정하지 말라. `AWAITING_DIAGNOSIS`에서는 그 세대의 비용후 백테스트 실측 거래 ID, 손실/성과, 당시 신호와 한계를 바탕으로 반증 가능한 기전·대안·S7 실험계획을 **GPT가 분석·작성**하여 `submit_diagnosis`하라.
>
> **승인된 evidence commit을 확인해야만 한 세대로 집계**하고 바로 다음 checkpoint를 읽어 이어가라. 시도 횟수나 임의 파라미터 루프를 GPT 세대라고 계산하지 말라. 단계별 모델 컨텍스트에서 지원하지 않는 지표/metric, 중복 체결, 변형 효과가 없는 제출은 동일 토큰과 거절 피드백으로 재설계하라. 실패 가설과 효과 없는 S7의 원인을 다음 계획에 전달하고 우수 부모 자동 계승 정책은 그대로 유지하라.
>
> **10세대마다 중단하지 말라.** 실제 기록된 `completed_generations=100` 또는 재시도/사용 한도/권한 오류 등 해결할 수 없는 외부 조건에서만 종료하라. Work 세션 또는 호출 한도 때문에 중단될 경우 **실제 완료 수, 정확한 phase, 마지막 evidence hash, 남은 수, 중단 사유**를 명시하라. 작업이 이미 다른 실행자에 의해 변경됐다면 합병/재작성하지 말고 중지하라.
>
> 원래 OAuth·고정 URL·실거래 비활성·데이터/백테스트 코어·봉인 OOS를 절대 변경하지 말고, 외부 API를 새로 설치·과금·연결하지 말라. 연구는 2020~2025 QQQ 비-PIT 개발구간이며 2026 독립 검증 또는 수익성 입증으로 표시하지 말라. `P4-2` 독립 provider signed provenance가 없다면 이 사실을 명시하라. 종료 후 Moon 원장 감사, 대시보드 검증, 중앙 진행 문서·Git 백업 및 실패/미완료 세대 보고를 수행하라.

## 4. 워크플로 수락 테스트 (아직 실행 안 함)

1. ChatGPT **Work**에서 사용자가 이미 연결한 `@moon` 플러그인이 보이는지 확인. 없다면 별도 OAuth를 새로 등록하지 말고 중지.
2. Work의 첫 단계는 **P5 상태 읽기**: 정확히 20/100, G21 `AWAITING_PLAN`, 마지막 evidence hash 일치. 잘못된 기본 운영 세션(68/100)과 섞이면 즉시 중지.
3. Work가 **자체 GPT 판단으로** 1세대 Plan→실측 S2→손실 기반 진단/S7→counted evidence 완결(G21)을 성공시키는지 검증.
4. 동일 Work 작업에서 후속 여러 세대를 반복 호출하며 G22·G23으로 계속하는지 확인. 단기 성공으로 이미 100세대라고 표시하지 않음.
5. 대화 앱 밖에서도 Work 작업이 계속되는지는 **실제 동일 task ID·원장 카운트**로 확인. 사용자의 승인 필요/플러그인 정책/용량제한을 포함한 Work 제한이 발생하면 보존하고 중지.
6. 전체 결과의 독립 provider 서명 영수증/PIT-OOS 결여, 모델 호출 원장과 원본 counted 증거의 차이를 보고.

## 5. 현재 결정

- 별도 API 경로(B)는 **여전히 사용자 명시 승인 전 미허용**. ChatGPT Work 경로(A)는 사용자 승인된 기본 ChatGPT+MCP를 변경하지 않는 시도이며 이 문서에서 1순위.
- **이 문서는 Work 작업을 새로 만든 것이 아니며 실제 G21을 실행하지 않았다.** Moon 코드 변경/프로세스/기존 OAuth 재설정 없음.
- 작업 시작은 **사용자가 ChatGPT Work를 선택**하고 동일 프로젝트·Moon 연결로 이 지침을 보내는 것. Moon에서는 Work의 호스트 기능을 대신 시작할 수 없다.
