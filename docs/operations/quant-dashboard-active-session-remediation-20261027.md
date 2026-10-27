# T4 Quant 대시보드 신규 N세대 연구 자동 인식 수정 (2026-10-27)

## 범위/승인

- 작업: T4-DASHBOARD-ACTIVE-SESSION-20261027. 사용자 요청: 추가 N세대 실행 시 대시보드가 신규 세션을 반영하도록 개선.
- 대응: Q02(자율 연구 현황), Q06(백테스트 피드백), Q08~Q09(불변 증거 및 지표), Q15(지정 N세대), Q16(사용자 보고), Q17(세대와 실험 구별), Q20(검증 단계 구별).
- 변경 가능 영역: 읽기 전용 연구 대시보드, 테스트, 운용 문서만. 기존 V05→T4→V01~V04→V06→V07 수행 순서 불변.
- 금지: Quant/Moon MCP URL·OAuth·실거래/실주문 권한·연구 이력·증거 해시·기존 엔진·부모 계승 로직·봉인 OOS·마켓 데이터 수정.
- 수락 기준: 기존 G94 100세대와 신규 50세대 동시 존재 시 UI가 신규 세션을 자동 식별, 이전 G94를 분리 보존, 세션 고유 Run ID, HTTP 새로고침/무재시작 갱신, 비인가 401, 독립 증거/성과 혼합 금지.

## 원인

- `scripts/fresh_research_dashboard.py`는 `LIVE_SESSION_ID`를 기존 100세대 `14626d55...`로 하드코딩하고, 새 세션의 ID를 요청별로 선택하지 않았다.
- API `snapshot()`이 SQLite의 `sessions`에서 해당 ID를 영구 선택하여 모든 5초 브라우저 폴링이 과거 100/100을 반복 표시했다.
- 두 유형(학술 GPT 세션, 고정 탐색 배치)의 대시보드 표시가 분리돼 있으며 `/api/research-batches/latest`는 GPT 자율 연구가 아닌 고정 파라미터 연구 원장이다.
- 별도 세션이 동일 세대 번호로 나타날 때 백테스트 식별자 `fresh-G#`가 충돌할 수 있었다.

## 해결

1. 연구 DB의 `sessions` 최신 등록 행을 **읽기 전용** 조회하여 현행 세션을 매 API 호출 시 자동 선택 (`_latest_live_session`). 마지막 등록 세션에 오류/미완료 등록이 있으면 오래된 세션으로 조용히 대체하지 않고 명시적 오류를 반환.
2. `snapshot(..., session_id=...)`는 **동일 LIVE 원장의 내부 신뢰된 요청**만 허용. 과거 G94/100은 `cohort=prior_mcp` 명시 요청에서 기존 `LIVE_SESSION_ID`로 조회. 과거 P5·historical·original API는 보존.
3. 응답에 정확한 `session_id` 추가; `archived_best`에 G94 원장의 별도 검증된 최고값/세대 표시. 프런트엔드 성과 상단에 분리된 이전 원장의 최고 결과를 표시. 세대별 그래프와 진행률은 현행 세션 것만 사용.
4. 각 백테스트 ID를 `fresh-<session-prefix>-G#`로 범위 지정. 동일 G번호라도 다른 세션은 다른 ID로 표시. OAuth 등 비공개 데이터 조회/변경 없음.
5. 신규 세션 시작 후 서버 재시작 불필요하도록 테스트 추가; 기존 원장 읽기 전용 및 증거 해시 정상 검증.

## 실측

- 수정 전: 8081/8082 모두 이전 `14626d55...`의 100/100 반환, 새 `3178d812...`의 50세대 연구가 DB에 있으나 화면 미반영.
- 운영 적용 후: 8081 `/api/status` 및 8082 `/api/status` 모두 `3178d812...`의 **45/50** 반환(검증 시점), `proof_chain_ok=true`.
- 8082 `/api/dashboard`는 새 세션 고유 `fresh-3178d812-G45` 및 45건의 최근 세대 반환.
- 8082 `/api/status?cohort=prior_mcp`는 별도 `14626d55...`의 100/100, G94 +206.81%, MDD22.67%, 증거 연결 검증 true 반환.
- 현재 신규 세션은 별도의 연구 계보이며 이전 G94의 100세대에 이어지는 합산 145세대라는 근거는 없음.
- 대시보드는 기존 supervisord의 자동 재시작으로 갱신됨. Quant MCP 8787 프로세스(pid 3314), 원래 URL/OAuth/주문 설정/프록시 설정 불변. nginx의 미인증 `/academic/api/status`는 HTTP 401 그대로.
- 변경 파일: `scripts/fresh_research_dashboard.py`, `scripts/fresh_original_dashboard.py`, `dashboard/static/fresh-performance.html`, `dashboard/static/fresh-performance.js`, `tests/dashboard/test_fresh_research_dashboard.py`, `tests/dashboard/test_fresh_original_dashboard.py`.

## 검증 및 미해결

- 추가 회귀 및 기존 대시보드 테스트: **21 PASS** (SQLite 이중 세션, 자동 선택, 세션별 ID, 무재시작 신규 인식, 이상 세션 fail-closed, 아카이브 및 원본 API).
- 전체 Ruff: PASS. 변경 Python 모듈 mypy: PASS. JS 구문 검사: PASS. `git diff --check`: PASS.
- 전체 mypy: **FAIL, 기존 다른 스크립트 16개에서 51건**; 수정한 대시보드 파일은 오류 없음. 기존 타입 오류를 작업 범위를 넘어 수정하지 않음.
- 전체 pytest: **INTERRUPTED** (시간 긴 통합 테스트에서 약 7분 4초 후 사용자가 기다리는 동안 장시간 점유를 피하고 종료). **715 PASS, 0 FAIL 관측**, 하지만 전체 수집 테스트 PASS는 **아님**. 마지막 실행 중이던 경로 `tests/integrations/test_gpt_research_batches.py:417`에서 KeyboardInterrupt 처리; 해당 테스트 자체가 실패했다고 해석하지 않음.
- 범위 추가 테스트: 거버넌스/서비스 Supervisor/실 MCP 세션 단위 31 PASS. 대시보드 회귀 21 PASS. 합산 성공 개수는 테스트 중복 가능성이 있어 고유 테스트 건수로 주장하지 않음.
- 실제 사용자 브라우저의 육안 검증: NOT RUN. 봉인 OOS, PIT 데이터 및 무인 모델 호출 검증: NOT RUN; 대시보드 조회 정상화와 연구 성과 입증은 별개.
- 코드 커밋 `c2ed88b`, 브랜치 `fix/quant-dashboard-active-session-20261027`, 원격 `origin` push PASS. 원본 100세대 G94 증거 원장 보존.
- 남은 개발 순서: T4 남은 GPT 독립 호출·재개 증거 및 원래 V05 검증 상태 계속 확인 → V01~V04 외부 독립 PIT/OOS → V06 paper-only → V07 별도 GO/NO-GO. 이 패치는 원래 계획 변경이 아님.
