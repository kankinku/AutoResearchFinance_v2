# Quant AutoResearch — P0-3 GPT 연구 판단 출처·실측 근거 연결

기준: 2026-10-19 KST · `SCOPE_LOCKED_20Q` 유지 · T4 GPT MCP 원형 유지 · 운영 미배포

## 1. 기존 개선 대비 원인 및 중복 금지

P0-2A의 `verified_lineage_bootstrap`, P0-2B의 격리 G25→G54 StrategyIR 계승 및 기존 `loss_attribution`, `experiment_learning`, `cross_generation_memory`, `economic_feedback`는 실제 측정 데이터를 GPT에게 제공한다. 그러나 `submit_algorithm_plan` 및 `submit_algorithm_diagnosis`는 **어떤 S7 가설의 어떤 실제 결과를 근거로 해당 결정을 했는지** 기록하지 않았다. 그 결과 앞선 50세대는 계획·진단·S7 증거가 있어도 템플릿 반복을 독립 GPT 연구라고 부정확하게 판단할 여지가 있었다.

**본 작업은 모델 오케스트레이터/백테스터/부모 선택기 재구현이 아니다.** MCP 제출 메타데이터를 소형 읽기-검증 사이드카로 남긴다. 핵심 기존 QQQ/StrategyIR/S7/수수료/원장 코드 변경 없음.

## 2. 구현: 외부 GPT 주장과 근거 검증 분리

- `research/llm/decision_provenance.py`: 호출자가 선택한 `declared_origin`(`CHATGPT_CLIENT`, `SCRIPTED`, `HUMAN`, `UNSPECIFIED`), 자기표현적인 결정 요약, 기각한 대안, **과거에 실제 측정된 S7 report hash·가설 ID·원본 status**, 진단 시 현재 감사된 거래·결정 ID를 검증. 지난 실험을 참조해야 하는 2세대 이상에서는 참조 1건 이상 필수. 미래 세대·허위 해시·허위 성과·가짜 거래 ID는 제출 전 거부. 결정 요약은 외부에 공유 가능한 이유만 기록하며, 숨겨진 모델 내부 추론(COT)은 수집하지 않는다.
- 기존 `AcademicMCPCheckpointService`: `decision_evidence` 및 `require_decision_evidence` 옵션을 계획·진단 도구에 추가(기본 OFF, 레거시 호출 유지). 엄격 모드에서 근거가 없으면 체크포인트 소비 없이 거부. 채택된 제출 payload 해시와 이전 세대 증거 해시를 `research_decision_receipts` gateway 사이드카에 저장하고, 읽기 때 해시·세션·세대·단계 일관성 검증. 계획·진단이 정상 완료되기 전에는 성공한 근거로 기록하지 않는다. 과거 불변 세대 증거는 수정하지 않는다.
- 기존 GPT MCP 도구 32개 이름 및 URL/OAuth 불변. 각 제출 도구의 JSON schema에 **선택형** metadata 필드를 노출. `get_algorithm_research`가 최근 최대 10개 짧은 판단·근거를 반환하고, 다음 계획 문맥에는 `prior_decision_provenance`를 추가한다.
- **인증 경계:** 해당 도구는 모델의 실제 정체, 추론 경로, 독립성, 적응적 성능을 알 수 없다. `CHATGPT_CLIENT`를 제출하더라도 **`origin_authenticity=UNVERIFIED_CLIENT_CLAIM`, `real_model_connection_verified=false`, `model_autonomy_verified=false`** 그대로다. 현재 완성한 것은 근거-인용 무결성 검사이지 GPT 실제 자율 학습 인증이 아니다. SQLite 해시는 서명이 아니므로 악의적 DB 관리자에 대한 증명도 아니다.
- `require_decision_evidence`를 전체 호출에 즉시 강제하지 않는다. 과거 53/100 연구 세션, 운영 체크포인트·MCP 인증을 훼손하지 않고 신규 엄격 연구 검증에서 명시적으로 활성화한다.

## 3. 확인해야 하는 실패 및 성공 수락 조건

1. 근거가 없는 엄격 모드·미측정 가설·틀린 S7 status·다른 S7 report 해시·미래 세대·가짜 거래 ID·모델 출처 스스로 인증 주장 모두 거절.
2. 정상 GPT-클라이언트 주장도 source origin은 **UNVERIFIED**, 측정 근거 링크만 확인. `SCRIPTED`는 SCRIPTED로 남음. 미인증 모델 결과를 연구 성공으로 계산하지 않음.
3. 기존 ScriptedResearcher로 하는 2세대 새 계약 통합테스트에서 엄격 plan/diagnosis 둘 다 저장, 동일 checkpoint 재전송 시 idempotent, 서로 다른 payload는 충돌 거절, sidecar 변조 시 조회 실패. 기존 레거시 계획·진단은 정상 진행.
4. 기존 53세대 SQLite 격리 복제본의 G25→G54 부모 계승 테스트에도 엄격 근거 기록을 추가하고, inherited S2 체결변화 및 반증 S7을 보존. 실제 운영 세대 53/100, parent selection 0, successor lineage 0, orders OFF 유지.
5. 동일예산 GPT vs random vs local 통제와 GPT가 추론 과정을 자유롭게 선택하여 계획을 실제 수정하는지의 장기 검증은 **P0-4/P0-5**에서 별도 평가한다. 별도 모델 API 사용·실거래·봉인 OOS 풀기는 승인하지 않았다.

## 4. 운영 경계 및 다음 작업

이 구현은 별도 `feat/quant-t4-p0-3-evidence-20261019` 브랜치에만 저장한다. 운영 고정 소스 `54a515f`, 기존 MCP URL/OAuth 및 연구 원장은 수정하지 않는다. 새 도구 스키마를 실제 운영에서 사용하려면 나중에 전체 회귀·MCP 연결 계약 검사 후 별도 배포 승인 및 비교가 필요하다. 이번 단계에서 새 47세대는 실행하지 않는다.

다음 선행 조건: P0-3의 실측 링크 저장 기능을 기존 GPT 의사결정 흐름에서 실제 이용하는 작은 세대 테스트와 **SCRIPTED vs GPT의 증명 가능한 구분**을 실시해야 한다. 서버에서 못 읽는 모델 identity는 `UNVERIFIED`로 유지한다. 그 후 P0-4 경제적 개선 분리 및 P0-5 동예산 비교를 진행한다.

## 5. 실제 이번 개발 검증 결과

- 새로운 strict/legacy 진단 근거 통합테스트 **3 PASS**; 기존 G25 S7→손자→검증 부모→격리 counted G54 S2/S7 경로에서 `SCRIPTED` 증거로 plan/diagnosis receipts **2건을 추가하고 1 PASS**. 진행·부정 예상 결과는 원본 계산과 동일. 해당 GPT 모델의 실제 정체/추론 여부는 `UNVERIFIED`.
- 연구 세션·계승·MCP 스키마·범위잠금 관련 회귀 **44 PASS / 0 FAIL (101.39초)**. 전체 저장소 Ruff PASS, Mypy **278 source files PASS**. 전체 Pytest를 새로 실행하지 않았으므로 전체 통과 판정 금지.
- 거절 검증: strict metadata 누락, S7 실제 상태와 다른 관찰 주장, 가짜 현재 거래 ID, 변조된 receipts, 모델 출처를 verified로 가장할 수 없는 반환값, 레거시 도구 호출 이전과 동일한 동작. 기존 32개 도구 이름 유지.
- 원본 운영 실연구는 **53/100, sidecar 근거 기록 0(아직 운영 미배포)**. 서버를 재시작하거나 추가 GPT 연구 세대를 실행하지 않음.
