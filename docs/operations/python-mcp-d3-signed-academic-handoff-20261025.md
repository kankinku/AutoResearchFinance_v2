# D3 — 서명 검증 기반 Academic MCP 계획·진단 전달 계층

**기준일:** 2026-10-25 KST · **작업:** T4-PY-MCP-D3-01
**승인 범위:** 원래 인터뷰 Q02/Q06/Q08/Q09/Q11/Q15/Q17/Q20 및 D1/D2 후속. 고정 V05→T4→V01~V04→V06→V07 유지.
**범위:** **독립 포크** `kankinku/AutoResearchFinance_PythonMCP`, Moon의 별도 포크 작업공간만 사용. 원본 Quant·Moon 자체/OAuth·원본 P5 28/100·브로커·봉인 OOS 변경 없음.

## 이번 구현

1. `integrations/python_mcp_academic_handoff.py::SignedAcademicHandoff`: **기존** `AcademicMCPCheckpointService`와 공개 `get_algorithm_research`, `submit_algorithm_plan`, `submit_algorithm_diagnosis` 도구를 사용하는 얇은 MCP 연결 계층. 전략 계산·S7·원장·세대 계수 로직 **재작성 없음**.
2. `QuantMCPSettings.capture_public_key_hex`: **신뢰된 외부 수집기의 공개 키**만 학술 세션에 바인딩, 새 자식 서버에 `QUANT_MCP_P4_MODEL_CAPTURE_SESSION_ID`·`QUANT_MCP_P4_CAPTURE_PUBLIC_KEY_HEX`를 전달. 개인 서명키나 OAuth/API 비밀 정보 복사·추출 없음. 공개 키 형식과 원래 P5 state 경로 차단.
3. 제출 전 포크-local `read_academic_checkpoint` 실제 조회: 정확한 세션 ID/체크포인트 토큰·단계·generation·orders OFF·sealed OOS·P4-2 등록·외부 수집기 chain을 확인. `research/llm/model_provenance_v1.verify_capture`로 응답 본문 해시·기존 chain_head·컨텍스트 해시·Ed25519 서명 재검증.
4. 동일한 MCP 자식 프로세스 안에서 재조회 후 정확한 단계만 제출. 계획 단계에서는 부모가 검증된 경우 `require_execution_change`, 그리고 `require_trade_activity`를 설정. **첫 세대의 비상속 AlgorithmPlan은 검증된 inherited parent가 없으므로 `require_execution_change=False`를 명시해야 함**. 진단에서 실제 거래/결정 ID·대조실험은 기존 Academic/S7 서비스가 검증한다.
5. 정상 완료 시 두 번째 authoritative `get`으로 단계와 세대 증가를 검사. 완료된 세션은 다음 토큰을 제공하지 않을 수 있으므로 `checkpoint_token=None`을 허용. 불확실한 응답·동시성 변경·이상 세대 증가는 중단. **불확실한 요청을 무조건 재시도하지 않음**. 중단 후 다음 처리는 언제나 원래 checkpoint를 먼저 조회해야 함.
6. 모델 제공자 호출은 **없음**. signed `model_capture`는 **EXTERNAL_COLLECTOR_SIGNATURE_NOT_PROVIDER_ATTESTATION**에 해당. 서명이 수집기 내부 증명일 뿐 실제 GPT 공급자나 모델 호출을 독립 입증하는 증거가 아니다. **P4-2의 `provider_signed_receipt_verified=False`, `independent_model_invocation_verified=False`를 그대로 인정**. 외부 collector가 사용자 승인 없이 자동으로 서명키를 만들거나 제공자 인증을 가장하도록 구현하지 않음.

## 현재 테스트 기준

신규 `tests/integrations/test_python_mcp_academic_handoff.py`:
- 공개 키/정확한 학술 세션/실행 표면 조건 검사
- 서명 누락/서명 본문 변조 → 제출 전 거부, 원장 미증가
- 실제 fork-local **공식 MCP STDIO** subprocess로 테스트 수집기 서명 사용해 비용 반영 AlgorithmPlan → 진단 → 원래 S7 controlled experiment → 최종 checkpoint/SQLite/Ed25519 chain까지 1세대 완결 검증
- **시나리오의 작성 주체는 `ScriptedResearcher` deterministic fixture**. 실제 GPT 호출을 증명하지 않으며 **실제 1세대 진행률에 포함하지 않음**.
- 원본 P5/기존 포크 기본 state와 다른 `tmp_path` 하위에 데이터/DB/공개키가 모두 격리됨.

검증:
- D3 전용 pytest **9 PASS** (격리된 서명·MCP 계획/진단·S7·완료 정상 시험).
- **포크 독립 `.venv`의 관련 회귀 pytest 37 PASS**: D3 신규·D2 STDIO·P4-2 외부 수집기 서명·기존 S7·ChatGPT MCP 공개 SDK·범위 거버넌스. `ruff check .` PASS, `mypy integrations/python_mcp_direct.py integrations/python_mcp_academic_handoff.py` PASS, `git diff --check` PASS.
- 전체 경제검증/독립 OOS·실거래/전체 pytest는 **NOT RUN**. GPT 모델 호스트 호출 **0**.

## 다음 단계 및 차단 사유

**D4: 실제 GPT 모델을 호출하는 승인된 호스트/기존 ChatGPT 플러그인 실행 환경 연계가 없으므로 여전히 BLOCKED.** 현재 Moon 새 포크 내 Codex SDK 로그인 상태와 인증된 출처 영수증은 없음. `SignedAcademicHandoff`가 model provenance를 직접 발행/서명하거나 provider credential을 발급하지 않는다.

다음에는 승인된 모델 실행 주체가 실제 prompt/response를 생성하고 신뢰된 수집기가 이미 확정한 Ed25519 공개 키에 연결된 **독립 키로 서명**한 경우만 D3에 공급하여, fork-local 실제 GPT 1→3세대를 검증한다. 실제 호출 식별자/사용량/중단·재개·메모리 압축은 D4 때 반드시 확인한다. 그 전에는 테스트 서명으로 만든 세대를 실제 모델 연구로 표기하지 않는다.

**사용자 가치:** Python은 반복 MCP 교환·원장 확인과 S7 실행을 담당하고 GPT는 계획/진단 작성만 하게 하는 최소 연결이 작동한다. 코드 중복 없이 기존 전수조사의 단일 Academic checkpoint 권한을 유지한다.
