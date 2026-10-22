# Quant AutoResearch — Moon 직접 실행 100세대 실제 착수 증거 (2026-10-23 KST)

## 상태 판정과 연구 유형

사용자의 **100세대 테스트 시작** 요청에 따라 별도 연구용 100세대 실행 프로세스를 실제로 실행했다. 시작된 범위: G453–G552, **총 100개 신규 세대 목표**. 시작 및 검증 시점: 2026-10-23 00:20–00:23 KST. 본 문서의 집계는 해당 시각에 실제 확인한 스냅샷이며, **100/100 완료 주장 아님**.

- 세대 컨트롤러: `scripts/fresh_development_cohort_controller_20261021.py`의 `DETERMINISTIC_GPT_DESIGNED_POLICY_NOT_PER_GENERATION_LLM`. **실제 비용 반영 엔진, 체결 ID, S7 비교와 해시 연결은 수행**하지만 세대마다 독립 GPT/ChatGPT/OpenAI API 모델이 전략을 새로 판단하지는 않는다. *GPT 자율 연구 100세대 실증으로 분류 금지.* 유료 API를 임의 호출하지 않았고, 별도 Quant OAuth MCP `/quant/mcp`가 미복구여도 로컬 Moon 실행 가능.
- **기준 연구 원본**: `state/moon-http/fresh-20261021/research/academic-gpt-checkpoints`, 완료 **G452/452**, 원본 마지막 Evidence `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`.
- **100세대 격리 복제본**: `state/moon-http/quant-moon-bounded-100-20261023/` (Git ignore). SQLite 3개를 원본에서 SQLite online backup 후 `PRAGMA integrity_check` 통과, `start-manifest.json`에 SHA256와 이전 증거 해시, 연구 유형 고정. 기존 부하테스트 1,435개 이전 후보 시도 로그를 동일 독립 복제본에 보존해 중복/소진 재탐색을 최소화했다. 기존 ChatGPT 직결 **별도 G453 실험 복제본** `moon-invoked-live-g453-20261022`는 건드리지 않았다.
- 동일 계보 복제본에서만 `scripts/run_academic_cohort.py`와 `scripts/fresh_development_cohort_controller_20261021.py`의 **프로세스 내부 상태 경로**를 오버라이드하는 파일 `state/moon-http/quant-moon-bounded-100-20261023/run_bounded_100.py`를 저장했다. 추적된 애플리케이션 코드를 수정하지 않았다.
- 실행 명령: `PYTHONPATH=. .venv/bin/python -u state/moon-http/quant-moon-bounded-100-20261023/run_bounded_100.py`.
- Moon 관리 세션 ID `7916b9d8-7f4a-4060-9557-9f0935e7e213`, 프로세스 PID **37928**. 실행 stdout `BACKUP VERIFIED` → `EXTENDED 452 TO 552` → `RESUMING 452 OF 552` → 개별 `{"g":..., "r":..., "mdd":..., "trades":..., "evidence":...}` 기록.
- Cohort 메타데이터 `state/moon-http/quant-moon-bounded-100-20261023/cohorts/G453-G552-20261023-moon-stress.json`: `state=RUNNING`, `target=552`. **주의:** 실행 중 `completed` 필드는 최초 값 452에서 실시간 갱신되지 않고 종료/오류 시 갱신되므로, 진짜 현 세대는 `research/academic-gpt-checkpoints/cycles.sqlite`의 `generations` 행 수/최대 세대 번호 또는 진행 JSONL로 확인할 것.
- **2026-10-23 00:23:15 KST 실측:** `ps`에서 PID 37928 `Rsl` 실행 중. Clone SQLite **457행/G457 (신규 5/100)**, head `5a19abe9ff3ab2d98e91598c482bb4eca351252177a617b35df32cdab8b8154d`. 원본 452행/G452, head `e620bfec...` 그대로.
- 표본 실제 결과: G453 **+1.66% / MDD 27.78% / 거래 422건**, G454 **+126.70% / MDD 34.95% / 거래 123건**, G455 **−43.40% / MDD 51.61% / 거래 460건**. 이 값들은 **같은 재사용 개발 QQQ 자료**의 비용 반영 개별 후보 결과이며 투자 수익이나 GPT 모델 성과를 의미하지 않는다. 일부 MDD는 30%를 초과한다. 이 기본 결정론적 실행기에는 P3에서 별도로 적용한 MDD 30% 사전 승인 한도가 **활성화되어 있지 않으므로**, 100세대 집계와 위험 한도 합격은 별개다.
- 진행 로그에서 미지원 후보 `ResearchCatalogError: inherited fill has no valid close decision`가 여러 번 사전 거부됐으나 유효 후보를 계속 찾고 세대가 실제로 전진하는 것을 관찰했다. 원인·감사 추적 일치성 문제는 미해결.
- 운영 가드: `orders_enabled=false`; 공식 legacy G350 미복구; sealed OOS 미접근; 새 OAuth URL/키 생성 없음; ChatGPT 전용 MCP 재등록 없음; 원본 복제 및 API 모델 과금 없음.

## 결과 집계 방법 및 실행 안정성

- 최종 100세대 결과 여부는 `G552/552 COMPLETED`, 체인 연속성 및 각 세대 S7 저장, 3개 SQLite 무결성 통과 여부를 **별도로 재검증해야 한다**. 사용자에게 완료 보고할 때까지 `RUNNING`/부분 완료와 `COMPLETED`를 혼동하지 않는다.
- 안전한 동일 작업 재진입은 **이전 PID/세션이 완전히 종료된 뒤** 동일 명령을 동일 복제본에서 재실행하는 것. 실행기는 cohort ID·세션·기준 Evidence 해시·목표 G552를 재사용하고 단일 파일 락으로 중복 실행을 차단한다. `AWAITING_DIAGNOSIS` 또는 `INTERRUPTED` 단계로 중단된 경우 자동으로 뒤섞어 재실행하지 말고 해당 체크포인트와 Evidence를 검증해야 한다.
- 시작 시 `cohorts/...json`과 `start-manifest.json`에 원본 SHA 및 불변 기준을 기록. 실험 SQLite/시스템 자격증명/원본 시장 데이터는 Git에 넣지 않는다.
- 실제 GPT 10→100세대의 **본래 T4 목표는 아직 NOT VERIFIED**. 모델 호출 권한·출처 기록을 갖춘 루프가 따로 필요하다. 범위 승인 순서 V05 → T4 모델 자율 10/100 → V01–V04 PIT/OOS → V06 paper-only → V07 GO/NO-GO 유지. 본 작업은 **연구 백테스트 실행과 내구성 검사**이며 공식 투자 실적/실전 모델 자율 진척으로 분류하지 않는다.

**검증된 출발점:** 독립 복제본의 G452를 원본 해시 그대로 확인하고 G453–G457 실제 계산·해시 기록, 원본 불변 유지, 실제 100세대 목표로 프로세스 실행 중인 상태까지 직접 확인. 이후 어느 시점의 진행률이나 최종 완료는 새 실측 없이 주장하지 않는다.
