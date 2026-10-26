# Quant 직접 채팅형 연구 — P1/P2/P3 체크포인트 비용·재개·오류 수정

**날짜:** 2026-10-26 KST
**작업 ID:** `T4-CHAT-DIRECT-P1P3-CHECKPOINT-20261026`
**Q02/Q06/Q08/Q11/Q15/Q16/Q17/Q20**, **선행/후행:** 승인된 V05→T4→V01~V04→V06→V07 **불변**. 실제 model-authored T4 연결성을 향상하는 기존 종속 작업, 경제/PIT/OOS 수익성 실험 아님.

## 해결하려는 구체적 문제

현재 Quant의 `get_algorithm_research`는 68세대 history가 수십만 문자로 쌓여도 그대로 모델 문맥으로 응답한다. 모델은 기존 ChatGPT 채팅에서 GPT가 담당하며, 연구 엔진은 실행·진단·S7 원장이다. 추가 Codex SDK 호출 또는 별도 모델 스레드 도입은 사용자 명시 요구에 반한다. 100세대 사용자 지시가 10세대 근처에서 종료된 현상은 **정해진 10세대 서버 한도라고 증명되지 않았고**, 단일 ChatGPT 응답이 종료된 뒤 서버가 다음 GPT 턴을 스스로 만들 수 없는 구조가 확인되었다.

## 세 가지 구현 (통합 개발 브랜치만)

**P1. 기존 32개 MCP 도구 중 `get_algorithm_research`에 `response_mode` 선택 추가:**

- `full` **기존 기본값 그대로**: 원본 response와 해시/체크포인트 포함. 기존 호출자를 전부 지원하며 응답 필드 삭제 없음.
- `compact` **명시 선택**: 실제 서버가 검증한 원본 응답에서 단지 전달용 JSON을 생성한다. `history`는 최신 1개만 보여 주고, 원래 전체 개수·마지막 `evidence_hash`·원본 전체 응답 SHA-256·읽기 모드·원장 미변경을 출력한다. `model_context`의 계획·진단 타입드 JSON schema, 선정된 부모, 거래/손실 출처, 정책, 기존 checkpoint token은 그대로 보존한다. 과거 관측의 *일부* 미리보기 리스트만 명시적 개수와 함께 축약한다; `avoid_retesting_identical_child_hashes`와 `exact_prior_parent_interventions`는 임의 절단하지 않는다.
- **최대 96 KiB 안전 한계**를 초과하면 **명시적 오류** `COMPACT_CHECKPOINT_UNAVAILABLE`을 반환한다. 조용히 다른 필드나 중요한 부모·계획 schema를 삭제하거나 FULL로 몰래 반환하지 않는다. `full`은 항상 다시 선택할 수 있다. 변환 함수 자체는 DB 읽기/쓰기 없이 동작하고, 기존 앱 내부 SDK는 MCP 서버 구현에 필요한 것이며 별도 Codex 모델 SDK 호출은 아니다.

**P2. 다음 GPT 행동·안전 재개 안내:**

- `AWAITING_PLAN → AUTHOR_AND_SUBMIT_PLAN`, `AWAITING_DIAGNOSIS → AUTHOR_AND_SUBMIT_DIAGNOSIS`, `INTERRUPTED → INSPECT_AND_EXPLICITLY_RESUME_IF_SAFE`, `COMPLETED/CANCELLED → NO_MORE_GENERATIONS`.
- 현재 `completed_generations`, 다음 세대 번호, 마지막 증거 해시, **변경하지 않은 원본 checkpoint token** 및 해당 제출 도구를 별도로 제공. 불확실한 쓰기/응답 유실 이후에는 항상 `get_algorithm_research` 재조회. 로컬 기억이 출처 증거가 되거나 서버 원장을 자동 진전시키지 않음. 추가 사용자 요청 없을 때 백그라운드 모델 호출 0회.

**P3. 모델이 고칠 수 있는 정해진 체크포인트 오류:**

- 기존의 계획 중복/동일체결/P2 위험/P3 의미 중복 수정 코드 유지. `P3_DIAGNOSIS_SEMANTIC_REJECTED`를 추가해 다음 연구계획이 중복일 때 **현재 토큰으로 새로운 진단 제안**이 필요하다는 정적 안내 제공.
- `recovery.next_step`, 전체/축약 재조회 모드를 오류 반환에 추가. 예외 본문, 민감정보, 원래 토큰은 사용자 응답으로 그대로 반환하지 않는다. 알 수 없는 실패는 `retry_same_checkpoint=false`; 진짜 새 세대나 모델 판단을 자동 생성하지 않는다.

## 실제 검증 범위

- 신규 `tests/integrations/test_chat_quant_compact_checkpoint_p1_p3.py`: 도구 32개 보존, 기본값 full/compact opt-in, 요청 스키마 변경 제한, 정확한 타입드 계획/진단 컨텍스트와 토큰·부모·증거 해시 유지, 무결성 원본 미변경, 68세대 합성 전송 스케일링, 알 수 없는 phase 또는 실주문/OOS 위험 거절, byte-budget 초과 거절, 실제 adapter get parity, 복구 오류 문자·토큰 비유출.
- 격리된 학술 fixture는 진짜 Quant 코어 테스트 백테스트/S7을 구동하지만 **ScriptedResearcher 테스트 작성 판단**이므로 실제 ChatGPT 신규 세대나 모델 비용 개선 증거가 아니다.
- 신규 `pytest` 7/7 PASS, 기존 MCP/학술/보안/복구 포함 확대 회귀 **71/71 PASS** (148.26s), `ruff check .` PASS, 변경 모듈 3개 `mypy` PASS, `git diff --check` PASS. 전체 저장소 pytest/mypy·실운영 GPT 턴·서버 배포 **NOT RUN**. **실제 68세대 서비스의 압축 byte 감소량, 유료 GPT token 절감률, 100세대 단일 채팅 완결은 아직 측정/증명하지 않았다.** 68세대 합성 history 성능 시험은 실제 68세대 GPT 문맥 품질 시험이 아님.
- 운영 서버는 여전히 보호된 기존 `/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021`, 기존 공용 고정 URL/기존 OAuth/기존 68/100 증거 DB/32 tools 고정. **이번 개발은 통합 개발 브랜치만 수정**; 프로덕션 MCP 재시작·배포·등록·토큰/원장/데이터 변경 없음.

## 채팅형 사용 예시 (개발 도구 배포 후)

1. 기존 `get_algorithm_research(session_id=..., response_mode="compact")` 조회, 정확한 `model_context` 출력 계약에 따라 이 채팅의 GPT가 **직접 판단**.
2. 현재 원장 `checkpoint_token`과 GPT 생성 `plan` 또는 `diagnosis`로 기존 제출 도구 호출. 쓰기 도구 응답은 축약되지 않음.
3. 응답이 모호하거나 오류가 발생하면 `get_algorithm_research`로 현재 단계와 head 재조회하고 **중복 집계 없이** 수정 계획만 같은 체크포인트에서 제출.
4. 채팅이 종료됐을 때 이 채팅 자체의 후속 모델 턴을 Quant/Moon MCP가 자동 생성할 수 없음. 여기의 변경은 **사용량/문맥과 재개 효율**을 높일 뿐, 무인 100세대 반복 제어 또는 ChatGPT 앱의 사용량 제한 해제가 아님.

## 잔여 및 다음 순서

1. 기존 원장 68세대 복제본에서 `full` 대 `compact` 실제 크기·hash·typed model_context·부모/S7 재조회·증거 정확성 비교. compact 실패 시 원인을 수정하되 과거 기록/증거를 버리는 식의 조용한 삭제 금지.
2. 현재 인증된 ChatGPT→Quant MCP 컨트롤러에서 기존 OAuth/URL 그대로 **배포 전 운영 재현 테스트**(32 tools ABI, 격리 원장/실계정 안전 조회), 명시적인 배포 승인 전 실제 서비스 변경 없음.
3. 사용자 호출 기반 GPT 1→3→10 유효 세대, 중간 실패·중단/재개, 메모리 누락·모델 토큰/한 턴 처리량 비교. 사용자가 새 발화 없이 다음 GPT 세션이 시작된다고 주장 금지.
4. 이후 SDK Fork에서 **별도 GPT 호출 없이 재사용 가능한** P3/P4 부모 일반화, S7 사전 품질, 비용/국면 검증 기능만 별도 분리 이식. 비용/통계 V05→T4→V01~V04→V06→V07의 최종 승인 순서는 유지.
