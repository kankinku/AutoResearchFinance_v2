# T4 — 10/100세대 반복 제어기 격리 검증 (2026-10-25 KST)

**작업 ID:** T4-PY-MCP-FIXTURE-10-100-20261025
**대응:** T4, Q02/Q06/Q07/Q08/Q09/Q15/Q17/Q20.
**사용자 가치:** 정식 GPT 연구를 늘리기 전에 반복·중단·계승 계수 및 미검증 출처 차단을 직접 확인.
**경계:** 로컬 `TEST_ONLY` FakeCheckpoint/FakeModel 및 독립 실제 Academic 서비스 + fixture 시장. 운영 원본 P5 및 fork의 기존 real-GPT synthetic checkpoint를 수정하지 않음.

## 현재 세션 실측

| 시험 | 결과 | 해석 |
|---|---|---|
| 독립 FakeCheckpoint 0→10 | `TARGET_REACHED`, 10/10, FakeModel 콜백 20회(계획 10 + 진단 10), provider_verified=false | **PASS / TEST_ONLY**, 실제 GPT 세대 0 |
| 독립 FakeCheckpoint 0→100 | `TARGET_REACHED`, 100/100, FakeModel 콜백 200회(계획 100 + 진단 100), 계획·진단 토큰 중복 0, provider_verified=false | **PASS / TEST_ONLY**, 실제 GPT 세대 0 |
| 미검증 운영 콜백을 10세대에 제출 시도 | `ModelUnavailable` 발생, 첫 제출 전 0회 완료·0회 계획 제출 | **PASS / fail closed** |
| checkpoint·Codex 계정·provider 및 scope 회귀 | `31 passed in 15.96s` | **PASS** |
| 실제 AcademicMCPCheckpointService+fixture 시장 단일 S7 통합 | `1 passed in 10.73s`, 기존 테스트 재실행 | **PASS**, 모델/시세 모의 |
| isolated Codex 계정 검사 | `CODEX_HOME=$HOME/.codex-quant-python-mcp`: account_connected=true, provider independent verification=false | 계정 연결 **PASS**, 운영 GPT 출처 **BLOCKED** |

**주의:** 이 시험의 10/100은 *상태제어기 내구성 모의 시험*이지 10/100개의 신규 GPT 연구가 아니다. 루프는 in-memory fixture만 이용했으며 실제 시장 데이터의 10세대 성과/향상률/비용을 산출하지 않는다. 기존 실제 Codex-authored 합성 1세대 스모크(별도 보고서)는 그대로 1세대, 동결 T4의 공급자 독립 증빙을 갖춘 실개발시장 완결 연구는 **0/10** 유지.

## 미완료 및 다음 고정 작업

- **BLOCKED:** actual development PIT 데이터 + V05 비용/통계 수락 증거, 제공자 호출별 독립 검증가능한 증빙과 분리된 수집기 서명 경계. SDK metadata나 동일 호스트의 테스트 개인키는 독립 출처 증명이 아님.
- **NOT RUN:** 실제 GPT를 이용한 새로운 개발시장 1→3→10→100세대, 독립 동일 예산 random control, 외부 PIT/OOS, 실거래, 전체 pytest/mypy.
- **NEXT:** 원래 V05→T4→V01~V04→V06→V07를 유지하면서 위 차단 조건을 해결 후 **실제 GPT 1세대** 먼저 수행·재검증하고, 3→10→100으로 확대. 운영 원장에 fixture 결과를 승격/혼입하지 않음.
- **NON-GOALS:** OAuth/고정 URL 변경, 다른 모델 API 무단 활성화, 운영 P5 원장 수정, OOS 해제, 주문 실행, synthetic 성과로 수익성 주장.
- **재현 명령:** `PYTHONPATH=. .venv/bin/python -m pytest -q tests/integrations/test_t4_checkpoint_orchestrator.py tests/integrations/test_t4_codex_host_preflight.py tests/integrations/test_t4_codex_account_probe.py tests/research/test_codex_provider.py tests/governance/test_autoresearch_scope_lock.py` (31 PASS); `PYTHONPATH=. .venv/bin/python -m pytest -q tests/integrations/test_t4_checkpoint_orchestrator.py::test_real_isolated_service_checkpoint_completes_only_after_s7` (1 PASS). 10/100 메모리상 별도 직접 호출은 현재 Moon 작업의 기록으로만 존재.

**상태 기준 커밋:** `f67576c`; 본 세션 신규 소스코드 변경 없음. 배포 변경 없음. 문서 GitHub push 상태는 별도 확인.
