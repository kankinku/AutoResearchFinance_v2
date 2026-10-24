# Quant AutoResearch — P4-3 S7 계약 일치 및 품질 사전검증

**작성일:** 2026-10-24 KST
**상태:** 개발 브랜치 구현·신규 opt-in 세션 통합 테스트 PASS / 실운영 미배포 / 기존 10세대 원장 완전 일치

## 승인 범위와 목표

- 원래 승인 범위: T4(S7)/Q06(LLM 진단·가설)·Q08(실패/중복 기억)·Q09(실측 지표 분리)·Q17(무의미 실험으로 세대 카운트 증가 방지)·Q20(엔진 ≠ 수익성).
- 사용자 이익: 모델이 미지원 지표를 골라 허비하는 재제출을 없애고, 실제로 실행 효과가 0인 S7 가설을 학술 세대 확정 **전** 진단한다.
- 경계: DEVELOPMENT QQQ 기존 비용·다음 봉 시가·StrategyIR·원장/S7 해시는 보존. LLM 새 API/민감 키·모델 제공자 증거·OOS/실거래·대시보드 미변경. 새 세션에서만 P4-3 정책을 명시적으로 등록한다.
- 합격 조건: typed S7 schema와 실제 엔진 지원 집합 일치, 노출률 실제 체결 기반 검증, no-effect/0-trade/undefined 수용 금지, 수정 제출 동일 체크포인트 재사용, 실패 감사 및 P4 원장 보존. 잘못된 방향으로 확인된 *유효한* 가설은 음성 연구 결과로 인정한다.

## 구현

1. **단일 metric 계약:** `research/llm/diagnostic_research.py`의 `SUPPORTED_S7_METRICS`와 실제 `controlled_experiments.SUPPORTED_CONTROLLED_METRICS`를 일치. `total_return`, `cagr`, `max_drawdown`, `sharpe`, `sortino`, `trade_count`, **`exposure`** 7개 지원. 현재 엔진에서 모든 계승 타입의 정의를 충족하지 못하는 `win_rate`·`profit_factor`는 제안 스키마에서 제외하고, 기존 API 검증 문구 `unsupported S7 metric`을 유지한다.
2. **`exposure` 구현:** 검증된 canonical buy/sell 다음 시가 체결을 원장 마켓 일봉 timestamp 순서에 적용해 각 봉 장중 포지션 보유 여부를 계산, `보유 포지션인 봉 수 / 전체 봉 수`로 측정. 균형 없는 매수/매도·자료에 없는 체결 날짜·중복체결은 거절. 일간 자본가중/레버리지 위험 노출이 아니라 **보유시간 노출률**이다. 기존 `decision_audit`의 action 기반 노출률과 기간 경계에서 미세한 차이가 있을 수 있으며, 다른 지표 및 기존 실험 성적을 소급 변경하지 않는다.
3. **실측 S7 사전 실행:** `p4_s7_quality_v1=True`인 신규 세션은 진단 토큰을 선점하거나 세대를 커밋하기 **전**에 동일 개발 데이터/비용을 이용한 원본-자식 paired 실험을 다시 실행. `NO_OBSERVED_EFFECT`, `DEGENERATE_INACTIVE_CHILD`, `METRIC_UNAVAILABLE` 결과는 모두 세대 미계수 거절. `DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY`는 가설 반증의 가치가 있으므로 남김. 동일 전략 semantic hash는 기존 `approve_diagnostic_plan`에서 중복 거절.
4. **증거·피드백:** `p4_s7_enrollments`, `p4_s7_rejections`, `p4_s7_approvals` 별도 gateway sidecar. 제출내용 자체/비밀 토큰 없이 proposal·token·dataset·context·측정된 S7 보고서 SHA, 사유, 수정 지침, 원본 counted evidence SHA를 결합. 중복 실패는 `INSERT OR IGNORE`와 읽기 비교로 단일 증거 유지. `get_algorithm_research.model_context.p4_s7_rejection_feedback`에 최근 5건 사유를 안전하게 전달. `p4_s7_quality_audit`는 승인/거절 누계와 counted source 해시를 제공. 해시 누락·사후 활성화·다운그레이드·교차 DB crash 후 approval 부재는 fail closed.
5. **격리 활성화:** 기본값 OFF. 새 연구세션에서 `QUANT_MCP_GENERALIZATION_PARENT_V1_NEW_SESSION=1`, `QUANT_MCP_P4_QUALITY_NEW_SESSION=1`, `QUANT_MCP_P4_S7_QUALITY_NEW_SESSION=1` 동시 설정. `QUANT_MCP_P4_S7_QUALITY_SESSION_ID`와 P4-1의 scoped ID가 병행 설정되면 동일 ID 필요. 별도 P4-2 외부 서명 수집기가 없으면 provider 서명 모델 연구 완료를 주장할 수 없다. 기존 운영 및 과거 P4-2 등 세션에는 활성화하지 않는다.

## 실측·회귀 증거

- 신규 격리 통합: `ScriptedResearcher` 테스트 fixture 진단이 canonical S7에서 `NO_OBSERVED_EFFECT`일 때 토큰/세대 유지, 동일 요청 다시 제출해도 거절 증거 중복 없음, 실패 원인을 프롬프트에 제공, 포지션 사이징 대조로 수정 후 정상 1세대 + S7 승인 sidecar 생성 확인. **Fixture는 실제 GPT 모델 호출 증거가 아님.**
- S7 exposure: canonical 체결 보유봉 분율과 `DIRECTION_NOT_MATCHED` 음성가설을 실제 실행으로 검증. `win_rate`/profit_factor 거절과 새 계약 일치 검사 추가.
- 과거 P4 10/10: `scripts/quant_p4_verify_10gen.py` 재실행 → 기존 `p4_verified_report.json`과 **정확히 일치**; 보고서 SHA `22024e6871c0f905b7afc182bc8837acab9bd79d9f86510a8e635efdee813aeb`. 기존 성과나 무효 S7 결과를 소급 수정/삭제하지 않았다.
- 변경 소스 Ruff PASS, 관련 모듈 Mypy PASS. 최초 확대 테스트: **93 PASS, 6 SKIP, 2 FAIL** (1건은 원래 `historical G33` 오프라인 스냅샷 누락; 1건은 새 Pydantic enum 오류 문구가 `unsupported.*metric` 사전 계약과 불일치 → 코드 수정 후 개별 **10 PASS**). 스냅샷 누락을 성공으로 재분류하지 않음.
- 최종 확대 재실행: 원래 누락된 G33 snapshot 의존 1건만 명시적으로 deselect → **94 PASS / 6 SKIP / 1 DESELECT / 0 FAIL**. 전체 repo tests, 운영 MCP 웹/대시보드 종단 및 독립 OOS/신규 GPT 100세대 **미실행**.

## 남은 과제

- **P4-4:** 장세/시장기간 독립 연구 및 봉인 전진 검증, 비용 2배·슬리피지 민감도, 이전에 이미 관찰한 2026 데이터의 EXPOSED_DIAGNOSTIC 표기. 발전한 후보 수익성 판단은 여전히 미확립.
- **P4-2 외부 의존:** 실제 provider 호출 출처 receipt 미확보; collector 서명 fixture는 실제 GPT 무인 모델 호출 아님.
- **한계:** 사전 S7 비교는 독립 OOS가 아니며, 통과한 후보를 라이브 성과로 승인하는 게이트가 아니다. 여러 서로 다른 수정이 정확히 같은 자식 체결곡선을 만드는 경우의 완전 벡터 중복 탐지는 추가 경로 필요; 현재는 부모 대비 무효와 semantic duplicate를 차단한다.
- 다음 고정 상위 로드맵 V05→T4→V01~V04→V06→V07 변경 없음. P5 100세대 확대는 아직 실행하지 않는다.
