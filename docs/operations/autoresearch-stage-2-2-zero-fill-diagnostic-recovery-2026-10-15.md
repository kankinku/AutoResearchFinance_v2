# Quant Autoresearch — [2-2 / 전체 5단계] 무거래 전략 GPT 진단 데드락 수정 (2026-10-15)

## 실제 연결된 ChatGPT MCP 검증

현재 ChatGPT에서 기존 Quant MCP 연구 도구 32개 사용 가능, workspace READY, 페이퍼 모드, orders_enabled=false.

- 세션 43b4715cb859403b94387fff207a7403: GPT 작성 SMA 전략 → 실데이터 QQQ 1,508봉 Plan 제출 → 60건 실제 개발 백테스트 거래·손실 ID 보고 → 진단 제출 → 원본 60건 대조 변경 18건 → S7 재조회 동일 기록 해시로 완료. 수익성·독립 OOS 승인 아님.
- 별도 10세대 세션 cb4185adb0e84a07a4c1f4fa56b28a99: G1 EMA/SMA 연구(거래 80건·개발 수익률 +75.52%); 이탈 가설 실험은 오히려 거래 103건으로 증가하여 DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY. G2 SMA/Range-low reclaim Plan은 유효하나 실제 거래 0건. 서버가 AWAITING_DIAGNOSIS로 들어가면서 execution_samples와 loss_cases 모두 빈 값으로 제공, 그런데 DiagnosticResponse에는 observed_ids 최소 1개가 요구되어 진행 불가. 허위 거래 ID 작성 금지. 운영 MCP는 아직 고치지 않았으므로 해당 세션은 G1 증거 보존 후 CANCELLED. **10세대 완주 아님**.
- 실제 ChatGPT 툴 직접 사용과 별도 모델 API 인증은 다르며, 서버 real_model_connection_verified 플래그는 false 상태 유지.

## 수정 기능 및 안전장벽

research/llm/diagnostic_research.py: Audit 원장의 full decision trace_hash로 검증되는 audit.decisions 중 실제 비실행 판단만 선택해 0-fill인 경우 최대 12개 샘플(ID, UTC signal_time, 당시 조건과 indicator values)을 모델 context의 non_execution_decision_samples에 추가. 해당 데이터에서만 검증된 관측 ID를 참조하는 진단 가설 허용. 가짜 체결·거래·수익 또는 사후 인과 인증 금지. 변조된 context, 허위 ID, 다른 부모, 비승인 전략 변경은 거부.

원래 거래가 하나라도 있는 전략은 컨텍스트 본문과 audit.llm_packet, trace_hash, 과거 세대 증거를 변경하지 않는다. 따라서 기존 MCP 요청·원장 호환과 sealed OOS/실거래 비활성 유지.

## 검증 및 후속

테스트: synthetic 무거래 연구에서 감사 결정 ID 제공, 위조된 ID/변조된 컨텍스트 거부, 기존 거래 전략 구조 유지. 로컬 MCP 2세대 수직 통합: 0-fill Plan → 승인된 무진입 observation diagnosis → S7 실험 자동 평가 → 다음 일반 계획과 진단 완료. 관련 테스트 28개 및 Ruff/Mypy 통과. 전체 suite는 최종 실행 결과 별도 확인.

기존 Quant MCP URL/OAuth, 실제 런타임 프로세스/원장, 봉인 OOS, 거래 주문 차단 불변. 별도 개발 브랜치만 변경·운영 미배포. 새 코드를 운영에 적용하려면 기존 URL 유지·독립 QA·배포 심사, 이후 GPT 10세대 실제 재시험과 failure/recovery, 예산/효과 및 동일 데이터 반복 과적합 위험 평가 필요. 1-1 추가 Nasdaq 수집 및 1-2 실제 PIT 외부 증거도 별도 미완료.
