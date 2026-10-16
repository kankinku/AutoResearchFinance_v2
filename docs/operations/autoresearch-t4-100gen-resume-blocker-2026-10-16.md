# T4 / 4단계 — 100세대 연구 이어하기: 11 완료·12 진단 대기

기준: 2026-10-16 UTC/KST. 20문답·동결된 범위 및 단계 순서 불변.

- 기존 연구 세션 `a84a100b15a242269b554282b01d91c9`, 동일 QQQ 2020~2025 비PIT 원본, 현재 100세대 요청 유지.
- 11세대 `t4_100_g011_sma_regime_low_churn`: typed Plan/백테스트 99 거래, 개발 수익률 35.71%·최대낙폭 26.50%; 거래 손실 ID 기반 가설/대조실험 S7 저장. 실험 거래 수 -38, `DIRECTION_MATCHED_DEVELOPMENT_ONLY`. 원세대 SHA `ce413c6fa0e80a36930cd890885b8ca099c674dbf0c78068b787a803dfe1f654`. 이는 PIT/OOS 실현 수익 증명이 아니다.
- 12세대 `t4_100_g012_risk_persistence`: typed Plan·원 백테스트는 실행(59 거래, 개발 수익률 45.21%, 최대낙폭 27.13%), 단 진단 제출이 OpenAI 도구 안전 검사에 반복 차단. 상태 직접 조회 `completed_generations=11`, `checkpoint_phase=AWAITING_DIAGNOSIS`. **12세대는 미완료, S7 미실행.** 안전 거부를 우회하거나 12세대를 완료로 계산하지 않음.
- 모델 독립 인증 `false`, 실주문 OFF, 기존 MCP 32개/URL/OAuth, 운영 `b50b4c7`/launcher `6e09457` 불변. 코드 변경 없음.
- 다음: **동일 세션 기존 12세대 진단 승인→S7 측정** 후 13~100세대 계속. 이 요청이 여전히 차단되면 BLOCKED 보고. 독립 수익성 판단·PIT/OOS는 뒤 별도 단계.
- 검증: 연결된 MCP로 11세대 S7 원본 해시 일치·12세대 대기 상태 직접 확인. 새 코드가 없어 이번 턴 T3 전체 재실행 안 함(직전 1655 PASS 기록 유지).
