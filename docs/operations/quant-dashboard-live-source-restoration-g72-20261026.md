# Quant 실시간 대시보드 복구 및 G72 연구 검증

**일시:** 2026-10-26 KST, 현재 운영 Quant 연구. **사용자 지정:** Quant=현재 ChatGPT 채팅+Quant MCP; SDK=보존 중인 PythonSDK Fork.

## 실제 장애와 확인 증거

- 대시보드 웹서버/인증/포트 자체는 정상. 인증 없이 `127.0.0.1:2999/academic/`은 **HTTP 401**로 의도대로 로그인 보호되고, 내부 `8081`, `8082` 상태/API는 **HTTP 200**이었다.
- **주원인:** `scripts/fresh_research_dashboard.py::snapshot()`이 `P5_STATE`(별도 오래된 연구 28/100세대)를 LIVE_STATE보다 우선 선택해, 실시간 대시보드의 기본 `/api/status` 및 `/api/dashboard`에서 **28세대**를 보여 줬다. 사용자의 운영 채팅형 Quant 원장은 이미 **71/100**이었다. `?cohort=prior_mcp`에서만 진짜 LIVE 71세대가 보였다.
- 화면 자동 갱신은 이미 `dashboard/static/fresh-performance.js`에서 `setInterval(refresh,5000)`으로 구현되어 있었다. **주기적 갱신이 오래된 소스를 계속 읽는 문제**였으며 새로고침을 추가하는 것으로 고칠 수 없었다.
- 연결 UI가 GPT 입력 `AWAITING_PLAN`을 "연구 중단" 또는 "연구 프로세스 미실행"으로 오인하도록 되어 있던 기존 WIP도 함께 정리하여 **GPT 계획 대기/진단 대기**를 정확히 안내한다. 이는 별도 백그라운드 모델 실행을 시사하지 않는다.

## 수정 및 안전 경계

1. 기본 LIVE 우선: 명시된 현재 ChatGPT Quant 세션 `14626d55fb2b461faa485df911920071` 원장의 SQLite를 우선으로 읽는다. LIVE 파일이 없을 때만 격리 P5/기존 연구를 대체 자료로 선택. LIVE 파일이 존재하지만 검증이 실패하면 역사 데이터로 조용히 대체하지 않는다.
2. 과거 P5 28세대 원장: 별도 **읽기 전용** `/api/status?cohort=p5` 유지. 과거 G453~G552(`cohort=historical`), 이전 보존 원장(`cohort=original`)도 유지. `cohort=prior_mcp` 기존 호환 별칭은 현재 LIVE를 계속 가리킨다.
3. 기본 대시보드 화면의 제목과 보존 원장 링크를 실제 상태에 맞게 수정. URL `/academic/`·`/quant-research/`와 nginx HTTP Basic 인증, Cache-Control no-store, OAuth/Quant MCP/32도구, 채팅용 서버 8787은 **변경하지 않음**.
4. 읽기 전용 SQLite `mode=ro`/`PRAGMA query_only=ON`, 주문 OFF, 독립 OOS 잠금 그대로. 외부 SDK 모델 호출 0. 기존 PHP/JS/원장 데이터 덮어쓰기 없음.

## 확인 결과

- 기존 2개 대시보드 프로세스(8081,8082)만 종료 후 **기존 supervisord가 자동 재시작**. 재시작된 8081·8082의 `/api/status`가 **현재 71/100 → 72/100**, `proof_chain_ok=true`, 최신 원장 `e65c63940e4a…`와 `AWAITING_PLAN`을 실시간 출력했다.
- 새 **G72**는 현재 ChatGPT가 부모 G60의 RSI 하한 필터 `>40 → >45`를 단일 가설로 설계·제출했다. Quant 개발 백테스트 + GPT 진단 + S7 대조실험 후 공식 원장 72/100 완료. 개발 수익률 **+65.30%**, MDD **10.33%**, 완료 거래 **56건**. G60 부모: 수익 **+66.65%**, MDD **10.33%**, 거래 59건. S7 RSI 조건 `>45 → >43` 대조 결과 예상대로 거래 수 **+2건**; 이는 인과/OOS/실수익 증명 아님.
- G72의 공식 세대 증거 해시 `e65c63940e4ad04f37af80ebb480603158f5b21d6ed073695489e757c3c7806b`. 8081 및 8082 모두 해당 해시 prefix로 동기화되었음을 **실제 HTTP GET**으로 확인. 8082의 `/api/dashboard` 또한 공식 현재 세대의 기록 **72건** 반환.
- `pytest -q tests/dashboard/test_fresh_research_dashboard.py tests/dashboard/test_fresh_original_dashboard.py`: **14/14 통과**. 신규 테스트: P5 복제 파일이 존재해도 LIVE를 기본으로 고르는지, running dashboard HTTP 서버가 재시작 없이 SQLite의 신규 세대를 다음 요청에 읽는지. 전체 `ruff check .` PASS, JS `node --check` PASS, `git diff --check` PASS.

## 이후 점검

- 실제 개인 브라우저에서 `https://project-moon.taild689f9.ts.net/academic/` 접속 시 기존 HTTP Basic 인증을 거쳐야 한다. 자격증명을 채팅이나 로그로 노출하지 않는다. 외부 브라우저 렌더링/사용자 세션 화면 자체는 직접 확인한 것으로 주장하지 않는다.
- `8081`과 `8082`는 supervisor가 시작·복구하는 프로세스이고 nginx에서 `/academic/`은 8082로 보낸다. 이 연결은 다시 재시작해도 LIVE 최우선이며 P5 별도 보관을 유지한다.
- 사용자의 기존 SDK Fork, 별도 Star 프로젝트, Quant 주문 권한, OOS 봉인, OAuth/URL, 다른 대시보드 백업은 변경하지 않음.
