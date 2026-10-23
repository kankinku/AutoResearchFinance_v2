# Quant T4 — P2/P3 후속 개선, 2026-10-24

## 완료 범위

기존 G452/G552, OAuth, 대시보드, S2/S7 및 비용 모델은 변경하지 않았다. GPT 연구 세션 14626d55fb2b461faa485df911920071만 부모 포트폴리오 V2에 선택적으로 참여하도록 했다. 실제 모델 자동 호출 권한과 유료 API는 추가하지 않았다.

## P2 실험: 정식 부모와 S7 자식의 공동 평가

실행 원장 5/100을 읽기 전용 SQLite 온라인 백업으로 두 번 복제했다. 첫 복제에서 기존 G6 부모 선택은 그대로 유지됨을 확인. 두 번째에서만 G6 부모 핀을 삭제한 후 V2 정책을 모의 적용했다. G2 정식 세대 원본(+91.12%, MDD 21.36%)을 비롯한 3개 counted 후보와 S7 자식 3개, 총 6개 후보가 실제 체결·비용·위험 replay를 통과했다. 3개 다목적 계열 [G2, G1, G4]을 선택했다. 그중 G6에 해당하는 결정적 로테이션은 G4 S7 자식(+55.57%, MDD 15.95%)을 선택했으며, 이는 최고 수익률 선정이 아니라 다목적 탐색 로테이션임을 명시한다.

## 스코프를 제한한 실제 활성화

integrations/codex_mcp_core.py가 QUANT_MCP_PARENT_PORTFOLIO_V2_SESSION_ID의 정확한 32자 hex와 요청 session_id 일치 여부를 검증한다. scripts/run_quant_moon_http.sh가 state/moon-http/research/config/parent-portfolio-v2-session-id라는 비밀정보가 아닌 별도 운영 설정 파일에서 해당 값만 읽는다. 미지정된 세션과 신규 세션에는 기존 정책 적용. 기존 parent_selections에 이미 기록된 G6 핀은 변경하지 않고 미래에 새로 선정할 때만 V2를 적용한다. SQLite 핵심 세 파일의 백업은 state/moon-http/operator-backups/t4-scoped-parent-v2-pre-20261024 아래 저장했다. 변경 코드 commit 650b8ea로 Github 푸시.

Quant 전용 8787 프로세스만 재시작한 후 설정이 실제 프로세스에 반영된 것을 확인했다. 기존 인증 HTTPS Quant 경로는 비인증 401, 대시보드와 Moon health는 200 응답. GPT 원장은 여전히 5/100 AWAITING_PLAN, 이전 G6 선택 해시 및 마지막 evidence SHA 그대로였다.

## 실제 ChatGPT GPT G6 종단 검증 (복제본 아닌 실제 실행)

ChatGPT가 기존 G5 S7 부모 기반의 신규 normalized_atr_percent(20일) 0.035 미만 volatility regime 조건을 신규 등록 계산기로 생성 및 제출, 실제 S2는 +80.9519%, MDD 19.5497%, 청산 71건, 검증된 다른 체결(143 이벤트 대 부모 147). 손실 거래 307289d93a03-T-000138 및 진입/청산 결정 ID를 근거로 GPT가 ATR 조건만 제거하는 S7 가설을 제출했다. 원래 G6 최종 자산 18095.19달러, S7 필터 제거 18435.32달러, 체결 143대147; 진단 및 S7 해시 저장. 실제 6/100 세대 커밋 SHA 380302c4d3c3f6614bc2d64d628dcb755a93a0bf360447b7d96c6125d87b6b71. 다음 G7의 V2 부모는 COUNTED_GENERATION G2 원본, 개발 총수익 +91.1204% 및 MDD 21.3605%로 실제 선정됨. G6의 개발 성과는 QQQ 매수 보유 대비 열세이고 PIT/OOS 승인·자율 모델 출처 증명은 아님.

## P3 상태

기존 P3InheritedCheckpointAutopilot은 ResearchModel.propose 콜백을 제공받으면 계획, S2, 진단, S7, 다음 세대와 모델 결과 receipt 해시 체인을 반복한다. INHERITED_FEATURE_ 접두어 오류를 세대 소비 없는 재시도 대상으로 보완하고 FakeProvider 회귀 시험을 추가했다. 새 자동 호출 공급자를 만들거나 모델 토큰을 발급하지 않았다. 이 호스트에는 codex, claude, gemini, ollama CLI가 설치되어 있지 않으며, MCP OAuth는 서버가 ChatGPT를 역방향 호출할 권한이 아니다. 따라서 무인 100 GPT 세대는 아직 미완료다. 유료 모델 API는 사용하지 않았으며 명시적 비용·권한 승인 없이 사용하지 않는다. 실제 GPT는 본 대화에서 계획과 진단을 작성해 MCP 도구로 제출했다.

## 검증과 보존

69개 관련 pytest, 전수 Ruff, 변경 소스 Mypy, launcher bash -n 모두 통과. 7개 새 스코프 test와 1개 P3 retry test를 포함. 실제 대시보드 6/100와 원래 G452 452/452 및 G552 552/552 모두 read-only API proof_chain_ok true. 원래 G452/G552 마지막 SHA, SQLite integrity_check 모두 일치. live orders=false, independent_oos_approved=false. 진행률은 GPT 6/100으로만 증가. 별도 규칙 기반 100/100 실험은 합산하지 않는다.

## 다음 기술적 차단점

P3 무인 연구는 승인된 실제 모델 추론 공급자의 역호출 경로를 확보한 후에만 실행 가능하다. 그전에는 채팅 모델이 MCP 제출을 직접 수행하는 방식으로 추가 세대를 검증할 수 있으며, 이를 서버 내부 무인 진화로 표기하지 않는다.
