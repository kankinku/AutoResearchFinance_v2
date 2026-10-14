# Quant Autoresearch — S4/S5 다세대 실제 연구 연결기 1차

기준일: 2026-10-14. 기준 브랜치 `feat/p0-indicator-research-engine-v1`. [20문답](../decisions/2026-10-14-autoresearch-interview-20q.md)에서 확정한 **세대 = 설계 + 백테스트 + 원인 진단 + 다음 방향 결정**을 외부 LLM provider로 반복할 수 있게 만드는 작업이다. 기존 MCP URL/OAuth/브로커 경로는 변경하지 않는다.

## 구현 내용

- `research/llm/checkpoint_autopilot.py`의 `AcademicCheckpointAutopilot`: 기존 `AcademicMCPCheckpointService`의 **동일 연구 세션·동일 체크포인트 토큰**으로 모델 제안→`AlgorithmPlan` 스키마 승인→canonical backtest→감사 추적→모델 진단→`DiagnosticResponse` 스키마 승인→세대 커밋→S7 변형 대조→연구 방향 피드백(S8)을 반복한다. 고정 최대 `max_generations=1..100`만 허용한다. 1회 실행에서 마지막 세대까지 완료하거나 그만큼 진행한 뒤 상태 반환. 백그라운드 프로세스가 아니다.
- S7 보고서가 커밋되기 전 모델 컨텍스트를 사용하지 않도록, **실험 저장 후 컨텍스트를 새로 조회**한다. 장애가 세대 커밋 직후 발생하면 기존 S7 보고서를 멱등 반환 또는 누락 시 재실행하고, 다음 계획에 보내기 전에 사용한다.
- `AWAITING_DIAGNOSIS`에서 모델 연결이 끊겨도 이전 Plan은 다시 제출하지 않는다. 새 호출은 유효한 진단 체크포인트에서 재개하며, 완료 세대·감사 원장·대조 실험은 중복 추가되지 않는다. `RUNNING/INTERRUPTED`는 **자동 강제 복구하지 않는다**. 이전 실행이 종료됐음을 운영자가 확인한 후 기존 `reconcile_algorithm_research` 절차를 사용해야 한다.
- `research/llm/openai_response_transport.py`: 선택형 OpenAI Responses HTTPS 모델 연결기. `OPENAI_API_KEY` 환경변수 + 명시적 `--model`이 있어야만 호출할 수 있다. 공식 Responses JSON output mode, **별도 Pydantic 응답 스키마**와 입력 context를 제공하고 모델 JSON을 반드시 재검증한다. `store=false`, 공개 공식 HTTPS endpoint만 사용하고 임의 URL, 임의 코드 실행, 브로커 주문/Sealed OOS 접근을 열지 않는다. 모델 API 오류나 불완전 응답을 오류로 기록하고 없는 연구 결과를 생성하지 않는다.
- `scripts/run_academic_autopilot.py`: 기존 Moon 서버의 지정된 `--project-root`, `--state-dir`에서 새 세션 또는 기존 `--session-id`를 **명시적으로** 실행하는 전경 CLI. 시작 즉시 세션 ID를 표시해 중단 시 복구할 수 있도록 한다. 외부 모델 API 키를 소스에 저장하지 않으며 등록된 ChatGPT MCP 앱을 삭제·재등록하지 않는다.

## 운영자가 직접 외부 모델을 연결하는 경우 (현재 미실행)

API 키는 Moon 실행 환경에 별도로 준비돼 있어야 한다. ChatGPT 앱의 기존 OAuth 키와 구분한다. 사용자의 동의 없이 API 자격증명을 추가하거나 비용이 발생하는 외부 모델을 실행하지 않았다.

```bash
# 아래는 예시이며, 실제 model ID와 비용/쿼터를 먼저 확인할 것
export OPENAI_API_KEY='운영자가-별도로-제공하는-키'
cd /shared/moon-workspace/AutoResearchFinance_v2-quant-mcp-runtime-<검증된-실행커밋>
PYTHONPATH="$PWD" /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/.venv/bin/python \
  scripts/run_academic_autopilot.py \
  --project-root /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory \
  --state-dir /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/research \
  --model '운영자-선택-모델' \
  --data-path data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet \
  --generations 10 --max-generations-this-call 10

# 시작 시 출력된 세션 식별자로 이어서 실행. 중단 상태면 기존 복구 도구로 먼저 조정
# 동일 옵션에 --data-path 대신 --session-id <32자리-ID> 사용
```

실제 운영에서 이 예시를 실행할 때는 환경의 비밀정보 저장 정책을 준수하고, 터미널/프로세스 로그에 키가 표시되지 않도록 할 것. **본 구현에는 장기 실행 서비스 등록, 서버 내 API 키 저장, 모델 비용 예산/사용량 게이트가 없다. 운영 자동화 상시 활성화를 위해선 반드시 추가 검증이 필요하다.**

## 검증 사실과 한계

- 결정론적 `TenGenerationScriptedProvider`가 **하나의 호출에서 10개의 서로 다른 전략 설계 및 10개의 증거 식별된 진단**을 제출한다. 각 세대는 종전 canonical QQQ backtest 및 S7 paired comparison을 수행하며 다음 S8 컨텍스트에 실제 보고서가 제공되는 것을 확인한다. 재호출해도 완료 기록이 중복되지 않고, 강제로 진단 시점 provider 오류를 주입한 경우 기존 계획을 유지해 재개하며, 부분 1세대 실행 후 남은 2세대도 연속 진행하는 것을 확인한다.
- 추가로 **실제 QQQ 2020~2025년 DEVELOPMENT Parquet(1,508봉)** 를 별도의 임시 state 아래 사용해 결정론적 provider로 10세대 연속 실행을 수행했다. 결과: 세대 10개 완료, 계획 10 + 진단 10 총 20개 mock model proposals, 개발 통제 실험 보고서 10개 완료, 실거래 주문 0. 이는 외부 모델이 아니라 **실제 거래 데이터를 사용하는 연구 엔진의 실행 수락**이다. 이 샘플 결과를 금융 수익률 증명으로 제시하지 않는다.
- `httpx.MockTransport`로 Responses API 요청 형식, `store=false`, 원격 오류(429), 응답 누락/거절/비정상 JSON, 모델 키 누락 시 fail-closed 동작을 검증한다. **실제 OpenAI API 연결/청구/모델 출력은 호출하지 않았으며 실사용 비용·모델 판단 성공률 미검증**.
- 10세대 전체 검증은 **자율 연구 제어 루프와 저장·복구의 성공**이지 LLM 모델의 가설 생성 능력/진화 효율/재현성과는 다르다. 모델 출력 오류·무의미한 전략·데이터 누출 방어가 실제 모델에서도 충분히 낮은 실패율인지 불명. 동등한 평가 예산의 랜덤 베이스라인 비교, 연결된 ChatGPT 앱 자체의 10세대 연구, 기간/시장 분리 OOS, 실전 순수익 검증은 다음 수락 기준으로 유지한다.

## 보안 및 일관성

기존 QuantAuto MCP 공개 리소스 `https://project-moon.taild689f9.ts.net/quant/mcp`, OAuth DB·key 및 기존 도구 32개는 **그대로 유지**한다. 이 단계는 기능을 별도 CLI로 제공하며 모델/연구 지시를 MCP의 새로운 URL로 재등록하지 않는다. 완료 세대의 hash chain을 덮어쓰지 않고, 모든 자율 연구 데이터는 DEVELOPMENT/non-PIT 영역에 머문다. 브로커 주문은 기존대로 비활성이다.

## 최종 테스트 확인

- 전체 회귀 `pytest -q -p no:cacheprovider`: **1,387 passed, 0 failed, 487.80초**.
- `ruff check .`: 통과. `mypy .`: **230개 소스 파일** 통과.
- 새 시나리오: 10세대 연속 동작, 중간 오류 후 이미 제출된 알고리즘 재사용, 한 번에 1세대 실행 후 재개, 이미 완료된 연구 재호출 시 새 진단 미발생, 응답 JSON/HTTP 오류 차단, 키 미제공시 네트워크 모델 호출 및 세션 생성 모두 거부.
- 임시 디렉터리에서 QQQ 2020~2025 DEVELOPMENT 데이터를 이용한 결정론적 테스트 모델 10세대 연속 실행 결과: **COMPLETED, 10 generations, 20 proposals, 10 S7 controlled experiment reports**, 실거래 주문 없음. 실제 LLM 결과가 아님을 명시한다.
