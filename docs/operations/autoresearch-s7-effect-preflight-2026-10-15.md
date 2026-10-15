# S7 유효 실험 사전검사 — 2026-10-15

## 배경과 명시적 근거

- [10세대 GPT vs 무작위 비교](autoresearch-gpt-vs-random-10gen-2026-10-15.md)에서 GPT의 S7 실험 10회 중 6회가 거래·수익에 관측된 효과가 없었고, 대부분 `REMOVE_REGIME_FILTER`로 발생한 무효 검증에 가까웠다.
- 기존 학술 AlgorithmPlan 컴파일러에서 `plan_regime=0`이면 `plan_entry=0`이다. 원형 전략의 진입 규칙은 `plan_entry > 0.5`, 바깥 단일 필터는 `plan_regime > 0.5`다. 따라서 **이 원형을 바꾸지 않은 상태에서 바깥 필터만 삭제**해도 새로 거래할 수 있는 기회가 생기지 않는다.
- 이 결론은 과거 수익률을 보고 추측한 것이 아니라 컴파일러의 이진 논리에서 증명되는 **좁은 정적 무효 조건**이다. 모든 변경 전략·모든 시장·모든 동적 조건의 무효를 예측할 수 있다는 의미는 아니다.

## 구현

1. `research/indicator_engine/experiment_preflight.py`에 정적 무효 규칙 검사 `static_noop_hypotheses`와 전략 변경 설명을 추가했다. 판정은 원형 엔트리/청산 규칙, 단일 바깥 필터, 단일 `REMOVE_REGIME_FILTER(regime_filters.0)`가 **모두** 일치할 때만 한다. 모호하면 거부하지 않는다.
2. `submit_algorithm_diagnosis`에 **선택형** `require_signal_change=true`를 도입했다. 검증된 정적 무효 실험이면 해당 세대의 원장/체크포인트를 커밋하기 전에 거부하고 **동일한 토큰으로 수정한 DiagnosisResponse 재제출**을 허용한다. 기본값 `false`는 과거 사용자/세션/SDK의 기존 동작을 유지한다. 비불리언 값은 거부한다.
3. 새로운 `get_algorithm_research` `AWAITING_DIAGNOSIS` 응답의 `model_context.experiment_quality_guidance`는 무효 필터를 설명하고 `plan_vote_score`를 활용한 구조 변경 **예시**를 제시한다. 이 새 UX 보조 필드는 검증된 원래 `context_hash` 검사가 끝난 뒤에만 덧붙이며 이미 저장된 진단·전략 컨텍스트 해시/토큰/원장은 수정하지 않는다.
4. 기존 MCP `submit_algorithm_diagnosis` 스키마에 선택적 불리언 속성 하나만 추가했다. MCP 툴 개수/URL/OAuth/실거래 권한은 그대로 유지한다. **클라이언트의 오래된 18개 도구 캐시 문제를 서버 업데이트만으로 고쳤다고 주장하지 않는다.**

## 테스트 및 실제 연구 자료 대조

- 합성 시장 통합 검증: `require_signal_change=true`인 확정 무효 가설이 세대 0/미소비 토큰을 유지한 채 거부됨; 2개 `REPLACE_RULE`(진입 `plan_vote_score > 0.8`, 청산 `plan_vote_score <= 0.8`)로 수정하여 동일 토큰 제출하면 **완료 거래 2→1건**, 체결 이벤트 감소, 다음 세대 증거와 S7 실험 기록 정상 기록.
- 실제 QQQ 1,508봉 DEVELOPMENT에서 기저 GPT G7 전략에 동일한 0.8 투표 점수 진입/청산 개입을 적용: **완료 거래 24→52**, 추가 체결 이벤트 72개, 제거 17개, 수량 변경 이벤트 28개. 누적수익률은 원본 +89.897%에서 비교안 +23.149%로 감소. `predicted_direction=DECREASE`는 **DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY**로 올바르게 판정되었다.
- 실제 시장 실험은 좋은 결과가 아니라 **정보가 있는 부정 결과**다. 청산 기준까지 바꾸면 거래 횟수가 늘어날 수도 있으므로 점수 조건 강화가 저위험/저빈도 투자를 보장하지 않는다.
- 샘플 기간은 반복 사용한 개발 구간이며 as-of/PIT, 새로운 데이터 독립 검증, 다중검정 및 인과 확정은 미완료. 모델은 실전 주문을 실행하지 않는다.

## 범위 및 잔여 과제

- 이번 단계의 preflight는 *확실한 한 종류의 무효 변경*만 안전하게 차단한다. 강제로 생성된 효과나 미래 수익률을 예측하지 않는다.
- `require_signal_change` 기본값은 호환성 때문에 `false`; 앞으로 인증된 MCP 연구 클라이언트가 신규 엄격 모드를 명시적으로 이용해야 효과가 발휘된다. 과거 저장된 S7 `NO_OBSERVED_EFFECT` 기록은 바꾸지 않는다.
- 필요 후속 개발: 동등 위험 비교와 신호 시간 변화를 구분하고, S7 실험 설계를 다양화하되 가격 최적화가 아니라 반증 가능한 가설 위주로 설계; 동일 예산 다중 seed/독립 OOS/PIT 검증.
- 인증된 ChatGPT 앱 32개 신규 도구 캐시는 여전히 현재 대화에서 18개만 노출. 기존 앱 새 대화/연결 도구 목록 새로고침 필요; MCP 주소 재등록 금지.
