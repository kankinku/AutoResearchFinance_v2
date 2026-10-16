# T4 — Quant Autoresearch localhost 연구 현황 모니터

기준: 2026-10-16 KST/UTC. 사용자 신규 요청으로 추가하는 **읽기 전용 진행 상황 화면**이며 원래 20문답 Q02/Q09/Q15/Q16/Q17, 확정된 T4 연구 순서를 변경하지 않는다.

## 실제로 보여주는 항목

- 기존 GPT MCP 100세대 연구를 포함한 모든 연구 세션 선택, 요청/완료/남은 세대, 3초 단위 브라우저 갱신.
- 원장에 기록된 정확한 상태: RUNNING(단 작업자 heartbeat를 입증하지 않음), AWAITING_PLAN(다음 입력 대기), AWAITING_DIAGNOSIS(진단 입력 대기), INTERRUPTED(중단), CANCELLED, FAILED, COMPLETED. **대기는 실행 중이라고 표시하지 않는다.** 호스트에서 차단된 요청은 원장에 남지 않을 수 있으므로 차단 원인을 임의 추정하지 않는다.
- 현재 모델은 진단 대기 시 다음 세대의 미커밋 AlgorithmPlan ID만 표시하고, 그 단계의 손익 수치를 가짜로 부여하지 않는다. 최신 완료 세대는 별도 표시.
- 개발 데이터에서 관측된 최고 **누적 수익률 후보** 및 최고 Sharpe 후보를 구분. 각 세대별 수익률, CAGR, MDD, Sharpe, Sortino, Calmar, 승률, 거래 수, 회전율, Profit Factor, 노출 비중, S7 측정 여부를 그대로 제공. 원본 비율은 화면에서 퍼센트 단위로 변환한다.
- 수익률/MDD 세대별 추이 그래프와 최근 평가 내역. 이는 **각 전략을 똑같은 과거 개발 구간에서 실행한 결과**이지 한 계좌의 시간 순 누적 자산곡선이 아니다.

## 실행 방식

기존 로컬 페이퍼 대시보드: FastAPI 메뉴 **GPT 연구 모니터** 또는
http://127.0.0.1:8080/academic

기존 연구 DB가 기본 state/academic-gpt-checkpoints가 아니라면 대시보드 실행 전에 환경변수 QUANT_ACADEMIC_CHECKPOINT_DIR 을 실제 academic-gpt-checkpoints 디렉터리로 지정한다.

독립 연구 모니터: Moon 저장소 루트에서 다음을 실행한다.

  .venv/bin/python -m dashboard.academic_run --checkpoint-dir /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/research/academic-gpt-checkpoints --host 127.0.0.1 --port 8081

같은 **실행 환경**의 브라우저 주소: http://127.0.0.1:8081/

중요: Moon 컨테이너/원격 서버의 localhost는 사용자 Windows PC의 localhost와 다르다. Windows PC에서 직접 열려면 별도로 승인된 SSH 로컬 포트 포워딩 또는 루프백 전용 호스트 네트워크 경로가 필요하다. 외부 0.0.0.0 바인딩 및 무인증 인터넷 공개는 허용하지 않는다. 로컬 서버 실행만으로 사용자 Windows 브라우저 도달 가능을 주장하지 않는다.

## 원장 보안과 안전

- SQLite cycles.sqlite 및 gateway.sqlite를 mode=ro, query_only=ON으로 열고 사용 후 닫는다. DB·토큰·계좌/원본 거래 내역·시장 가격·봉인 OOS를 쓰거나 외부 공개하지 않는다.
- 매 세대 원본의 evidence SHA 체인, 각 S7 결과 보고의 내용 해시·세대 해시·가설 ID를 검증한다. 해시 불일치 시 503으로 실패를 알리며 성과를 표시하지 않는다. 실험이 아직 없을 때는 S7_NOT_MEASURED로 별도 표시.
- 모델 식별자, 세대, 이미 계산된 지표 외의 상세 프롬프트·승인 토큰을 API에 포함하지 않는다.
- localhost만 바인딩, 별도 TrustedHost 및 CSP, GET-only. START/STOP/ORDER/RESUME/TRADE 경로가 없고 연구 도구를 호출하지 않는다.
- 연구의 출처는 NON_PIT DEVELOPMENT QQQ; PIT/OOS/독립 실제 수익성과 실거래 GO가 아님. 반환 결과에 orders_enabled=false, profitability_verified=false, independent_oos_approved=false를 명시.

## 적용 범위 / 남은 작업

이번 기능은 별도의 localhost 표시 계층이며 기존 Quant MCP URL, OAuth, 32개 도구 및 운영 pinned SHA b50b4c7을 수정하지 않는다. 기존 GPT 연구 세션 a84a100b15a242269b554282b01d91c9는 11/100 완료, 12세대 진단 입력 대기 상태 그대로 유지한다.

검증: FastAPI 스키마 및 실제 연구 원장 조회, 미커밋 모델/최고모델·S7 증거 검증, 고의 변조 차단, INTERRUPTED 우선 표시, 비인가 호스트 거부, 별도 모니터 및 기존 페이퍼 화면 연동, JS 문법 및 기존 대시보드 회귀 검사를 실시한다. GitHub 별도 브랜치에 이 모니터 변경을 기록한다.
