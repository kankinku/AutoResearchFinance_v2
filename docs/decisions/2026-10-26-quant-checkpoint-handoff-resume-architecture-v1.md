# ADR — Quant AutoResearch의 호출형 세대 진화 및 영속 인계 문서 v1

- **날짜:** 2026-10-26 KST
- **단계:** `T4-CHECKPOINT-HANDOFF-ADR-20261026`
- **상태:** `ADOPT_DESIGN_FOR_EXISTING_USER_TRIGGERED_MCP; IMPLEMENTATION_NOT_DEPLOYED`
- **후속 세부 로드맵 v2:** `../plans/quant-evidence-memory-compression-and-unified-research-roadmap-v2-20261026.md` — 압축 예산, 기억 계층, F4/F5, 173 지표·V3/Pine·레거시·V05/OOS 통합 평가 게이트. **v1의 고정 8–20천 문자 목표는 v2에서 적응형 S/M/L+REPLAY 실험 가설로 구체화되며 단일 하드 한도로 확정하지 않음.**
- **관련 범위:** Q02/Q06/Q07/Q08/Q09/Q11/Q15/Q16/Q17/Q18/Q20
- **기준 브랜치:** `feat/quant-unified-mcp-20261026`, 직전 `6d69a9e`
- **사용자 요청:** 한 세대 결과/다음 실행 계획을 문서화하여 다음 SDK 또는 ChatGPT MCP 호출에서 이어서 진화하는, 지속 프로세스가 불필요한 연구 방식의 타당성·결정
- **범위 잠금:** 원본 Q01–Q20, 결정 문서, 기본 ChatGPT↔Quant MCP, 고정 URL/OAuth, protected core, 봉인 OOS, 실거래 OFF, V05→T4→V01–V04→V06→V07 순서를 변경하지 않는다. 이번 ADR은 연구 모델 제공자·권한·배포·세대 완료조건을 변경하는 승인서가 아니다.

## 결론

**조건부 채택.** `Quant의 불변 체크포인트(정본) + 해시 검증된 압축 연구 인계서(파생 캐시) + 매번 새로 진입하는 GPT 호스트 연구 턴 + 얇은 SDK 호출/예산/정지 제어기`로 설계한다.

- 이 구조는 **대화나 프로그램이 종료되어도** 세대별 연구 내용을 잃지 않도록 한다. 사용자 `다음` 또는 지원되는 GPT 호스트 새 호출이 있으면 정확한 이전 체크포인트에서 **1세대씩 진행**할 수 있다.
- 인계서/파일 자체는 모델이 아니다. **SDK의 `tools/call`만으로 새로운 GPT 추론이 자동 발생하지 않는다.** 현재 존재하는 ChatGPT가 주도하는 직접 MCP 연구 턴은 계속 사용한다. 별도 서버에서 무인 100세대를 자동 호출하는 기능은 합법적인 호스트 턴 dispatch 지원 확인 전까지 `BLOCKED_MODEL_HOST_DISPATCH`이다.
- SDK가 결과를 읽고 요약·재판단하는 *새 금융 연구 모델*이 되어선 안 된다. 기억 압축·실험 평가·다음 가설 후보의 품질 필터는 **Quant**가 담당하고, GPT는 Quant의 제약 아래 새로운 전략·원인 가설을 작성한다.
- 2026-07-28 MCP 사양은 서버→클라이언트 `sampling/createMessage`를 deprecated로 분류한다. 향후 클라이언트 지원이나 승인 없이 Sampling을 자동 GPT 턴 시작의 기반으로 도입하지 않는다. 공식 참고: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx

## 확인된 현황 (2026-10-26, 읽기만 수행)

활성 Quant MCP `get_algorithm_research`는 **68/100, AWAITING_PLAN**, `orders_enabled=false`, `independent_oos_approved=false`. 결과 직렬화 **664,081 문자**, `history` **548,966 문자**, `model_context` **113,581 문자**, 마지막 세대 이력 약 **8,147 문자**. **이 수치는 JSON 문자열 길이이며 UTF-8 바이트 수/실제 토큰 수가 아니다.**

가장 긴 모델 문맥 구성요소: `cross_generation_memory` 약 29,614 문자, `loss_attribution` 약 18,211, `experiment_learning` 약 17,084, `feature_weakness_guidance` 약 10,096, `prior_research` 약 9,183. 따라서 완전한 이력을 또 다른 Markdown에 복제하면 문맥·토큰 소비를 줄일 수 없다.

기존 `AcademicMCPCheckpointService`는 이미 `get → submit_plan → submit_diagnosis → S7 실험 보고 → checkpoint → get`, 원장 해시, 중복 제출/재개 영수증과 `cross_generation_memory`, 부모 선택 기능을 갖고 있다. 개발용 SDK는 현재 운용 중 호스트의 새 GPT 턴을 독립적으로 시작할 수 없다. `final_report`는 세대 진행 중 **null**일 수 있으므로 세대별 S7은 별도 해시 검증 실험 영수증으로 확인해야 한다.

## 데이터 계층: 원본과 인계 문서를 절대 혼동하지 않음

| 저장물 | 목적 | 진실의 원천/가변 여부 |
|---|---|---|
| Canonical `cycles.sqlite`와 `gateway.sqlite` 증거, `experiment_reports`, parent/lineage receipts | 거래·S2/S7·실패·모델 응답·해시·세대 완료의 사실 | **원본 정본; append-only/증빙 보호** |
| `research_handoff_v1.json` (권장, 신규 파생 리소스) | 다음 GPT가 알아야 할 최근 사실·부모·시도/금지 패턴·가설·실험 요구조건을 요약 | **정본 아님**; 항상 source head hash에 결박하고 재생성 가능 |
| `research_handoff_v1.md` (선택적 사람용) | 사람이 업무를 인수하고 장애 원인을 확인하는 읽기 쉬운 보고서 | 자동 생성; 원본 데이터 수정 금지 |
| SDK run state | `run_id`, session lock, 호출 예산, pause/reconcile 원인, 마지막 본증명 체크 | 최소 제어 metadata; 새로운 전략원장·모델 정책 금지 |

인계서 스키마의 필수 키 예시(실제 시스템에 구현된 것으로 주장하지 않음):

```json
{
  "schema": "quant-research-handoff-v1",
  "session_id": "<unchanged-server-issued-session-id>",
  "generation_completed": 68,
  "checkpoint_phase": "AWAITING_PLAN",
  "dataset_hash": "<from-canonical-gateway>",
  "catalog_version": "<pinned-version>",
  "source_evidence_head_hash": "<last-immutable-generation-hash>",
  "source_s7_report_hash": "<last-verified-S7-receipt-hash>",
  "selected_parent_hash": "<verified-parent-or-null>",
  "frontier": "<small-curated-valid-parent-frontier>",
  "last_observations": "<measured-trade-based-facts-and-regime-weaknesses>",
  "tested_hypotheses": "<outcomes-and-rejections-linked-to-evidence>",
  "next_research_candidates": "<hypotheses-to-test-not-fixed-SDK-plan>",
  "blocked_options": "<failed-duplicates-broken-units-missing-data>",
  "execution_safety": {"orders_enabled": false, "independent_oos_approved": false},
  "provider_attestation_status": "UNVERIFIED_UNTIL_PROVEN",
  "generation_budget": "<separate-per-run-policy>",
  "handoff_hash": "<canonical-hash-of-remaining-fields>"
}
```

**보안:** raw `checkpoint_token`, OAuth, private signing key, account ID, proprietary data excerpt는 인계 Markdown/JSON 또는 Git에 저장하지 않는다. 토큰은 **매 재진입 시 Quant에서 새로 읽어 해당 모델 제출에만** 쓴다. 인계서는 해시로 정본과 버전 연결; 오래되거나 source hash/dataset/catalog/phase가 다르면 버리고 다시 만든다.

## 단일 세대/단계 재개 프로토콜

1. **Trigger**: 사용자가 `다음` 또는 `N세대`를 요청하거나, 지원이 **확인된** GPT 호스트가 다음 호출을 발생시킨다. 사용자가 직접 호출하면 user-triggered 단계 연속성이며 unattended 운영이라 주장하지 않는다.
2. SDK/호스트는 `get_algorithm_research(session_id)`로 정본과 최신 상태를 조회한다. `session_id`, 데이터·카탈로그 해시, 마지막 증거 체인, 현재 phase, S7 영수증을 확인한다. 어떤 상태인지 모른 채 이전 인계서를 신뢰하지 않는다.
3. Quant 내부에서 `handoff_v1`의 source hashes를 검증하거나 새로 파생한다. **GPT에는 인계서(권장 8–20천 문자 목표)와 실제 필요한 typed schema/증거 ref만 전달**한다. 필요할 때 세부 증거를 추가 조회한다.
4. `AWAITING_PLAN`: Quant 정책·부모 frontier·실패 증거에 근거한 GPT 전략/가설을 생성해 기존 MCP `submit_algorithm_plan(session_id,checkpoint_token,plan)`에 제출. 중복/무효/무거래면 **같은 phase/token**에서 오류 요인만 피드백해 유한한 횟수만 재제안한다.
5. `AWAITING_DIAGNOSIS`: 이전 계획 **재생성 금지**; 실제 S2 체결 및 검증 문맥으로 GPT가 `submit_algorithm_diagnosis` 작성. 완료 후 `latest_controlled_experiments.record_hash`와 원장 재조회를 결합해 각 가설의 S7·head·거래 근거를 검증한다.
6. commit+S7이 검증된 경우에만 **completed += 1**; Quant가 다음 부모/탐색 정책을 선택하고 파생 `handoff_v1`을 원자적 기록으로 갱신한다. 다음 호출에서 새 head를 기준으로 다시 시작한다.
7. `CANCELLED/INTERRUPTED/uncertain response`: 중복 계획 제출·아무 재시도 금지. 기존 `reconcile_algorithm_research`/`resume_algorithm_research` 계약으로 근거를 확인한 후 적법한 단계로만 복귀한다.
8. GPT 호스트가 없거나 run budget 소진 → `BLOCKED_MODEL_HOST_DISPATCH` / `BUDGET_EXHAUSTED`로 **중단하고 상태를 보존**. 문서를 이용해 가짜 모델 판단이나 세대를 만들지 않는다.

권장 실행 단위는 **재진입 가능한 1세대**, UI/SDK 명령의 처리 크기는 우선 **1–3세대**로 제한해 실제 토큰 비용·시간·중단 복구를 측정한 후 10·100으로 확대한다. 1세대는 통상 계획·진단 최소 2 GPT 판단 단계와 비용 포함 S2/S7이며 MCP 호출 수는 세대 수와 다르다.

## 인계 컨텍스트 품질 게이트 (문맥 축약이 학습을 훼손하지 않도록)

- 최근 1–3세대의 중요한 *거래 기반 사실*, 다목적 우수 부모/대안(수익률, MDD, 회전율, 거래 건수, 노출), 거절·중복·반증 이유, F1/F2 지표 약점, S7·개선 기여 및 아직 측정하지 않은 가설을 유지한다.
- `F3/F4` 정식 장기 기억이 검증되면 교차 세대 증거 링크만 인계서에 포함하고 원본 결과는 immutable DB에 남긴다.
- 계속 반복한 실패나 부정확한 요약은 hash/link를 통해 원본 거래를 재조회할 수 있어야 하며, GPT의 설명과 관측 사실을 분리한다.
- 연구 요약은 Quant가 만들어야 한다. SDK가 임의로 어떤 지표/전략이 유망한지 선정하거나, 부모 선택 기준을 덮어쓰는 것은 금지한다.
- **서버 측 간결 조회가 중요:** 현재 `get_algorithm_research` 응답 전체를 모델에게 먼저 반환하고 SDK가 나중에 짧게 정리하는 구조만으로는 모델 토큰 전송을 줄일 수 없다. 원본 32개 도구/기존 `get` 응답은 그대로 두고, 향후 별도 **opt-in read-only `get_research_handoff`** 또는 호환 가능한 server-side compact view를 검증·추가한다. 새 도구 등록/권한 배포는 별도 승인·기존 클라이언트 회귀와 연결.

## 선택지 비교 및 결정

| 선택지 | 연구 상태 연속성 | 독립 GPT 호출 필요 | 위험·비용 | 결정 |
|---|---|---|---|---|
| 기존 68세대 원장 + 다음 사람 주도 ChatGPT↔MCP 호출 | **가능 (기존 구현)** | 사람이 `다음`을 말하면 현재 ChatGPT 호스트가 판단 | 최소 구현/배포 위험, 큰 context 비용 | **즉시 기본 유지** |
| 정본+해시 인계서 + 범위 제한 상태 비저장 재진입 | **가능; 새 server-side brief 필요** | 매 호출마다 GPT 호스트 필요, 지속 프로세스 불필요 | 적은 문맥 목표, 문서 노후화 방지 필수 | **채택: 다음 핵심 구현안** |
| 순수 MCP SDK `tools/call`만 100번 반복 | 상태 조회만 가능, 전략 진화 안 됨 | 없음 → GPT 판단 부재 | 자율 연구 세대로 허위 계산될 위험 | **기각** |
| 검증된 모델 호스트 스케줄러/공식 provider를 통한 무인 세대 루프 | 가능, 조건부 | **필수** | 추가 인증·사용료·제공자 증거·오류 관리 | **향후 호스트 계약 확인 후 별도 승인** |
| 전체 이력 Markdown 덤프를 다음 모델에 반복 전달 | 기술적으로 가능 | 여전히 필요 | 실측 현재 약 664천 문자/응답, 토큰 낭비·정본 드리프트 | **기각** |

## 실증 수락 기준

1. 현행 68/100 운영 원장·MCP OAuth·상태·고정 URL·OOS 봉인·orders OFF 변경 0.
2. 동일 정본 상태→동일 handoff hash; 상태·parent·dataset·S7 변경→서버에서 인계서 무효화/재생성; 비정상 입력·토큰 노출·원본 해시 불일치 시 fail-closed.
3. 계획/진단/중간 중단/유실 응답/동시 실행/완료 모두 정확한 단계 복구. S7 미완료·증거 없는 세대 추가 0.
4. 실험 비교: 기존 full-context vs compact-handoff를 **복제된 비PIT 개발 세션**, 동일 데이터·실험 횟수/모델 정책·모델 호출 예산으로 3→10세대 비교. 컨텍스트 문자 수뿐 아니라 실제 input/output 토큰, 생성/진단 차례, 거절·중복률, 가설 다양성, 새로운 거래 증거, 수익률/MDD/노출·비용·QQQ 기준, 다음 GPT 활용 여부를 측정. 토큰 절감과 품질 보존은 실측 전 **미확인**.
5. 운영 적용은 명시 승인 및 전체 회귀/복구 검증 후. SDK-runner 단독으로 native ChatGPT 새 모델 턴 자동 생성 가능하다고 주장 금지.

## 다음 개발 우선순위 (동결 순서를 바꾸지 않음)

- **V05 유지:** 수익·슬리피지·용량·다중검정 등 기존 안전 게이트부터 확인.
- **T4 최소 구현:** 먼저 `QuantHandoffBuilder` read-only derived state + compact `/get_research_handoff` 설계·리플레이 테스트; 그다음 기존 ChatGPT MCP 모델로 1세대 실제 진행(사용자 호출 방식), 세대 종료 handoff 자동 저장·재개, 3→10 비교. 호스트 없이 무인 루프 요구 시 blocked를 그대로 보고.
- **별도 기존 결함:** 173 generic 지표의 검증된 학술 경로(현 운영 8 VERIFIED), F3→F4/F5 장기 반증 기억, V3 정식 다부모/국면별 컴파일·S2/S7/계승, 과거 19 레거시 파일 기능 동등성 확인은 계속 단계별로 수행. 이들은 인계 시스템 이전에 전부 완료돼야 하는 선행조건이 아니다.

**이 ADR은 사용자가 제안한 “호출할 때마다 기록으로 이어서 진화” 방식의 기술적 채택 판단이며, 기존 연구 목표와 ChatGPT↔Quant MCP/인증 기본 경로 변경을 승인하거나 주장하지 않는다.**
