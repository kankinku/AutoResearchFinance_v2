# Quant Autoresearch — [2-2 / D01] 재제출 멱등 계약 개발 기록 (2026-10-15)

## 대상과 실제 변경

현재 Moon 개발 저장소 브랜치 `feat/d01-mcp-idempotent-submission-20261015`, 기능 코드 `d9255d9`를 GitHub origin에 Push했다. 운영 서버에는 배포하지 않았다.

- `application/academic_checkpoint_service.py`: 새로운 SQLite `submission_receipts` 테이블로 가장 최근 Plan/Diagnosis 제출별 요청 해시·이전/결과 토큰 해시·결과 phase·완료 세대 수 및 레코드 무결성 해시를 보존한다. **토큰 원문은 중복 저장하지 않는다.**
- 원래 체크포인트가 소비된 상태에서 동일 토큰·동일 요청이 재전송되면 현재 저장된 phase/token/generation과 수집 기록의 무결성을 확인해 **동일한 checkpoint 결과**를 반환한다. 재실행·세대 증가·실험 중복 저장 없음.
- Diagnosis 재제출 시 S7 실험 보고서의 기존 checksum/immutable evidence를 읽어 최초 제출과 동일한 `latest_controlled_experiments` 답변을 복원한다.
- 토큰이 같아도 변경된 payload나 `require_signal_change` 옵션, 이후 세대로 이동해 무효가 된 재제출, 조작된 수신증은 거부한다.
- `integrations/chatgpt_mcp_sdk.py` 제출 설명에 동일 제출 재시도 계약 추가. 기존 32 MCP 도구 이름·인자 스키마·URL·OAuth 변경 없음.
- 무거래 G2 판정에 사용했던 실제 결정 ID 정책은 그대로 보존한다. 이 단계는 **고객 응답 소실 시 중복 실행 방지**이며 오류가 발생한 RUNNING 상태 복구 전체는 D02에서 다룬다.

## 실행한 테스트와 후순위 검증

- T0/T1: `tests/integrations/test_academic_mcp_submission_replay.py`의 성공 후 프로세스 재생성·Plan 재제출·Diagnosis 재제출·다음 세대 이후 stale 토큰·payload 변경·수신증 무결성 변조 검사. `test_academic_mcp_sessions.py`에서 실제 무거래 2세대 재제출 및 기존 동일 제출 반려 기대치를 새 멱등 계약에 맞게 수정.
- 실제 실행: 선택 관련 Pytest **8 passed, 20 deselected**, Ruff/Mypy 변경 소스 통과, `chatgpt_tools()` 32개 확인. 별도 전체 프로젝트 Pytest 및 T4 실제 GPT 10/100세대는 **실행하지 않았으므로 PASS가 아님**.
- T2: 기존 SDK·연구 MCP 전체 통합 검사는 차후 D02~D07과 합동 수행. T3 저장소 전체 회귀 및 T5/T6 실제 빈티지·OOS·수익·모의거래는 원래 사용자 지정 개발 우선순위에 따라 후순위.

## 다음 순서

1. **D02/2-3:** 서버 크래시가 phase=`RUNNING`으로 남긴 경우의 분류·안전 reconcile·재개·checkpoint receipt 보존 일관성 확장.
2. D03/3-2: 논문 후보 방법/권리 검토와 안전 수식 파이프라인.
3. D04/3-1부터 D08/5-1까지 기능 개발 → V01~V07 최종 검증.

**제약:** 기존 실제 ChatGPT MCP endpoint/인증/운영 프로세스·저장된 세대 원장·sealed OOS/실거래 주문 권한은 이번 코드 개발에서 건드리지 않았다. `d9255d9`는 GitHub 개발 브랜치만 통과했고 운영 적용 승인은 아님.
