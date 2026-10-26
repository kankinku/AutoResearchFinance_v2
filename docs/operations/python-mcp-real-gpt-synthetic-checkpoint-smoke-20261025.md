# T4-PY-MCP-D4 — 실제 Codex 모델 + 합성 개발 데이터 체크포인트 1세대 스모크 테스트

**날짜:** 2026-10-25 KST · **작업 ID:** T4-PY-MCP-REAL-GPT-SMOKE-01
**요구사항:** Q02, Q06, Q08, Q09, Q11, Q15, Q17, Q20
**저장소:** 독립 포크 `kankinku/AutoResearchFinance_PythonMCP` (`main`).
**합격 정의:** 실제 Codex SDK 모델 응답(계획·진단) → 기존 P4-2/Academic MCP 서명 검사 → 비용 포함 canonical backtest → S7 통제실험 → 원장 증거의 재오픈 검증. **단, 합성 개발 데이터·신뢰되지 않은 로컬 수집기 서명을 사용하므로 운영용 모델 출처/수익성/PIT/OOS 합격 판정과 구분한다.**

## 1. 실제 실행 결과

| 단계 | 실제 확인 |
|---|---|
| 독립 Codex 인증 | `CODEX_HOME=/root/.codex-quant-python-mcp`에서 `Codex.account()` connected=true. 기존 ChatGPT 플러그인 OAuth 재발급 없음 |
| 첫 실제 GPT 탐색 가설 | 1 SDK 턴 / 총 11,509토큰. QQQ/200일 이동평균 검증 가설. **백테스트에 제출한 계획과는 별개**, 세대 미집계 |
| 실제 GPT typed AlgorithmPlan | 1 SDK 턴 / 총 15,473토큰. `AlgorithmPlan.model_validate` PASS; `plan_id=explore_trend_confirmation_v1`, 1개 분기, `sma_direction` 필터·`dual_sma_trend_50` 진입 투표 |
| 계획 제출 | fork-local ChatGPT Academic STDIO MCP `submit_algorithm_plan` 승인. `AWAITING_PLAN → AWAITING_DIAGNOSIS`, 세대 0 |
| 실제 GPT typed 진단 | 1 SDK 턴 / 총 15,309토큰. 실제 비용 포함 synthetic 개발 백테스트의 해시/판단 식별자를 근거로 가설·`CHANGE_POSITION_SIZE` 70% 대조 실험 제안; 원인 가설로만 취급 |
| 진단 제출·S7 | 동일 MCP `submit_algorithm_diagnosis` 승인. 종료 응답 `COMPLETED`, 1세대 |
| 재오픈 확인 | 별도 새 프로세스에서 checkpoint 1개·history 1개·증거 해시 64 hex·관측 거래 4건·S7 approved 1/rejected 0·P4-2 capture 2단계 검증 |
| 거래/OOS | `orders_enabled=false`, `independent_oos_approved=false`, broker 실행 없음 |
| 원본 보호 | 원본 P5 28/100과 별개. 원본 Moon/Quant Git, OAuth, 고정 URL, sealed OOS 변경하지 않음 |

실제 GPT SDK 호출은 **총 3턴 / 42,291 토큰**(탐색 가설 11,509 + 학술 계획 15,473 + 진단 15,309). 실제 checkpoint 세대에 직접 기여한 GPT 호출은 계획/진단 **2턴 / 30,782토큰**. **독립 제공자 사용량 영수증이 아니라 Codex SDK가 자체 보고한 token usage**이다. 비용 청구액, model provider 측 서명, 100세대 예산 상한은 확인되지 않았다.

## 2. 데이터·연구 범위

- 시장 데이터는 `tests.research.test_academic_algorithm_plan._market()`가 만드는 **650개 합성 시계열**, 자산명이 QQQ인 **가짜 개발용 데이터**다. 실제 QQQ 호가/수익률/배당/PIT 검증이 아니므로 투자 알고리즘 성과 근거로 사용 불가.
- 외부 저장 증거는 **새 포크에서만** `state/python-mcp/gpt-real-connector-smoke/` 아래(이미 gitignored). `synthetic-development.parquet`, `checkpoint/`, `plan-sdk-audit.json`, `diagnosis-sdk-audit.json`, `smoke_session.json`, `collector-public.hex`이 대상. `state/`를 Git에 추가하지 않는다.
- 계획과 진단은 진짜 Codex SDK 턴에서 생성되었지만 **별도의 제공자 서명은 없고, P4-2는 같은 호스트에서 생성한 로컬 테스트 수집기의 Ed25519 서명**을 검증한다. 결과 `external_collector_signature_verified=true`, `independent_model_invocation_verified=false`, `provider_signed_receipt_verified=false`.
- **중요한 격리 한계:** 로컬 테스트 수집기의 개인 서명키가 실행 시점에 연구 작업공간의 동일 호스트 파일시스템 안에 있었으므로 이를 신뢰된 외부 수집기/독립 보안 경계라 주장할 수 없다. 완료 후 공개키만 남겨 재검증하는 데 성공했으며 **테스트용 개인키는 폐기했다**. 향후 운영용 실험은 모델 런타임과 수집기 개인키를 OS 계정·프로세스/볼륨 권한 수준에서 독립 분리해야 한다.
- `COMPLETED 1`은 **합성 데이터 기반 연결성 스모크 테스트** 성공 수치이며, 동결된 T4의 **실제 개발시장/독립 제공자 증거 10→100세대 수락 실적은 0/10**이다. 사용자에게 두 개를 혼동해 보여주지 않는다.
- 원인 분석 `causal_status=UNTESTED_HYPOTHESIS`이므로 S7 승인 = 가설 인과성 입증, 경제적 우월성 보증이 아니다.

## 3. 실제 수행·실패 내역

- 성공: 첫 Codex 실제 JSON 모델 턴·SDK thread/turn ID·schema·토큰 검증, synthetic academic session 시작, 실제 typed GPT plan MCP 승인, 실제 GPT diagnosis MCP 승인, 원장 재오픈 및 capture chain 검증, 공개키만 남긴 재오픈 확인.
- `tests` Python namespace가 원격 임시 스크립트의 `PYTHONPATH`에 없던 **첫 환경 준비 실행 1건은 실패**. 환경변수 명시 후 다시 실행 성공; 모델 호출/세대/원장 변경 없는 실패였다.
- 합쳐진 진단·서명·제출 명령은 **플랫폼 도구 안전 검사에서 1회 차단**. 이후 실제 모델 진단 생성과 MCP 서명 제출은 명시적 단계로 분리해 정상 실행. 차단된 호출로 모델 요청/세대 커밋이 일어나지 않았다.
- 신규 핵심 라이브러리·기존 백테스트·P4·S7 **코드 변경 없음**, 기존 D3/D4 API를 실제 사용.
- 자동 회귀 `pytest`, Ruff, mypy, `git diff --check` 결과는 최종 확인 후 아래 원장에 표기. 전체 pytest/myPy·경제/PIT/OOS 검사는 **NOT RUN**.

## 4. 후속 실험 및 실수 방지

1. 우선 **소스 자체를 더 중복 구현하지 말 것**. `CodexStructuredDecisionHost`→`SignedAcademicHandoff`→`AcademicMCPCheckpointService` 기존 경로가 실제 동작했음.
2. 로그인/모델 실행/사용량에 대한 **제공자 독립 증빙** 또는 관리되는 신뢰된 capture 체계를 확보. 로컬 수집기 키를 같은 모델 파일시스템에 다시 두면 안 됨. 미승인 API 과금이나 OAuth 변경 금지.
3. 재사용 개발 데이터는 V05 실제 비용·통계 기준을 충족하는 실제 **비봉인 개발 시계열**이어야 하며, 2026 독립 OOS 데이터는 여전히 봉인.
4. 실제 시장에서 검증된 1→3→10→100 GPT-authored 연구 루프, 재시작·재개·예산 상한/실험 중단·거래/의사결정 IDs·동일 예산 무작위 대조를 검증. 합성 1세대를 실제 실적에 더하지 않음.
5. 원래 20문답과 **V05→T4→V01~V04→V06→V07** 순서 불변, 실거래 OFF.
