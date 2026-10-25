# T4 — 등록 피처의 출력 단위 검증·거래 0건 사전 차단 및 P5 G28 연구

- 날짜: **2026-10-25 KST**
- 범위: 기존 확정 **T4(S4/S5)**, Q02·Q05·Q06·Q07·Q08·Q09·Q11·Q15·Q17·Q20
- 상태: **feature unit advice/guard PASS, opt-in non-empty candidate gate PASS, 실제 GPT G28 COUNTED & S7 PASS**.
- 원본 코어/backtester·MCP/OAuth/고정 URL·실주문/OOS 경계 변경 없음.

## 1. 지난 G21~G27의 실측 결함과 직접 대응

P5 G25/26의 Schaff Trend Cycle(STC) 값에 0~100 척도 조건을 사용해 각각 360번 청산 및 거래 0건을 발생시켰다. 그러나 기존 등록된 Python calculator는 `schaff_trend_cycle` 호출을 `_percentile(_macd(...), lookback)`로 계산한다. **이 저장소의 반환 범위는 [0,1]**이다. 유명한 지표명이나 외부 제공자의 0~100 표기만으로 이 코드의 내부 임계치를 판단하면 안 된다.

- 신규 `research/llm/t4_feature_units.py`: 등록된 `schaff_trend_cycle`의 **확인된 내부 단위**와 공식 계산기를 기반으로 계획 컨텍스트에 `feature_unit_guidance` 제공. 직접 확인되지 않은 다른 지표는 **UNKNOWN_DO_NOT_ASSUME**. 전체 신규 지표를 임의로 0~1이라고 분류하지 않음. 미래 누출 데이터·OOS 지표값을 읽어 threshold 튜닝하지 않음.
- `application/academic_checkpoint_service.py`의 `_context`: 기존 P4-S7 opt-in 세션의 **미래 계획 모델 컨텍스트**에 단위 설명 추가. 완료 세대, immutably signed 진단 S2 컨텍스트, 과거 해시는 변경하지 않음.
- inherited T4 계획 preflight에 `verify_feature_condition_ranges` 추가. STC `>50`, `<=25`, 범위 밖 숫자 조건은 `FEATURE_THRESHOLD_OUTSIDE_DOMAIN`으로 **계획 토큰 소비 전에 거절**. 실제 등록되지 않은 단위 또는 다른 feature의 범위 추측하지 않음.
- 새로운 선택 인자 **`require_trade_activity=True`**: 실제 canonical 비용 포함 S2 replay에서 진입/청산 **완료 거래가 하나도 없는 후보를 `NO_EXECUTED_TRADES_PRECOMMIT`으로 계획 제출 단계에서 거절**. `submit_plan` 새 인자에 정확한 bool 타입 검사, idempotent receipt request에 게이트 정책을 바인딩해 다른 제출자가 과거 정책을 무단 전환한 중복 영수증을 재사용할 수 없게 처리. 신규 세대 연구 클라이언트는 `require_execution_change=True,require_trade_activity=True` 조합 활용.
- **이 제한은 선택적 계획단계 필터**이다. 원래 P4-3 S7의 합격 기준, G22/24/26의 과거 무거래 실험 기록, 사용자 승인 성공 조건을 바꾸지 않는다. 0거래 후보를 자동으로 삭제·소급 미계수하거나 실주문 기능을 수정하지 않는다.

## 2. 테스트 및 실제 P5 개선 확인

테스트를 프로덕션 코드보다 먼저 작성한 뒤 수정했다.

- `tests/research/test_t4_feature_unit_gate.py`: 등록 계산기 출력 [0,1] 검증, 0.25/0.5 등 올바른 임계치 허용, 범위 밖 entry/exit/regime 조건 거절, 비기재 feature UNKNOWN, P5 계획 컨텍스트 advice 조회 전후 역사·토큰 불변, 실제 격리 `AcademicMCPCheckpointService`에서 무거래 계획을 `require_trade_activity`로 거절 후 **동일 토큰에서 수정 계획으로 `AWAITING_DIAGNOSIS` 진입, 기존 원장 미계수**, 잘못된 bool 값 거절 포함.
- 신설 테스트 **16 PASS**, 관련 P4-S7/Feature compiler/governance 함께 **31 PASS**.
- 저장소 전체 Ruff 검사 PASS. 신규 feature-unit 모듈 mypy PASS. `git diff --check` PASS. **전체 저장소 pytest·전체 mypy NOT RUN**.
- **실제** P5 `3b44e05e52b3497db6fa035681ed0a5d`: G28 계획 `stc_cycle >50` + 두 preflight 옵션은 `FEATURE_THRESHOLD_OUTSIDE_DOMAIN`으로 **정확히 거절**, `completed_generations=27`, `AWAITING_PLAN`, 체크포인트 토큰 및 history 동일. 이어 GPT 작성 `stc_cycle>0.25`를 G13 부모의 기존 EMA20 청산과 결합하여 `require_execution_change=True,require_trade_activity=True`로 실행: **+49.2582% 누적수익률, 13.5537% MDD, 49 거래, 노출 43.63%, Sharpe 0.6913, 개발기간 2020~2025 QQQ RAW 비PIT**. 실제 손실 거래 T-000004 -$399.28, T-000026 -$386.73, T-000028 -$306.24 근거로 STC>0.5 S7 민감도 가설 생성·비용후 대조·승인.
- **정식 G28 완료**: `28/100`, G29 `AWAITING_PLAN`, S7 approved **28**, 독립 전략 hash **28**, 증거 SHA 연속 28. 최신 증거 `16f3e430ff926efefe7e15f66a600c6dc025b0c6dd7c53118741f7993891b421`. SQLite `cycles`/`gateway`/`catalog` quick_check 3건 `ok`. Orders OFF, OOS 승인 OFF.
- 대시보드 재확인: `http://127.0.0.1:8081/api/status` HTTP200 P5 28/100 proof true, `http://127.0.0.1:8082/api/status` HTTP200 28/100, `...:8082/api/status?cohort=prior_mcp` HTTP200 68/100 proof true. 서버 재시작·배포·OAuth 변경 **안 함**. 단일 성공 시점에서 8081 응답 회복을 확인했을 뿐 장기 안정성을 입증한 것은 아님.

## 3. 검증의 한계 및 다음 단계

**실제 GPT가 수백 세대를 무인 연속 호출하는 인증된 모델 호스트는 아직 없다.** G28은 ChatGPT 대화에서 각 전략·진단을 작성해 Moon MCP 도구로 직접 실행한 연구이며, P4-2 독립 모델 공급자 서명 영수증은 없음. 타임윈도 반복 연구 개발 데이터 결과를 OOS/실전 알파로 오인하면 안 된다. QQQ B&H +187.77% 개발 기준보다 G28 성과 낮음.

계속할 때 GPT는 모델 컨텍스트 `feature_unit_guidance`를 확인하고, 원래 실주문/OOS 경계를 유지한 채 **`require_execution_change=True` 및 `require_trade_activity=True`**로 각 G29 이후 plan submit을 할 수 있다. 실패 시 같은 토큰에서 원인을 반영해 수정. G29~G100 **72세대 NOT RUN**. 그다음 고정 연구 목표는 T4 100 실제 세대와 P0 자동호스트 검증, 이어 기존 V01~V04 PIT/OOS·V06 paper·V07 go/no go.

**배포 지위:** 이 브랜치 코드에서 실제 P5 개발 제출 검증 성공. Moon 외부 운영 서비스에 신규 파일을 따로 배포·서비스 재시작한 것은 아니다. 과거 연구 원장·기본 OAuth/MCP·고정 URL 불변.
