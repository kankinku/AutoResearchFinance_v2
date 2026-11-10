# Quant 모의주문 미체결·부분 체결 정합성 — [5/16] Task 4

**작성:** 2026-11-10 · **대상:** `integrations/kis/paper_orders.py`, `tests/integrations/test_paper_orders.py`, `tests/cli/test_paper_order_smoke.py` · **상위 목표:** Q04/Q09/Q11/Q15/Q20, V05/T0 사전 안전성.

## 문제와 해결

- 기존 구현은 매수 10주 중 2주 체결만 관측해도 즉시 2주 매도를 제출했다. 나머지 매수 8주가 뒤늦게 체결될 수 있으며, 매도 부분 체결 후 잔량이 남아도 계좌 잔고가 일시적으로 원래 값이면 `FLAT`을 반환할 수 있었다. 같은 주문번호의 중복 체결 레코드를 합산하는 오류도 있었다.
- **변경된 상태 계약:** 각 매수·매도 주문의 체결 결과가 요청 수량 전부이거나 미체결 잔량 `0`이 명시 확인되기 전에는 완료로 간주하지 않는다. 잔량이 남거나 상태가 불명확하면 가상 미국 주문 정정·취소 엔드포인트 `/uapi/overseas-stock/v1/trading/order-rvsecncl`, 모의 TR `VTTT1004U`로 **잔량 전체 취소**를 요청한다. 취소 접수 응답만으로 성공을 확정하지 않고 이후 주문체결내역을 다시 조회해 `nccs_qty=0` 혹은 요청 수량 전부 체결을 확인한다.
- 매도 전에 **현재 보유 수량 = 시작 보유 수량 + 확정 매수 체결 수량** 일치를 확인한다. 이 조건이 확인되지 않으면 추가 주문을 생성하지 않고 `UNSETTLED`를 반환한다. 매도 잔량도 동일 방식으로 취소·확인하며, 마지막 계좌 조회에서 시작 수량으로 복구되고 미체결 주문이 없을 때만 `FLAT`을 반환한다.
- 취소가 거절되거나 잔여 수량이 불명확한 경우에는 `UNSETTLED`로 안전하게 중단한다. 기존 `BUY_NOT_FILLED`, `SELL_NOT_FILLED`, `NOT_FLAT`, `FLAT` 결과 스키마 유지. 사용자 CLI `paper-order-smoke`는 `FLAT`이 아닐 때 종료 코드 `2`로 반환한다.
- 같은 주문번호로 반복 반환되는 누적 체결 레코드를 합산하지 않고 관측된 최대 체결 수량을 채택하며, 결과가 모호한 경우 더 많은 수량을 임의로 매도하지 않는다. 실제 API가 개별 체결만 제공하여 총 체결량을 확정할 수 없으면 `UNSETTLED`/잔고 불일치로 **fail closed** 한다.
- 라이브 KIS 호스트·실거래 모드 차단은 기존 그대로 유지. `PaperRoundTripResult` 구조, 주문 TR·OAuth 설정, MCP 연결, 거래 활성화 정책을 변경하지 않았다.

## 재현·검증

- **RED 재현:** 10주 매수 중 2주만 체결·8주 미체결인 모의 응답에서 기존 코드가 취소 없이 매도를 먼저 보내 `SELL_NOT_FILLED` 상태가 됨. 새 테스트는 취소 제출·미체결 0 확인·잔고 확인 이전의 반대 주문을 허용하지 않는다.
- **GREEN:** 부분 매수 취소 후 매도, 취소 중 늦게 체결된 추가 1주 반영, 부분 매도 취소 후 잔고, 취소 거절 및 미완료/미확인 잔량 차단, 동일 주문 중복 체결 데이터, 취소 후 잔고 불일치, 실거래 호스트 차단, 무체결 매수의 취소 확인, CLI 미정산 상태의 실패 코드 등 `RecordingTransport`/가짜 응답만 사용.
- **외부 문서 근거:** [한국투자증권 공개 샘플의 해외주식 정정취소](https://github.com/koreainvestment/open-trading-api/blob/main/legacy/Sample01/kis_ovrseastk.py)에서 모의 주문 취소 URL·TR `VTTT1004U`, 원주문번호·잔량 전체 취소 방식을 참고. **실제 가상 계좌에서 `nccs_qty` 필드 반환 여부, 취소 API 수락, KIS 체결내역 페이징 등은 E2E 미검증**. 필드가 없으면 성공을 추측하지 않고 안전 실패한다.
- **운영 제한:** 모든 주문/취소 테스트는 주입한 RecordingTransport가 처리했으며 실제 KIS 엔드포인트 전송·보유 자산 변경·주문 승인/가동·실거래 요청 **0건**. 과거 G1~G150/기타 실험 성과·부모·기억의 새 연구 계승을 금지한 2026-11-10 초기화 ADR 유지.

## 이번 작업의 실제 검사 결과

- `pytest -q -p no:cacheprovider tests/integrations/test_paper_orders.py tests/cli/test_paper_order_smoke.py` → **18 PASS**.
- KIS 격리·주문·모의 어댑터·CLI·범위 거버넌스 6개 테스트 파일 묶음 → **38 PASS**.
- `ruff check .` → PASS, `mypy integrations/kis/paper_orders.py` → PASS, `git diff --check` → PASS.
- `pytest -q -p no:cacheprovider tests/integrations tests/cli tests/governance` 확대 테스트는 약 26%까지 진행 중 **실패 1건 표시** 후 명령 제한시간 200초로 **INTERRUPTED**, 실패 테스트 이름/원인은 미확인. 따라서 통합 전체 PASS라고 주장하지 않는다. 전체 스위트도 이번 단계에서 별도로 완주하지 않았으며, 선행 작업에서 구 2026-10 세션 파일 의존 대시보드 실패가 있었음.
- 코드/테스트/진행표는 별도 구현 브랜치에서 작성, 기존 메인 배포 및 실제 KIS 가상 주문 E2E 검증은 하지 않음.

## 남은 조건

실제 가상 KIS 서비스에 연결한 **사용자 승인 하의 별도 검증**이 없으므로 이 결과만으로 운영 paper-only 자동 왕복 거래의 완전한 종단 안전성을 입증할 수 없다. 인증·운영 키·실거래 설정 변경은 승인되지 않았다. 실전 계좌 실행과 독립 수익성 증빙은 더더욱 해당하지 않는다.
