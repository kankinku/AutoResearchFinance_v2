# Quant 채팅 직접 연구: 3단계 압축 경로, 운영 연결 검증

**날짜:** 2026-10-26 KST
**Stage:** `T4-CHAT-DIRECT-ROUNDTRIP-OPTIN-20261026`
**Q IDs:** Q02/Q06/Q08/Q09/Q11/Q15/Q16/Q17/Q20
**범위:** 기존 ChatGPT 채팅 GPT ↔ Quant 32 MCP 도구 **그대로**, 별도 Codex SDK 모델 호출 0건. Quant 학술 세대 원장(68/100), OAuth/URL·실주문 OFF·OOS 봉인 불변. 상위 작업 순서 **V05→T4→V01–V04→V06→V07** 유지.

## 발견한 병목 및 실제 해결

기존 P1~P3 패치에서 `get_algorithm_research` 읽기만 `response_mode=compact` 옵션이 있었다. 하지만 한 세대마다 `submit_algorithm_plan`과 `submit_algorithm_diagnosis` 결과도 `history` 전체를 반환한다. 따라서 **조회만 경량화해서는 실제 ChatGPT 100세대 연구의 전송 병목이 해결되지 않는다.**

이번 작업:

1. 같은 기존 도구의 `submit_algorithm_plan`, `submit_algorithm_diagnosis`에도 `response_mode=compact` **선택 인자만** 추가. 기본값은 이전과 똑같은 `full`. 공개 도구 **32개 유지**, schema required 목록 변경 없음.
2. 응답에만 동일한 `compact_academic_checkpoint`를 적용한다. 코어 제출 인자는 `response_mode` 제거하고 그대로 전달한다. 계획/진단 모델 입력, 원본 SQLite, checkpoint token, parent/canonical evidence hash, S2/S7 측정과 typed schema 계약 변경 없음.
3. **원장 쓰기가 이미 성공한 후에 축약 실패한 경우** 절대 `is_error=true`로 처리하지 않는다. 원본 완전한 성공 응답을 `compact_submission_status=FULL_FALLBACK_AFTER_SUCCESSFUL_WRITE`와 함께 반환한다. 거짓 실패 → 이중 제출/계수 위험 방지. 읽기만 수행한 축약 실패는 기존 `COMPACT_CHECKPOINT_UNAVAILABLE` 오류로 안전하게 full 재조회 안내.
4. 모델/SDK fork 호출 추가 없음, 백그라운드 실행 없음, 사용자가 명령하지 않은 다음 세대 판단/제출 자동실행 없음.

## 검증

- 신규 테스트: 공개 도구 32개와 세 조회·제출 선택 스키마, 실제 격리 Quant 학술 plan→S2→diag→S7→next plan 전체 추적, 양쪽 write 응답의 캐노니컬 단계/해시/토큰 보전, 뒤늦은 축약 실패의 **성공 응답 보전·중복 계수 없음**.
- GPT 3단계·OAuth·서버·학술 plan/diagnosis/S7/중복·복구·거버넌스 선택 회귀 **76/76 PASS (134.33초)**, 전체 `ruff check .` PASS, 수정 소스 `mypy` 3개 파일 PASS, 별도 전용 9/9 PASS. 전체 저장소 pytest/mypy 및 진짜 GPT 세대 호출은 미실행.
- 운영 기존 68/100 실제 인증 MCP 호출은 먼저 기본 full로 68/100/AWAITING_PLAN 읽기 확인한 뒤 다음 단계를 확인한다. 모델 호출/실계좌 주문/OOS 미수행.
- 원래 68세대 개발가격 기준 `full` 701,397 bytes 대 `compact` 110,540 bytes (과거 **읽기 경로에 대해서만** 실제 원장 복제본 측정). 새 write 경로의 모델 비용/응답 실측은 분리해 표기한다. **바이트 감소 ≠ GPT billable tokens 감소**.

## 배포 및 현재 상태

- 수정 소스: `integrations/chatgpt_mcp_sdk.py`, 신규 테스트 `tests/integrations/test_chat_quant_compact_checkpoint_p1_p3.py`.
- 운영 Quant 루트의 기존 dashboard WIP 파일·그 밖의 세션·인증 상태 보호. 운영 브랜치가 별도 체크아웃이므로 개발 Git push만으로 자동 배포되지는 않는다.
- 운영 배포는 실제 MCP 32개/기존 인증상태 보존, 재시작, 연결된 앱의 read-only live check, clone test, 안전 롤백 조건을 확인한 뒤 별도 기록한다. 원래 모델 도구 스키마는 연결된 클라이언트 캐시에 남을 수 있으므로, 서버 배포가 됐더라도 채팅 클라이언트가 새 선택 인자를 인지하는지 별도 확인이 필요하다.

## 남은 단계

- 채팅 클라이언트에서 실제 opt-in GET/PLAN/DIAG 3개 공개 인자 노출 확인, 필요하면 기존 연결 갱신 **(OAuth 재발급 없이)**.
- 사용자 지시로 기존 68/100 checkpoint에서 **진짜 GPT** G69→ ... 를 진행하면서, 백테스트/계승 실패 시 재계획, 유효세대·생성시간·비용/토큰을 비교. 100세대를 단일 응답에서 무조건 완성한다고 주장하지 않는다.
- 기존 SDK Fork에서 모델호출 구조를 사용하지 않고 부모 선정/시장국면/S7 품질 기능만 분리 검증 후 순차 이식. 2026 OOS 잠금 및 주문 OFF 유지.

## 2026-10-26 운영 적용 결과

운영 Quant 브랜치에 세 소스 파일만 적용한 커밋 `e6a5719` 및 진행원장 커밋 `6a561ff`를 Push했습니다. Quant 서버 프로그램만 재시작했으며 기존 인증 연결의 일반 연구 조회에서 68/100세대, 69세대 계획 대기 상태를 확인했습니다. 기존 대시보드 수정과 별도 SDK Fork는 건드리지 않았습니다.

운영 코드의 MCP 어댑터 직접 조회에서는 68세대 원본 응답 701,520바이트, 압축 응답 110,663바이트로 84.2% 감소했고 세대 해시, 체크포인트, 부모, 계획 스키마는 일치했습니다. 도구는 32개이며 새 GPT 호출과 세대 추가는 없습니다.

**현재 남은 제한:** 이 채팅에 연결된 Quant 도구 인자 스키마가 예전 버전이라 `response_mode=compact`가 서버 도달 전에 거부됩니다. 서버 구현·배포는 완료했지만 사용자 채팅에서의 선택형 압축 호출은 아직 검증되지 않았습니다. 기존 일반 조회는 정상이며 기존 인증을 변경하지 않았습니다.
