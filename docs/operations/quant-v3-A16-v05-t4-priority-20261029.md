# Quant V3 A16 — V05 비용 원장 강화와 T4 280세대 연결 원장 검증

2026-10-29 KST · 연구용 별도 브랜치 `research/v3-v05-t4-priority-20261029` · 기준 A15 `3a75a43`.

## 사용자 범위
사용자는 **V05와 T4만 진행**하도록 승인했다. 별도 ADR `docs/decisions/2026-10-29-v05-t4-now-other-v-stages-deferred.md`. V01~V04/V06/V07은 **보류(미실행)**, 제거 아님. 운영 main/OAuth/고정 MCP URL/기존 원장/2026 sealed OOS/실주문 기능 불변.

## V05 — 결함 재현과 수리

기존 `audit_development_economics`는 체결가·수량·명목금액·비용이 내부적으로 맞고 총비용/자산곡선 해시가 맞으면 통과했다. 따라서 매수 하나의 수량·명목금액·수수료를 각각 절반으로 바꾸고 보고 총비용을 맞춰도 **원래 자산곡선과 체결기록이 실제로 일치하지 않는데 기존 검사를 통과**하는 결함을 TDD로 재현했다.

프로텍티드 `core/backtest` / `core/costs`를 변경하지 않고, V05 연구 진단기에만 모든 봉을 순서대로 **현금·보유주식·비용을 실제 체결기록으로 독립 재계산하여 일별 자산곡선과 비교**하는 자기금융(self-financing) 감사를 추가했다. 기록과 다른 매수, 공매도/과도한 현금 인출, 순서 이상, 자산 가치 조작을 연구 감사 단계에서 거절한다. 통과 결과에는 `self_financing_trade_equity_reconciled=true`가 들어간다.

신규 2 테스트는 수정 전 **2 FAIL**, 수정 후 **V05 전체 18 PASS**. 수수료/슬리피지 모델·StrategyIR·주문·결정 정책은 변경하지 않았다. 기존 비용 스트레스 2배 계산은 거래량 고정 proxy로, 주문 호가·시장 충격·진짜 실행 가능 용량/공식 독립 통계 유의성은 검증하지 않는다.

## T4 — 현재 원래 인증된 MCP 원장 감사

- 독립 Academic GPT 체크포인트의 원본 세션을 `get_algorithm_research(response_mode='full')`로 조회. 상태 **COMPLETED, 280/280**(2026-10-27 문서의 100/100 이후 추가 연구 포함).
- **실제 280개 세대 원본**, generation 1~280 연속 **누락 0**, 인접 증거 해시 링크 **279개 모두 일치**, `plan_hash`/`strategy_hash`/`audit_hash`/`evidence_hash` 누락 0, 입력 데이터 해시 불일치 0, 서로 다른 알고리즘 의미 해시 **280개**, 텍스트 분석+진단 해시 누락 0, 실험 가설 누락 0.
- Gateway 원장 요약 `proposed_hypotheses=280`, `tested_hypotheses=280`; 이는 Gateway가 생성한 280개 S7 측정 건수를 의미하며 독립 경제적 우월성은 입증하지 않음. 보고서 `docs/operations/quant-t4-g280-readonly-chain-audit-20261029.json`으로 보존.
- 모델 컨트롤러 `authenticated_chatgpt_mcp_client`, 실주문 false, `real_model_connection_verified=false`, `model_autonomy_verified=false`. **채팅 GPT가 도구를 호출하고 세대 진단을 작성하는 방식**으로 완료된 기록이다. 외부 provider model 호출이 자동으로 280번 수행되었다는 의미가 아니다.
- 기존 공정 비교는 GPT 10 / Random 10 / Local 10에서 개발 수익률 중앙값 19.655% / 4.233% / 30.997%, 특히 Local > GPT. 후보 정보량·시간·세대 적응 예산 불일치 → **GPT 경제적 진화 우월성 미입증**. 원본 후보/추가 자율 연구 원장을 변경하지 않음.
- 본 A16은 이미 완료된 280세대를 10세대 신규 실행이라고 세거나 독립 OOS·PIT·실거래·추가 신규 GPT 세대를 만들어내지 않음.

## 후속 T4 조건

다음 증빙으로는 완전 독립 모델 호출 출처와 실제 동일 예산/동일 기회·사전등록 GPT 대 Random/Local의 세대 간 개선률 재검증이 필요하다. 현행 채팅형 MCP 루프 자체의 280세대 계보는 일관되지만 *무인 자동진화 인증*은 여전히 미완료다. 승인된 V05/T4를 제외한 다른 V 단계는 시작하지 않는다. 정식 Moon 릴리스 게이트는 기존 `uv` PATH·whole Mypy 이슈로 별도 차단(프로덕션 배포 금지).
