# Quant T4 — 기존 진화 엔진 보존·고속 배치 검증 기록 연결 (2026-10-27)

**범위:** `T4-VERIFIED-LEARNING-HANDOFF`, Q05/Q06/Q07/Q08/Q09/Q14/Q15/Q17/Q20. V05→T4→V01~V04→V06→V07 순서와 기존 전략/연구 원장, 평가·OOS·주문 보호 유지.

## 원인과 구현

최근 100세대 배치는 `external_gpt_plan_local_deterministic_worker`로서 GPT가 세대마다 계획·진단한 자율 연구가 아니다. 기존 학술 GPT 부모 계승, S7 대조, 다중 부모/국면 전략 코드는 유지하되, 빠른 배치에서 나온 실패 데이터를 기존 GPT 연구가 참고할 수 있게 **읽기 전용**으로 연결했다.

- 신규 `research/llm/batch_learning_handoff.py`: 최근 완료한 두 배치의 SQLite를 `mode=ro/query_only`로 읽고, 모든 세대의 원장과 체크섬 검증된 불변 Evidence의 run/manifest/attempt/generation/end를 대조. 개발 데이터/연구 ID/후보 수/중복 수/탈락 게이트 일치 필수. 불일치 시 `EVIDENCE_UNVERIFIED`와 빈 결과. 실패한 최고 후보는 가설 참고자료일 뿐 자동 부모 승격 금지.
- `integrations/codex_mcp_core.py`: 기존 `get_research_brief`, `get_algorithm_research`의 계획/진단 대기 단계에 별도 `bounded_batch_research_memory` 필드를 추가. **기존 32 MCP 도구 스키마 불변, GPT 원본 model_context/context_hash/체크포인트 토큰·계보 불변**. GPT가 읽고 자율 판단하는 경로는 유지된다. 고속 배치 자체에 GPT 호출을 새로 넣거나 학술 세대 수를 증분하지 않음.

## 증거

- 신규 테스트 `tests/application/test_batch_learning_handoff.py`: 정상 리젝 기록, 변조·누락 차단, 기존 GPT 컨텍스트 불변, MCP 브리프의 간소화 투영 모두 포함 **5 PASS**.
- 기존 연관 MCP·배치·학술·거버넌스 회귀 **56 PASS**(신규 마지막 테스트 추가 이전), 전체 Ruff PASS, 신규 모듈 scoped mypy PASS. 확대 mypy는 기존 `application/academic_checkpoint_service.py` 등 선행 타입 오류로 FAIL(신규 변경 오류로 판정할 근거 없음).
- 실제 운영 원장을 통한 격리 읽기 검증: GPT 세션 `14626d55fb2b461faa485df911920071` 그대로 **83/100, AWAITING_DIAGNOSIS**, context_hash·academic cycles.sqlite SHA 불변; compact 응답도 memory를 보존. 최근 100세대 고속 배치 452개 전부 탈락, 10세대 배치 70개 전부 탈락 기록을 불변 증거와 대조하여 제공. 브리프 전체 약 58.6KB→간소화 약 17.9KB, 32도구 유지.

## 미완료와 다음 단계

이는 **연구 기억의 안전한 인계** 단계다. 실제 모델의 세대별 GPT Plan→백테스트→손실 진단→후속 Plan→부모 승격까지 검증된 것은 아님. 기존 GPT 진화의 83/100대기 세대를 배치로 대체하지 않는다. 다음 T4 단계는 원래 엔진의 모델 판단·증거기반 부모 승계를 소규모 1→3→10세대에서 실증하고, 그 이후 100세대 확대한다. 독립 OOS/PIT 및 실거래는 비활성 유지.

## 운영 적용 및 보존 검증

- 구현 커밋 `f15f71d`, 브랜치 `feat/quant-parent-portfolio-20261021`, GitHub Push PASS.
- Quant MCP 프로세스만 8787에서 재기동(이전 PID22 → 신규 PID3314), Nginx/대시보드/독립 GPT 원장/원래 OAuth 승인 정보 변경 없음. 공개 MCP의 비인증 요청은 계속 HTTP 401.
- 기존 설치된 Quant 플러그인 실호출 `get_algorithm_research` PASS: 원래 GPT 체크포인트 **83/100 AWAITING_DIAGNOSIS**, 기존 모델 컨텍스트 해시 유지, 최신 두 배치 검증 메모리 수신. `get_research_brief(response_mode=summary)` PASS: 검증된 최신 두 배치와 기존 32개 MCP 도구, 간소화 응답 약 18 KB. 기존 학술 cycles.sqlite SHA-256 `4294635268f6d1cff867c081413730a1793edf808d00a864082447d6ccd34f0b` 보존.
- **미진행**: 실제 GPT 판단을 한 세대 더 생성·진단하여 부모 계승까지 검증하는 T4 후속 단계. 코드 통합으로 해당 기능의 성능을 입증했다고 주장하지 않음.
