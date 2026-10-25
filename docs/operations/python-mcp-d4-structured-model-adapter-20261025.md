# D4-P2 — Codex 구조화된 연구 판단 어댑터 (인증 전 구현)

2026-10-25 KST / **T4-PY-MCP-D4-STRUCTURED-01** / 사용자 Q02·Q06·Q08·Q09·Q15·Q17·Q20

## 아키텍처와 중복 방지

- **Moon**은 원격 개발/실행 호스트, **Quant AutoResearch**는 기존 canonical AcademicMCPCheckpointService·S7·증거 원장, **새 포크**는 Python MCP/Codex 연결 실험. 기존 Moon/Quant 원본 저장소/서비스/OAuth/URL·P5 28세대 불변.
- `application/t4_codex_structured_model.py::CodexStructuredDecisionHost`는 **Codex Python SDK 0.163.0**의 `Codex.account()`, `thread_start(sandbox=Sandbox.read_only, ephemeral=True)`, `thread.run(output_schema=...)`를 사용하는 **선택형 모델 결정기**. 기존 `application/t4_codex_host_preflight.py`는 읽기전용 준비도, `integrations/python_mcp_academic_handoff.py`는 외부 수집기 서명된 결정을 canonical Quant MCP로 전달하는 역할.
- **권한 분리:** 새 코드에는 D3 제출 메서드·연구 원장 생성·실주문·OOS 개봉·collector 비밀키가 없다. 단일 판단만 반환하고 어떤 계획도 Quant 원장에 자동 제출하지 않는다. 모의 응답을 실제 GPT 세대로 집계 금지.
- **기본값** `enable_model_call=False`: SDK 실행 전 예외. 명시 허용 이후에도 `Codex.account()` 연결 실패면 모델 턴 0회. `login_chatgpt()`는 실행하지 않는다.
- SDK는 read-only sandbox 및 ephemeral 스레드로 실행. 출력은 JSON schema object 검증, 완료 상태·정상 JSON·비어 있지 않은 thread/turn ID·양수 total 토큰 사용량을 모두 요구. 실패는 **NO AUTO RETRY**, API/토큰 오류 예외의 내용은 외부 반환하지 않는다.
- 감사 메타데이터: canonical JSON context/decision SHA-256, thread ID, turn ID, 토큰 input/output/total, 스테이지(plan/diagnosis), `UNVERIFIED_LOCAL_SDK_METADATA`. **`independent_model_invocation_verified=False`, `provider_signed_receipt_verified=False`, `academic_checkpoint_submitted=False`로 고정**. SDK가 보고한 턴/토큰 사용량은 독립적인 공급자 서명 증빙이 아니며, 기존 D3 `model_capture`과 혼동하면 안 된다.
- 호출자 `project_root`는 존재하는 폴더여야 하고, 기존 `p5_session_id.txt`가 존재하는 **원본 P5 state 폴더를 모델 작업공간으로 직접 사용하면 거부**. 모델 컨텍스트는 JSON 직렬화 가능·256KB 이하. SDK 자체의 read-only sandbox는 host 전체 데이터 접근에 대한 별도 OS 보안 경계가 아니며 인증 완료 전 모델 실행 검증도 하지 않았다.
- 원본 D3의 `SignedAcademicHandoff`는 승인된 external collector가 진짜 모델 응답을 확인하고 **별도의 Ed25519 개인키로 서명한** 경우에만 호출 가능. 이 어댑터 결과만으로 수집기 서명을 대체할 수 없음.

## 테스트 및 실행 제약

신규 `tests/integrations/test_t4_codex_structured_model.py`는 **실제 GPT 호출 없는 fake Codex 객체**를 사용한다. 기본 미허용, 로그인 부재, JSON schema 및 ID/usage, 완료/중단/실패, 위반 JSON, 토큰 0/누락, P5 폴더 거절, 기본 반환 메타데이터의 provider-verified=false를 검증한다.

**실제 GPT 사용량**: 0회. 실제 포크 자율 연구 세대 0, 원본 P5 별도 마지막 검증 28/100. ChatGPT 플랫폼의 플러그인 OAuth와 Codex 독립 SDK 인증은 별도이며 자동 상속한다고 주장하지 않는다. 현재 독립 SDK 계정은 이전 검사 결과 미연결(`BLOCKED_CODEX_ACCOUNT_NOT_CONNECTED`).

## 다음 개발 기준

1. 사용자 승인된 Codex 로그인 및 모델 사용량 한도 확인(미승인 임의 로그인/외부 API 과금 금지).
2. fork-local 읽기전용 실제 모델 1턴의 계획 JSON schema 검증, 응답·turn ID·usage 감사 및 중단 시 동일 계획 자동 재제출 방지.
3. 별도 신뢰할 수 있는 외부 수집기의 모델 사용 증거 및 Ed25519 capture 검증 계약 충족 후에만 D3 MCP로 실제 GPT 1세대→3세대→10세대→100세대 시험.
4. 테스트 mock/result 계수 금지, 원본 20문답과 기존 V05→T4→V01~V04→V06→V07 순서·실주문 OFF/OOS 봉인 유지.

**참고:** [D4 계정 검사](python-mcp-d4-codex-model-host-readiness-20261025.md), [D3 서명 제출](python-mcp-d3-signed-academic-handoff-20261025.md), [전수조사 기준서](../architecture/python-mcp-predevelopment-source-map-v1-20261025.md).

**실제 관련 검증:** 신규 12개 포함 D4/D3/P4-2/S7/MCP/거버넌스 **66/66 pytest PASS**. 포크 전체 `ruff check .` PASS, 새 모듈 mypy PASS, fork-local Python 의존성 `pip check` PASS. 전체 pytest/전체 mypy NOT RUN. 공식 SDK 설치/미인증 account() 확인은 이전 실제 검사 결과를 유지하며, 이번 모델 턴/로그인/연구 제출은 실행하지 않았다.

> GitHub SHA와 원격 push 상태는 실제 commit/push 확인 후 중앙 진행 원장에 확정 기록한다.
