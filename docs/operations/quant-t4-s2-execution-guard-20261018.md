# Quant T4 S2 — 실제 체결 동일 후보 차단

검증일 2026-10-18 KST. 기능 브랜치 `feat/t4-s2-effective-fills-g181-20261018`; 운영 MCP 기존 주소·OAuth·32개 도구·주문 비활성 정책은 변경하지 않는다.

## 문제·해결

기존 `DUPLICATE_INHERITED_STRATEGY`는 StrategyIR 해시·과거 세대 해시가 같은 경우만 차단해, 조건을 아주 조금 바꿔 해시가 달라도 실제 canonical 매매·수량·수수료·비용 반영 자산곡선이 동일한 실험을 허용할 수 있었다. 지난 P3-1 3경로 비교에서 국소 변화 IR은 달랐지만 실제 체결과 자산곡선이 부모와 같았다. 이러한 무효 후보가 G181 이후 세대 예산을 소비하지 않도록 **S2 계획 접수 시점**에 검증한다.

신규 `research/llm/s2_execution_preflight.py`는 이미 검증된 상속 자식의 `audit_inherited_decisions().evaluation`과 해당 부모의 `evaluate_compiled_development()`를 동일 개발 데이터/초기 현금·정식 체결 비용으로 재평가한다. StrategyIR 해시에서 파생된 audit fill ID가 아닌 **실제 `Trade` 레코드(체결 시점·방향·수량·가격·비용) 전체**와 동일한 전체 자산곡선인지 비교한다. 정확히 같으면 `UNCHANGED_CANONICAL_FILLS` 오류를 발생시키고 **checkpoint token과 세대 수를 소비하지 않는다.** 체결·자산 곡선의 동일 판정이 서로 모순이면 fail-closed.

실제 다른 체결이 있으면 `VERIFIED_DIFFERENT_COSTED_FILLS` 상태, 부모·자식 StrategyIR 해시, 데이터 해시, 두 체결 SHA, fill 개수, 개발 데이터 전용·인과성 미확립·실거래/OOS 미승인 표시를 작은 메타데이터로 기록한다. 이 결과는 기존 진단 context hash를 재계산하지 않고 확인된 임시 pending에 결속하여 MCP의 진단 컨텍스트로 전달된다. 과거 세대 원본 SHA·S7 signed context는 수정하지 않는다.

엄격 검사 플래그는 제출 receipt의 해시에도 포함된다. 이미 수락된 일반 계획을 사후 `strict=true`로 재전송해서 검사 통과처럼 위장할 수 없고, 동일한 strict 요청 재전송만 idempotent 응답을 반환한다.

기존 MCP `submit_algorithm_plan`에 **선택형** `require_execution_change: boolean`(기본 false)을 추가하여 기존 호출과의 역호환성을 보존한다. 상속 부모가 없는 첫 AlgorithmPlan에서 true를 사용하면 지원 불가 오류로 거절한다. 검사 옵션은 실제 사용하는 호출에서 명시적으로 true로 지정해야 한다. 이 기능은 trade 변경을 증명할 뿐 수익 증가나 학술적 독립성을 보장하지 않는다.

## 테스트

- IR만 다른 부모와 자식의 실제 체결이 동일한 경우 검사 거절.
- 실제 체결이 다른 경우 비용·데이터·부모·자식 SHA가 묶인 통과 결과.
- 이전 읽기 전용 감사지원 G33을 임시 SQLite로 복원하여 `submit_plan(strict=true)`의 무효 후보가 토큰·세대 수·원장 해시를 변경하지 않는지 확인. 다른 후보는 진단 context에 실행 사전 검사 증거를 제공.
- 전체 G33 → G34 strict-plan/S2/S7 기록·재조회 테스트로 이전 복구·증거 체인과의 호환성 검사.
- MCP 32개 도구와 선택형 새 필드의 역호환성 검사.
- 단위+MCP+계승+복구+OAuth+거버넌스 관련 **57 PASS**, Ruff 전체 PASS, Mypy 전체 **275소스 PASS**.
- 최초 전수 실행 중 feature worktree `.venv` 링크 누락으로 MCP STDIO launcher 테스트 환경 실패 1건이 확인돼 해당 작업 폴더에만 무시되는 기존 venv 심볼릭 링크를 연결. 개별 launcher 테스트 통과 후 정규화된 환경에서 **처음부터 전체 T3 재실행 중**.
- 전체 T3 Pytest **실행 중**. 전수 통과와 PIN/실행기 보호 검사 전 운영으로 전환하지 않는다.

## 범위 제한

동일한 parent-child canonical fill trace만 검사한다. 다른 과거 부모/시장·새 기초 데이터에 대한 중복 여부, 미묘한 비경제적 신호 차이, 장기/독립 OOS, PIT, 실제 수익/자동 무인 LLM 운영은 보증하지 않는다. 이 기능을 이용해 G181을 실제 진행할 경우 `submit_algorithm_plan(require_execution_change=true)`로 호출하고, 그 증거를 보고해 정식 세대 수와 기존 180개 SHA가 보존되는지 확인해야 한다.

## 실제 G180 데이터 재검증으로 확인한 낭비

완료된 G180의 원본은 수정하지 않고 RO SQLite 75/80세대 실제 자료에서 부모를 정확히 복원했다. G75의 기존 상속 IR에 그때 검증된 S7 `plan_vote_score<=0.72`를 적용하여 **SHA `21827b9c...`가 G180의 기록된 부모 해시와 일치**함을 확인했다. G180 실제 StrategyIR+감사 SHA `895aae32...`/검증 trace를 동일 개발 QQQ 데이터에서 재생한 뒤 신규 preflight를 적용하니 **`UNCHANGED_CANONICAL_FILLS`** 로 거절됐다. 즉, G180의 표기된 `parkinson_variance 0.000088 → 0.000096` 임계값 수정은 독립 전략 코드 SHA만 바꿨고, 실제 실행 주문(수량·가격·비용) 및 전체 자산곡선은 부모와 같았다. 수익률 +63.48%를 새로운 발견으로 세어서는 안 된다. 이는 향후 본 기능의 개발 효용을 보여주는 사례이지 미래 수익 증명은 아니다.
