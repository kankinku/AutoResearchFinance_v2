# Quant [13/16] V06 주문 OFF·모의매매 KIS 접근 경계 검증

**검토일:** 2026-11-10 KST · Q04/Q15/Q20 · **개발 계약 테스트 완료 / 외부 paper API·실거래 실행 없음**

## 수행 범위와 실측
- 기존 `ResearchPermissions` / `KISPaperClient` / `KISPaperOrderClient` / `PaperTradingAdapter` / `SystemController`의 개발 계약만 검토. 기존 `mode.json`의 `selected_mode="paper"`, `orders_enabled=false` 조건과 런타임 스냅샷의 `orders_enabled=false` 일관성을 보존.
- Moon 작업공간에는 신규 실제 연구 QQQ 시세/운영 원장과 실제 GPT 10·100세대 결과가 없다. 구 G150 및 과거 전략 결과를 새 연구에 계승하지 않음. 실제 KIS 계좌 로그인·네트워크 요청·실제 모의계좌 주문·실계좌 주문·포지션 진입 **0건**. 합성 `RecordingTransport`와 `PaperTradingAdapter` 단위 테스트의 체결 수는 가상 체결 수일 뿐이다.

## 확인된 취약 경로 / RED
- 기존 `KISPaperOrderClient`는 실거래 KIS 호스트를 막았지만 조회 전용 `KISPaperClient` 생성자는 `PaperKISConfig(base_url="https://openapi.koreainvestment.com:9443", mode="paper")`를 **허용**했다. 해당 인스턴스에 나중에 `quote()` 등 인증 요청을 실행하면 실거래 주소에 앱 인증을 보낼 위험이 있었음.
- 기존 검사는 HTTP 비암호화 통신, 가상 KIS 호스트의 잘못된 포트, URL 내부 userinfo/쿼리/경로 우회, `PaperKISConfig` 직접 생성 후 `mode="live"`, 모델/직렬화 입력 `order_permission=None/0/""/[]` 같은 형태 검증도 포괄하지 못함.
- 새 부정 테스트가 실거래 URL에서 조회 전용 클라이언트 생성이 거부되지 않음을 **RED 재현**. 모든 위험 URL 테스트는 주입한 기록 전용 가짜 transport의 요청 횟수가 0인지 동시에 확인.

## 최소 GREEN 수정
- `integrations/kis/config.py::validate_paper_endpoint`에서 KIS 의도된 가상 서버 `openapivts.koreainvestment.com`과 `https`, 포트 `29443` 또는 기본 HTTPS, 경로·계정정보·쿼리·프래그먼트 없음, `mode`가 paper/demo/빈 값임을 검사. 실거래 호스트/HTTP/의심 URL을 실제 인증 요청 전 **즉시 거부**.
- 주입 mock 전송에만 인터넷으로 라우팅되지 않는 IANA 예약된 `.example/.test/.invalid` 시험용 도메인을 허용. 네트워크 `URLTransport`의 기본 경로는 **가상 KIS 호스트 외 거부**.
- 조회 `KISPaperClient`와 주문 분리 `KISPaperOrderClient`가 **동일 정책 함수**를 호출. 주문 전용 오류 형식 `PaperOrderError` 보존. 기존 모의계좌 체결·취소·미체결 확인 로직, 오류 매핑, 스로틀링, 실제 계좌 주문 OFF 정책 변경 없음.
- `validate_research_permissions`의 `order_permission is not False` 검증으로 falsy/미정 값이 '명시적으로 주문 권한 없음'인 것으로 오인되는 경로를 차단. `credential_ref`는 여전히 `None`만 허용.
- 코드 변경은 KIS 전송 경계에 한정. 새 API 키·사람 승인된 실주문 기능·OAuth 변경·실거래 엔드포인트 연결·DB 스키마·추가 전략/자동 거래 기능은 구현하지 않음.

## 실제 검증 결과와 한계
- KIS 격리/조회/모의주문/페이퍼 어댑터/시장 데이터 수집 mock/시스템 운영·거버넌스 확대 **97 PASS**.
- `ruff check .` **PASS**, KIS 변경 4개 파일 `mypy --follow-imports=silent` **PASS**, `git diff --check` **PASS**.
- 원본 운영 서비스의 실제 OS 프로세스별 자격증명 완전 격리, 외부 주문 API 인증, KIS 계좌/모의 거래 현장 검증, 주문 로깅/네트워크 캡처, 신규 GPT 생성 신호, 분산/수익성 성능 **NOT_VERIFIED**. 테스트 입력의 가짜 주문은 외부 요청이 아니다.
- 전체 `pytest -q -x -p no:cacheprovider` → **458 PASS, 1 FAIL** 후 첫 실패에서 중단. 기존 `tests/dashboard/test_fresh_original_dashboard.py::test_readonly_sqlite_bridge_matches_original_contracts`에서 2026-10-21 `state/moon-http/fresh-20261021/session-id.txt`가 현재 마운트에 없어 `FileNotFoundError`. 앞선 단계와 동일한 외부 역사 파일 의존. **전체 수트 PASS 아님**.
- **완료 범위:** V06 연구-only KIS 호출 경계 및 mock paper 세션 안전 테스트. **실제 paper 주문 관측 및 GPT 생성 신호 연계: 미실행**. 연구원 계정/주문 승인/실거래 기능 승격 **금지**.
- **다음 [14/16]:** V07 기술 안전/자율 진화/독립 경제성의 GO/NO-GO 세 단계 증거 분리와 전체 릴리스 검증. 미충족된 실제 GPT 및 OOS의 BLOCKED를 성공으로 처리하지 않음.
