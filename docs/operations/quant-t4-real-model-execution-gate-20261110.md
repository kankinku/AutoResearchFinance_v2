# Quant T4 실제 모델 10→100세대 실행 게이트·체크포인트 복구 — [11/16]

**작성:** 2026-11-10 KST · 승인 [16단계 계획](../superpowers/plans/2026-11-10-quant-research-improvement.md) Task 10 · Q02/Q06/Q07/Q08/Q09/Q15/Q17/Q20.

## 실제 환경 판단 — LIVE BLOCKED

1. Moon 사용 중인 단일 통합 브랜치 `impl/quant-improvement-20261110` 및 루트 `/shared/Quant-implementation-20261110`에서 읽기 전용 `find`로 시세 원본 `*QQQ*.parquet`, 연구 원장 `cycles.sqlite`, `gateway.sqlite`, 옛 `session-id.txt`의 실행 가능 정본을 찾지 못함. 현재 `state`에는 비활성 빈 JSON 4개뿐이며 `data/` 연구 원본 디렉터리 없음. **이 마운트에 없음 ≠ 운영 원본이 영구 삭제됨.**
2. 사용자 연결 Quant AutoResearch MCP의 **읽기 전용** `list_market_data`, `get_workspace_status`를 직접 호출했지만 **둘 다 내부 오류**. 같은 Quant 앱의 실 모델 Plan/Diagnosis 제출 및 인증된 운영 원장 검증 **NOT_VERIFIED**. 현재 작업자가 사용하는 Moon 도구가 연결되어 있어도 운영 Quant ChatGPT 앱이 인증됐다는 뜻은 아님.
3. Moon venv 실행환경에서 `OPENAI_API_KEY`, `QUANT_MCP_URL`, `MOON_MCP_URL`, `TIINGO_API_KEY`라는 **환경변수 이름의 설정 여부만** 조회한 결과 모두 NOT_SET. 사용자의 다른 앱·로컬 머신에 키가 없다는 단정은 아님. 키·개인 토큰 값을 출력하거나 저장하지 않음. 임의 신규 유료 API 공급자·MCP 서버·OAuth 우회 도입 **0건**.
4. 기존 `scripts.run_academic_autopilot`를 기본 `mcp` 모드와 존재하지 않는 읽기 경로로 실제 호출함. 결과는 `USE_EXISTING_CHATGPT_MCP_CONNECTOR`, `session_created=false`, `external_model_called=false`이며 지정한 빈 상태 디렉터리가 생성되지 않았음을 확인. 기본 스크립트는 **MCP 서버가 스스로 ChatGPT 모델을 호출하지 않음**. 이 응답은 모델 연결 정상/실행 허가의 증거가 아니다.
5. [10/16]에서 고정된 새 G1 세 군 연구 프로토콜 SHA `45a446476150784b92da958ffb78f280d406fe12d5dafa1be82f1c0334695daa`는 프로토콜 단독 고정이며, 신규 시세/평가 정책 SHA·신규 세션 3개의 실제 원본 진본을 얻지 못해 실행 매니페스트 아직 미생성. 사용자 승인 [과거 실험 배제 ADR](../decisions/2026-11-10-quant-fresh-research-reset.md)에 따라 과거 G1~G150·관련 S7/S8 기억/부모를 신규 G1로 연결하지 않음.

**따라서 실제 ChatGPT 10세대/100세대, GPT/무작위 성능 비교는 현재 BLOCKED.** 모의 계획과 위조된 100회 카운트를 실제 자율 연구로 인정하지 않으며, 원본 파케이 생성/다운로드·새 세션 무단 시작·비용성 API 호출·실주문·모의 성과 승격을 수행하지 않았다.

## 실행기에서 재현한 결함과 최소 수정

기존 `AcademicCheckpointAutopilot.run(session_id, max_generations=...)`은 `AWAITING_PLAN`, `AWAITING_DIAGNOSIS` 재개, `RUNNING` 명시 조정, 원장 append-only, 마지막 세대 S7의 재계산을 이미 지원한다. 이 기본 공개 메서드·MCP 32도구·기존 URL/OAuth·요청/응답 형식·실행 정책은 유지한다.

새 RED 시나리오: 복구된 S7 응답에서 `report.experiments`를 빈 배열로 바꾸더라도 실행기가 **S7 검증 없이 완료**로 보고하는 결함 확인. 테스트의 프록시 서비스가 잘못된 가설 ID/세션 ID/S7 해시를 돌려주는 경우도 방어해야 한다. 기존 반환 객체가 가진 `orders_enabled`/OOS 권한을 검증하지 않고 `propose`를 호출하는 경로도 차단한다.

- `research/llm/checkpoint_autopilot.py`: 공용 저장소 S7 `record_hash`를 다시 계산하고, 정확한 세션·세대·원본 Evidence·원본 `hypothesis_ids`와 측정 실험을 정합 확인, 개발 전용 study scope도 확인. 누락·조작·중복된 가설, 빈 실험, 다른 세션이면 모델에 다음 계획을 보내거나 완료로 보고하기 전에 `AutonomousLoopError`로 fail-closed.
- 실주문·봉인 OOS 접근 승격이 확인된 상태는 **모델 호출 전 차단**. 최종 COMPLETED 반환은 `all_proposed_hypotheses_measured=true`인 경우에만 허용.
- `actual_model_invocation_attested=false`를 결과에 추가한다. `model_transport_tested=CALLER_SUPPLIED_PROVIDER_ONLY` 보존. 호출자가 제공한 가짜 provider의 `propose`가 실행됐다 하더라도 사용자 앱에 실제 LLM 호출 증거가 있음을 추정하지 않는다.
- 새 자동 무제한 세대 실행기, 사용자의 앱 로그인 대신 별도 API, 데이터 생성·매매 권한·연구 기본 경로 변경 없음.

## 통합 시험(모의 호출; 라이브 GPT 아님)

`tests/integrations/test_academic_autopilot.py`에 기존 실 정본 백테스터·임시 개발용 synthetic Parquet을 재사용한 독립 회귀: 조작된 S7 4종, 주문/OOS 권한 승격 2종, 모의 모델 진위 플래그, S7 기록 삭제 후 **원본 세대 해시 유지/원장 재계산/다음 1세대만 정확히 진행**, RUNNING 상태의 **운영자 명시 재조정 후 중복 없이 완료**. 별도 기존 10세대 scripted 테스트와 API·게이트웨이 재시작/토큰 중복 제출/복구 테스트를 확대 실행한다. 합성 데이터 및 scripted provider는 연구 성과 증거 **아님**.

## 검사 결과

- 기존 세션·S7·중복 제출·복구·거버넌스와 신규 부정 테스트: **66 PASS** (모의 연구 전용). `ruff check .` PASS, 수정 `checkpoint_autopilot.py`에 대한 mypy PASS, `git diff --check` PASS.
- 전체 pytest 성공은 미확인(기존 구형 대시보드 자료 부재). 실제 GPT 10/100 미실행.

## 실측 테스트 결과

- 변경 전 기본 계약: 학술 자동연구·게이트웨이 복구·토큰 중복 재생·세션 확장·거버넌스 중심 **57 PASS**.
- 새 TDD: 빈 S7 실험 목록을 완료로 인정하는 실패를 RED로 재현, 구현 후 `tests/integrations/test_academic_autopilot.py` 신규/기존 **13 PASS**. 확대 MCP/OAuth/세션·코어 연구 재개·거버넌스 **68 PASS**.
- 실제 시스템 기본 명령: `python -m scripts.run_academic_autopilot --execution-mode mcp ...` → `USE_EXISTING_CHATGPT_MCP_CONNECTOR` / 세션 미생성 / 모델 호출 0.
- `ruff check .` **PASS**, `mypy --follow-imports=silent research/llm/checkpoint_autopilot.py` **PASS**, `git diff --check` PASS.
- 전체 `pytest -q -x -p no:cacheprovider` → **448 PASS, 1 FAIL 이후 중단**. 기존 `tests/dashboard/test_fresh_original_dashboard.py::test_readonly_sqlite_bridge_matches_original_contracts`가 마운트되지 않은 `state/moon-http/fresh-20261021/session-id.txt`에 접근함. **전체 pytest PASS 아님**, 변경 전부터 반복되던 환경 차단.
- 전체 `python -m mypy .` → **51 ERRORS / 16 FILES / 338 소스**, 수정 전 단계에서도 동일 51건이 확인됐고 수정한 `checkpoint_autopilot.py` 직접 오류는 0건. **전체 mypy PASS 아님**.
- 서명/자원·코드의 별도 독립 리뷰어 **NOT_RUN**. 이 테스트에서 `ScriptedResearcher`와 `TenGenerationScriptedProvider`의 10세대는 실제 백테스트를 쓰는 **합성 입력 기반 인터페이스 시험**이며 라이브 GPT 관여·새 실제 G1 10/100세대의 증거가 아님.

## 완료·미완료 및 다음

- [ ] 운영 실제 신규 QQQ 자료의 SHA/기간/평가 정책·데이터 소유자 검증, 실제 OAuth Quant MCP 앱 접속 및 Plan/Diagnosis 제출.
- [ ] 새 G1 사전등록 실행 매니페스트를 **실행 전** 외부 불변 로그에 커밋.
- [ ] 실제 모델 10세대 완료, S7 서명/모델 계획·진단 20회/중단·재개/토큰·비용 감사.
- [ ] 실제 모델 100세대 완료 및 명시 중지까지 지속 모드, 마지막 20세대 정체·중복 분석.
- [ ] 동일 자원 고정 규칙/난수 대조군과 독립 실제 S7·거래비용/중복 체결 결과 비교. 단순 완료 수로 자율 진화 우월성 주장 금지.

**단계 판정:** [11/16] **코드 안전·복구 테스트 개선 수행 / 실제 GPT 10→100 실행과 진화 효과는 BLOCKED**, T4 라이브 인수 조건 **NOT ACCEPTED**. 통합 PR #6 Draft 유지, `main` 미병합. 다음 로드맵은 [12/16] Task 11 독립 OOS 준비이며 라이브 T4 미완료를 성공으로 위장하거나 건너뛴 전제로 사용하지 않는다.
