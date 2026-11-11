# Quant ChatGPT MCP 공개 ABI 32개 동결 — [7/16] Task 6

**작성:** 2026-11-10 · **범위:** V05/T4 통합 계약·릴리스 회귀 게이트(Q02/Q06/Q15/Q17/Q20). 새 도구/권한·런타임 서비스 배포를 승인하지 않는다.

## WIP 재현 증거(읽기 전용)

- 기준 개발 통합 브랜치 `impl/quant-improvement-20261110`, 시작 HEAD `fc6fabb`; [승인된 새 G1 초기화 정책](../decisions/2026-11-10-quant-fresh-research-reset.md) 유지. `docs/decisions/2026-10-14-autoresearch-interview-20q.md`·기존 MCP 인증·32개 공개 도구 계약 보존.
- 작업 중인 **별도** `origin/fix/quant-v3-parent-feedback-ponytail-20261030` (`c6a05c7`)은 `main` 대비 **47개 파일 변경**. `integrations/chatgpt_mcp_sdk.py`가 승인받지 않은 `suggest_guided_thresholds`를 ChatGPT 공개 도구/검증 레지스트리에 추가했고 `integrations/codex_mcp_core.py`도 이 호출을 추가함. 32개 고정 검증이 동적으로 바뀌어 33개를 허용할 수 있는 구조임.
- **RED 실측:** WIP 별도 읽기 전용 worktree `/shared/Quant-inspect-20261105`에서 `pytest -q tests/integrations/test_chatgpt_mcp_sdk.py tests/integrations/test_chatgpt_mcp_moon_oauth.py` → **2 FAILED**: (1) SDK 도구 목록 33 != 32, (2) OAuth `tools/list` 목록 33 != 32. 양쪽 모두 도구 이름과 OAuth 32개 계약 위반으로 판단.
- **기존 정상 정본:** 변경 전 통합 브랜치에서 계획의 필수 `pytest -q tests/contracts tests/integrations/test_chatgpt_mcp_sdk.py tests/integrations/test_chatgpt_mcp_moon_oauth.py` → **57 PASS**. WIP 기능의 부모 계승/연구 안내/비공개 threshold 제안 전체를 이 시점의 메인에 합칠 이유나 데이터/실험 증명이 없다.

## 최소 안전 수정

- `integrations/chatgpt_mcp_sdk.py`에 2026-11-10 승인된 **정확한 공개 도구 이름 32개를 독립 불변 목록** `_APPROVED_CHATGPT_TOOL_NAMES`으로 작성. 런타임 `chatgpt_tools()`가 이 목록과 실제 광고 목록·기존 커스텀 레지스트리를 모두 대조하고, 33번째/중복/무단 대체 이름이면 공개 전에 **TypeError로 fail closed**. 기존 32개 도구 스키마·서명·요청·응답·OAuth scope는 변화 없음.
- 기존 `ChatGPTMCPAdapter.call_tool()`은 실행 시 mutable registry 맵 대신 **인스턴스 생성 당시 실제 스키마 검증을 거친 `_input_validators` 집합**만 허용. 생성 이후 런타임 registry가 변해도 미등록 이름 호출은 내부 `KeyError` 대신 기존 `UNKNOWN_TOOL` 일반 실패로 종료한다.
- `tests/integrations/test_chatgpt_mcp_public_abi_lock.py`: 별도 정적 승인 32이름 스냅샷, 33번째 도구/동수 이름 교체/레지스트리만 추가/생성 이후 무단 호출, OAuth 32이름·`mcp:tools` scope·금지 신규 도구 호출 등을 독립 검증.
- `tests/integrations/test_mcp_public_contract_d07.py`의 기존 테스트는 **원래 브랜치에서도 실패**했다(가짜 `D07_ISOLATED_DISPATCH` 응답에 `get_algorithm_research`의 정상 compact 응답 생성 요구). 이 모의 호출에서만 이미 존재하는 `response_mode=full`을 요청하도록 교정. **서버의 `COMPACT_CHECKPOINT_UNAVAILABLE` fail-closed 동작은 변경하지 않음**. 그 외 필수 schema와 실제 경계 테스트는 그대로 유지.
- 승인되지 않은 `suggest_guided_thresholds`를 다른 공개 도구의 신규 선택 인자로 넣지 않았으며 외부/국지 부하 및 권한에 영향 없는 유사 경로는 해당 WIP와 함께 **보류**. 기존 URL/OAuth scope `mcp:tools`·기본 32 도구·기존 컨트롤러/원본 세션 불변. WIP 47개 파일 **자동 병합 금지**; 승인이 필요한 공개 추가는 후속 ADR 필요.

## 재현·테스트 결과

- TDD RED: 32 도구 정상 확인 1 PASS; 변경 직전의 **4개 신규 위반 테스트 FAIL**(33개 공개 가능, 동일 수량 다른 이름 가능, 레지스트리 불일치, 무단 도구 호출 시 KeyError). 변경 후 관련 5/5 GREEN.
- 새 OAuth 경계 시나리오와 기존 정본 스키마 해시 확인 포함 필수+인접 계약 회귀: `pytest -q -p no:cacheprovider tests/contracts tests/integrations/test_chatgpt_mcp_sdk.py tests/integrations/test_chatgpt_mcp_moon_oauth.py tests/integrations/test_chatgpt_mcp_public_abi_lock.py` → **63 PASS**.
- 확장한 SDK/Codex/HTTP·학술 연구/거버넌스 회귀 → **101 PASS** (추가 스키마 고정 해시 테스트 포함). `ruff check .` PASS, `git diff --check` PASS.
- `python -m mypy .` → **51 ERRORS / 16 FILES / 337 source files**. 새 수정 대상 `integrations/chatgpt_mcp_sdk.py`에는 보고된 오류가 없고, **수정 전 통합 브랜치에서도 같은 51개**가 남아 있었음. 전체 타입 검사 PASS 아님. 원래 연구 서비스와 오래된 조사 스크립트들의 타입 오류는 새 기능 범위 밖이라 건드리지 않음.
- **스키마 동일성:** 실제 `main` 브랜치와 변경된 통합 후보의 ChatGPT **32개** 광고 스키마 전체 SHA256은 `badef8286b177181601b4fe88c561f9f4cd121172c5fc90ec74748661192ac87`, Codex **13개** SHA256은 `e11cfcce0a830f5a3cfc9a1f570c0cb21de25960d3876b11757fe7c7a1fed5ce`. 각각 양측 **동일**. 단순 개수뿐 아니라 전체 현재 공개 입력 스키마 해시를 새 회귀 테스트에서 고정.
- **전체 suite:** `pytest -q -x -p no:cacheprovider` → **448 PASS, 1 FAIL** 이후 중단. 첫 실패는 선행 단계와 동일한 `tests/dashboard/test_fresh_original_dashboard.py::test_readonly_sqlite_bridge_matches_original_contracts`, 2026-10-21 과거 세션의 `state/moon-http/fresh-20261021/session-id.txt` 미마운트. 전체 suite PASS 아님.
- 변경·전후 비교는 격리 worktree·로컬 임시 디렉터리 및 테스트 fake transport 한정. **실제 Moon 운영 MCP URL/OAuth 종단 접근/로그인·서비스 재시작·실모델 G1→100·실거래·과거 G150 물리 삭제·새 DB 생성**은 수행하지 않음. 테스트 인증은 샘플/모의 사용자만 이용.

## 차단 사항과 다음

- 실제 원격 ChatGPT 앱 OAuth 커넥터 재연결·실모델 10세대→100세대까지 완료됐다는 주장은 금지. 코드/모의 HTTP 통합에서 성공한 것과 별개이다.
- 기존 구형 대시보드는 2026-10-21 세션 파일이 마운트되지 않아 전수 테스트가 중단되는 알려진 문제. 서드파티 OOS/PIT도 별도 미검증.
- 다음 **[8/16] Task 7**은 T4 학습 패킷과 실패 연구 메모리 검증. **과거 실험의 계승은 금지**되고 새 G1부터 시작해야 한다는 정책과 충돌하지 않도록 가짜 검증 픽스처의 재사용 범위를 제한할 것.
