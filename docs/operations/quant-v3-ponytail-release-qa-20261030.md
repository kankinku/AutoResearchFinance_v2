# Quant V3 Ponytail full — 릴리스 게이트 후속 QA (2026-10-30)

## 목적/범위

T4(Q02/Q06/Q07/Q08/Q14/Q17/Q20). 기존 Ponytail 부모 피드백 브랜치 `fix/quant-v3-parent-feedback-ponytail-20261030`의 릴리스 게이트 오류를 조사·완화한다. 전체 연구 원장 110세대, 실제 Quant MCP 고정 URL/OAuth, 사용자 자격정보, 주문 OFF, OOS 봉인, 보안검사·호출 계약 보존. 운영 프로세스 재시작, 연구 데이터 변경, main 병합/배포 **없음**.

## 관측/개선

- 작업 시작 CLEAN HEAD `30a90b1`. 별도 `uv` 바이너리를 `/tmp/quant-v3-release-uv-bin`에 설치, 패키지 검증 환경 `UV_PROJECT_ENVIRONMENT=/tmp/quant-v3-parent-release-env-20261030`을 사용하여 기존 `.venv` 라이브 심볼릭 링크를 건드리지 않음. `uv 0.13.6` 설치됨.
- 원래 `moon.config.json` release의 `uv run --locked --extra dev ruff check .`는 **LOCKFILE_OUT_OF_SYNC**로 실행 불가. `uv.lock` 수정/우회 승인하지 않고, 실제 검사는 기존 잠금 파일을 사용하는 `--frozen` 격리 환경에서 진행. **정식 --locked gate는 미통과.**
- 격리 `uv run --frozen --extra dev ruff check .` 최초 실패 118건, 모두 이전 미커밋 Guided 연구 기능을 이식한 25개 파일 범위(긴 줄 90, import 정렬 및 기타). 관련 22개 Python 파일 서식/사전 자동수정 및 긴 문자열 인접 리터럴 분할 수행. 자동 서식과 문자열 분할은 Python AST 비교로 동일 평가 확인, 예외 재발생 시 명시적 원인 연결(`raise ... from error`)만 의미상 차이. 최종 `.venv/bin/ruff check .` **전수 PASS**, `git diff --check` PASS. 변경 코드 `c77a2ac` GitHub push 완료.
- 수정 후 격리 `uv run --frozen --extra dev python -m pytest -q` 하위군: **38 PASS / 2 FAIL**. 실제 실패 테스트 `tests/integrations/test_chatgpt_mcp_sdk.py::test_chatgpt_plane_does_not_mutate_legacy_public_surface`, `tests/integrations/test_chatgpt_mcp_moon_oauth.py::test_moon_oauth_registration_approval_pkce_and_scope`. 두 테스트 모두 공개 MCP 32개를 요구하는데 신규 `suggest_guided_thresholds`가 추가된 Guided 연구 개발 브랜치에는 33개. 기존 테스트 기대값이나 보안/승인 게이트를 약화하거나 신규 연구 도구를 삭제하지 않았으며, **릴리스 차단**으로 기록.
- 저장소 전체 `.venv/bin/python -m mypy .`는 **69 errors in 24 files (347 checked)**: 본 브랜치 변경 코드 18건/8파일, 변경하지 않은 기존 16파일 51건. Mypy 전체 **FAIL**. 기존 엄격한 검증 규칙을 완화하지 않음.
- 원래 G1–G110 signed Evidence, 원본 개발 data SHA, 생산 MCP URL/OAuth/주문/OOS/보호 경로 `core/`, `deployment/`, `state/`, `data/` 변경 없음. 본 후속 턴 신규 연구 세대 0, 본격 품질 비교·실 모델 호출 0. 전체 pytest/release 프로필 정식 완주 NOT RUN.

## 상태 및 차단

- **기능 개발 WIP / 전체 release 검증 BLOCKED / 운영 NOT DEPLOYED.** Moon MCP task_validate와 현재 승인 프로필이 요구하는 `uv --locked`/전체 Ruff/전체 Mypy/전체 Pytest를 모두 통과했다는 주장은 불가.
- 다음: 기존 MCP 32도구와 신규 threshold 제안 기능을 모두 보존하는 호환 API를 결정하고 같은 계약 테스트 통과 → 정확한 `uv.lock` 불일치를 검토/잠금 고정 → 변경 파일 Mypy 18건 해결, 기존 baseline 51건 별도 결함 분류 → 전체 release profile → 독립 검토 → 동일예산 진화 품질 실측. 사용자 승인 전 33도구 강제 배포, 프로덕션 인증·권한 수정, 봉인 OOS 접근 금지.
