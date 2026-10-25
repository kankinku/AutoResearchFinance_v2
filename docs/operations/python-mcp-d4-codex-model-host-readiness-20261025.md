# D4 — Codex 모델 호스트 설치·준비도 검증 (읽기 전용)

2026-10-25 KST · 작업 `T4-PY-MCP-D4-READINESS-01` · 사용자 확정 Q02/Q06/Q08/Q15/Q17/Q20 및 V05→T4→V01~04→V06→V07 이행 종속 작업.

## 시스템 역할을 바꾸지 않는다

- **Moon:** 기존 MCP/원격 작업실행 호스트. 연결 방식, 고정 URL, OAuth는 수정하지 않음
- **원본 Quant AutoResearch:** 기존 `kankinku/AutoResearchFinance_v2`, P5 28/100 checkpoint와 보안/시장 데이터/원장 그대로 보존
- **개선 실험 포크:** `kankinku/AutoResearchFinance_PythonMCP`, 별도 Moon 폴더 `/shared/moon-workspace/AutoResearchFinance_PythonMCP`, `state/python-mcp`만 새 연구 데이터
- **Codex SDK:** 모델 실행자 후보이며 독립적인 인증과 사용량 제한 적용. ChatGPT 플러그인 OAuth를 자동 상속한다고 가정 금지. D3 기존 signed academic MCP 제출은 **실제 모델 호스트가 인증·증빙되기 전까지 운영 사용 불가**

## 이번에 실제 완료한 작업

- 새 포크의 **독립 `.venv`에만** `openai-codex==0.163.0` 및 해당 공식 CLI 바이너리 설치. 선택적 설치 사양은 `requirements-codex-host.txt`에 고정. 원본 저장소나 Quant·Moon 기본 Python 환경에 설치하지 않았음
- `Codex.account()`를 사용하는 **읽기 전용 실제 app-server 연결 검사 PASS**. 계정 정보/토큰은 출력하지 않았으며 반환된 `account`가 `None`임을 확인
- `application/t4_codex_host_preflight.py` 신규: 기존 `application.t4_model_host_preflight.audit_t4_model_host`를 재사용하는 checkpoint-scoped 검사, 그리고 **아직 fork-local 세션이 없는 상태**에서도 사용할 수 있는 host-only `probe_codex_account()` / `probe_installed_codex_account()` 제공
- `scripts/codex_account_probe.py`: 모델 턴, 로그인, 외부 Quant 세션 접근 없이 설치와 연결만 검사; account id/토큰/환경변수 출력 금지
- `tests/integrations/test_t4_codex_host_preflight.py` / `test_t4_codex_account_probe.py`: 설치 누락·미인증·가상 인증·민감정보 포함 예외·거래/OOS 보호 경계. **기존/신규 D4 관련 17/17 PASS**
- 실측 명령:

```bash
cd /shared/moon-workspace/AutoResearchFinance_PythonMCP
PYTHONPATH=. .venv/bin/python scripts/codex_account_probe.py
```

실제 응답: `sdk_installed=true`, `sdk_version=0.163.0`, `account_connected=false`, `status=BLOCKED_CODEX_ACCOUNT_NOT_CONNECTED`, `model_turns_started=0`, `login_attempts_started=0`, `oauth_changes_performed=false`, `orders_enabled=false`, `independent_oos_approved=false`.

이 모델 호스트 조사 결과는 **Codex가 실제 GPT를 호출했다는 증거가 아니다**. 모델 요청 0회, GPT 전략/진단 0건, 실측 P5 추가 0세대, 새 포크 실측 GPT 세대 0.

## 안전/연구 무결성 결론

1. 독립 `Codex.account()` 응답은 계정 로그인 여부만 의미하며 **모델 호출 ID·거래/백테스트 성과나 공급자 직접 서명은 생성하지 않는다**.
2. 연결 후에도 현재 D3의 `model_capture`은 *external collector assertion*, **provider-signed proof**가 아니다. 운영용 자율 연구를 주장하려면 실제 모델 invocation의 검증 가능한 근거가 별도로 필요.
3. 새 포크의 연구 원장이 없는 상태에서 원본 P5 state를 연구 세션처럼 조회하지 않는다. D4 host-only probe는 이 용도로 새로 분리됨.
4. `login_chatgpt()`와 실제 모델 `thread_start`/`thread.run`은 이 검사 코드에서 호출하지 않는다. 사용자가 승인한 로그인·사용량 한도에 따라 별도 수행.
5. 격리한 P4 서명키에 대한 신뢰 경계, 원본 실거래 OFF, OOS 봉인, 기존 외부 ChatGPT 연결/기본값은 변경하지 않는다.

## 남은 작업

- 사용자 승인된 Codex/ChatGPT 계정 로그인: **BLOCKED_CODEX_ACCOUNT_NOT_CONNECTED**
- 인증 후 실제 모델 턴 및 SDK 구조화 JSON 출력; SDK 대기·사용량 제한·호스트 오류 중단/재개, 모델/turn ID·토큰 사용량 식별: **NOT RUN**
- 수집기 서명과 제공자 모델 실제 호출 증거의 구분, 실제 모델 결과와 D3 Academic MCP 1→3→10→100세대: **NOT RUN**
- 전체 pytest/전체 mypy, 다른 OS/호스트 설치 재현성, 독립 OOS 수익성: **NOT RUN**

버전 고정은 이 새 포크 실험환경에만 적용하는 **선택형 설치**이며, 기존 Moon이나 Quant 전역 모델 방식을 Codex로 교체하는 행위가 아니다.

## 확인된 검사

D4 단독·기존 T4 model host **17/17 pytest PASS**, D3/P4-2/S7·MCP·거버넌스 포함 독립 `.venv` **54/54 pytest PASS**, 실제 account-only CLI PASS. 포크 전체 `ruff check .` PASS, `mypy application/t4_codex_host_preflight.py` PASS, `pip check` PASS, `git diff --check` PASS. **전체 pytest/전체 mypy는 NOT RUN**. GitHub 동기화는 실제 push/원격 확인 후에만 완료 표시.

**원격 동기화 보충:** 독립 GitHub `main`에 이전 D3 두 커밋과 D4 구현 `bd9339d`까지 `git push origin main` 성공 확인. 기존 원본 Moon·Quant의 Git/인증은 변경하지 않았다.
