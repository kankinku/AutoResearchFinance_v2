# Quant Autoresearch — D02 / 2-3 크래시·체크포인트 복구 개선 (2026-10-15 UTC)

## 개발 결과 및 범위

- Git 개발 브랜치: `feat/d02-gpt-recovery-reconcile-20261015`; 기능 커밋 `86c2ccd` origin Push 완료, 운영 서버에는 **아직 적용하지 않음**.
- `application/academic_checkpoint_service.py`: 기존 동일 Plan/Diagnosis 재제출 보호(D01)를 유지하면서, 연구 세대가 immutable cycle DB에 먼저 커밋되고 gateway가 `RUNNING` 상태에서 종료될 때 `reconcile_algorithm_research`가 **최신 완료 세대의 S7 통제실험 증거를 확인·복원한 후에** 다음 `AWAITING_PLAN` 또는 `COMPLETED` 단계로 이동하도록 개선했다.
- `recovery_receipts`: 세션+동작(`reconcile`/`resume`)별 마지막 복구 결과 단계·완료 세대 수·결과 토큰 해시 및 무결성 해시를 보존. 같은 복구를 동일 단계에서 다시 요청하면 새 토큰이나 중복 세대 생성 없이 기존 결과를 반환한다. 상태·토큰이 달라졌으면 기존 복구 수신증을 재사용하지 않는다.
- 정상적으로 끝난 세대의 `experiments` 연구 비교 기록이 변조됐다면 S7 검증 실패로 `RUNNING` gateway를 그대로 보존하고 복구 진행을 거부한다.
- `integrations/chatgpt_mcp_sdk.py`: `reconcile_algorithm_research` 도구의 설명을 명시적으로 '이전 작업자가 완전히 종료된 것을 운영자가 확인한 뒤에만 호출'하도록 보완했다. **진짜 실행 중인 작업자를 자동 감지·차단하는 리스/하트비트 기능은 아직 없다.**
- 증거에 대한 계산은 과거/개발 구간 실험이며 OOS 독립 검증이나 실제 수익 증명이 아니다. 직접 LLM 모델 API 호출/실주문/백그라운드 자동 운영 없음.

## 실제 실행한 테스트

- T0/T1: `tests/integrations/test_academic_mcp_recovery_d02.py`에 gateway 중간 종료 후 누락 S7 복원, 최종 세대 복원, 실행 중 상태의 명시적 종료 후 reconcile→resume 재진행, 동일 호출 멱등성, 수신증/실험 기록 변조 차단 테스트 5개 추가.
- 신규 D02 파일 5개 + 이전 D01 재제출 3개: **8 PASS**. 그 뒤 mypy 반환 타입 오류 1개를 수정했고 Ruff/Mypy 통과.
- 기존 `test_academic_mcp_sessions.py` reconcile/resume 관련 선별 테스트: **3 PASS**, 22 deselected. 전체 도구 `chatgpt_tools()` 정확히 32개 유지 확인.
- T3 전체 프로젝트 Pytest는 미실행, 운영 연결 32개 기능별 실제 호출·배포 테스트 미실행. T4 실제 ChatGPT 10~100세대와 실제 장애 장시간 시험은 미실행. T5 실데이터 PIT/OOS/순수익, T6 모의거래 및 최종 승인은 계획대로 마지막 단계에 배치.

## 잔여 위험 및 다음 작업

1. **D03 / 3-2:** Crossref 발견 논문의 방법/라이선스 검토 큐와 승인 전 수식 명세서 파이프라인. 실제 논문 제목·인용수는 산술 계산식이나 실거래 승인 증거가 아님.
2. D04~D08: 지표 확장·LLM 진화·다시장 실험·MCP 통합 및 배포.
3. T3~T4: 서버 프로세스가 여전히 살아있는 상황에서 운영자가 잘못 `reconcile`을 호출하지 않도록 리스/하트비트·운영자 확인 절차를 별도 검증. 진짜 시간 단위 중단 복구·실제 모델 10/100세대 완주·MCP 서버 릴리스는 아직 하지 않았다.

**보호:** 기존 MCP 고정 URL, OAuth, 원장, 개발 시장 데이터, 봉인 OOS, 주문 비활성 정책은 이 개발 단계에서 변경하지 않음.
