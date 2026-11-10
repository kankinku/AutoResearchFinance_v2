# Track2 시장 특수 이벤트 조기 탐지 — 독립 실험 명세

**시점:** 2026-11-10 KST · **단계:** [15/16] Task 14
**상태:** SYNTHETIC_PROTOTYPE_ONLY / REAL_MARKET_BLOCKED / NOT_RELEASED
**범위 기록:** 2026-11-10 Track2 분리 연구 착수 ADR

## 원본 V3 계획 확보

16단계 계획이 참조한 v3-track2-event-detection-20261027.md 파일은 main 및 14단계 통합 브랜치에는 없었으나 **원격 research/v3-event-detection 브랜치의 기존 커밋 950bd49에서 발견해 원문을 보존했다**. 해당 계획을 기준으로 T2-01~T2-04를 읽고, 이 문서는 검증 가능한 초기 구현의 정보 경계와 미달사항을 별도로 명시한다. 실제 가격/OOS·Champion 후보/확률 보정이 완료됐다는 뜻이 아니다.

## 시장 이벤트 레이블과 경고 시점

모든 임계값, 관측 창, 사전 리드타임, 경고 횟수, 양성 사건 최소 수는 **실험 전 승인·고정해야 할 연구 변수**다. 테스트의 예시 수치를 사용자 확정 기준으로 해석하지 않는다.

| 사건 유형 | 사후 확인되는 최초 이벤트 | 후보 사전 위험 점수 |
|---|---|---|
| 폭락 CRASH | 직전 w봉 수익률이 마이너스 임계폭 이하로 최초 진입 | 승인 등록 지표 QQQ 20봉 수익률의 음수 부분 |
| 반등 REBOUND | 앞선 w봉 하락 이후, 직전 w봉 반등폭이 양의 임계치 이상 첫 진입 | 같은 등록 지표의 음수 부분. 미래 반등을 아는 신호가 아니다 |
| 변동성 급등 VOL_SPIKE | 최근 w개 일간 수익률 표준편차가 이전 w개 표준편차의 지정 배수 이상으로 첫 진입. 전 기간 표준편차 0이면 레이블 불가 | 등록 QQQ 20봉 수익률 절대값. 전문 변동성 예측기가 아닌 단순 기준 점수 |

- 경고는 **해당 봉이 닫힌 후** 생성된다. 실제 사건 첫 관측은 경고 시점에서 최소 min_lead_bars 이후, 최대 max_lead_bars 이내여야 한다. 두 기간이 겹치면 같은 사건은 최초로 부여한 경고에 한 번만 매칭.
- 사후 레이블은 평가에서만 사용한다. 경고 코드가 호출할 수 있는 데이터는 **경고 봉까지의 등록 지표**만. 미래 데이터를 알았을 때 점수나 그 경고 원장이 바뀌면 FAIL.
- 마지막 max_lead_bars개 봉은 미관측 결과를 정답으로 평가하지 않고 right-censor.
- 연도별 경고 횟수·점수 임계치·쿨다운은 **사전 고정**. 연도 종료 후 가장 높은 경고를 고르지 않고 발생 순서대로 예산 차감.
- 경고 원장에는 **그 시점까지의 날짜·가격 접두 해시**와 정책 해시만. 전체 가격 해시/사후 정답·평가성공 여부는 별도 사후 보고서에만 기록.

## 평가·비교 기준

**필수 수치:** 사건 발생 기저빈도(평가 가능한 시점별 양성 비율), 경고 리드타임(평균·중앙 및 사건별 봉 수), 경고 예산, 이벤트 단위 recall, warning precision, PR-AUC(tie-group Average Precision), **252개 평가 가능 봉당 거짓 경고 수**(연간 환산을 위한 *근사치*), 누적 신호 반복/경고 쿨다운. **Brier/확률 보정과 purged walk-forward**는 실제 예측 확률 및 독립 실데이터가 없어 미검증이며, 반환값은 NOT_CALIBRATED와 purged_walk_forward_validated=false. 훈련-평가 경계 사이 사건 리드타임만큼 embargo를 요구하는 사전 조건은 단위 테스트.

**기준선:** 무경고(0건)와 항상경고(같은 연도별 경고 예산·같은 쿨다운) 비교. PR-AUC는 전체 평가 가능 기회의 점수 순위로 계산한 별도 진단 값이며, 실제 예산 하의 경고 precision·recall을 대체하지 않는다.

사건이 연구 설정의 min_confirmed_events 미만이거나 양성·음성 구분 기회가 부족하면 평가를 **BLOCKED_INSUFFICIENT_EVENTS**로 표시하고 성능·승격·실거래를 주장하지 않는다. 임계값을 결과를 본 뒤 바꿀 경우 새 시험으로 취급해야 한다.

## 구현·분리·데이터 전제

- 기존 원본 계획의 T2-01 사건 레이블·T2-02 빈도 기준·T2-03 PR-AUC/경고 예산·T2-04 기록 형식을 따라 별도 설계했으나, **Champion 선정과 확률 보정, 실제 purged walk-forward는 아직 구현/실증하지 않았다**.
- 기존 FeatureRegistry에 이미 등록된 qqq_returns(등록된 QQQ close returns, 20봉) 및 계산기만 사용. 새 피처 등록·연구 엔진 StrategyIR·세대 커밋·백테스터 변경 없음.
- 독립 코드 파일 research/indicator_engine/track2_event_detection.py, 테스트 tests/research/test_track2_event_detection.py. **core, evaluation, application, integrations, runtime, 기존 MCP 32도구, 주문 권한 변경 없음**.
- 데이터 구역은 DEVELOPMENT만 허용. SEALED_OOS/VALIDATION 요청은 거부. 경고 보고서에 오프라인 사후 레이블, PIT 미확인, 인과성 불성립, Track1 미연결, 거래 비허가를 명시.
- 실제 QQQ 신규 원본·원시 게시 시각·PIT 수정이력·배당/분할·실 현금/유동성·독립 빈도·사전 고정 프로토콜·외부 독립 기간이 현재 Moon에 없음. 실제 이벤트 빈도, PR-AUC, 예측 리드타임의 의미 있는 추정, 수익성, 희귀 사건 검증은 **NOT_RUN**. 아래 테스트는 합성 fixture 전용.
- Track3 봉인 OOS 조회·Track1 전략 선택/LLM 학습·실주문·백테스트 성능 승격은 각각 별도 승인 전 **금지**. [14/16] 본체 V07 NO-GO 상태를 유지. 이 분리 브랜치의 코드 자동 병합 금지.

## 로컬 합성 테스트 명령

    python -m pytest -q -p no:cacheprovider tests/research/test_track2_event_detection.py
    ruff check research/indicator_engine/track2_event_detection.py tests/research/test_track2_event_detection.py
    python -m mypy --follow-imports=silent research/indicator_engine/track2_event_detection.py

**완료 판정:** 실 데이터 기반 성능 **판단 보류**, 연구용 인과 차단 및 평가 계약 **테스트 가능**.
