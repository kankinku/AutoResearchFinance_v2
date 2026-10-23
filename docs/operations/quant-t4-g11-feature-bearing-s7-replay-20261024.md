# Quant T4 — G11 복합 지표 및 S7 부모 승격 복구 (2026-10-24)

## 운영 결과

- 인증된 ChatGPT MCP 연구 세션 `14626d55fb2b461faa485df911920071`: 실제 GPT 작성 계획·실제 체결 기반 진단·S7까지 **11/100세대** 완료, 현재 `AWAITING_PLAN` (G12).
- G11: 앞선 G10 원본(기등록 RSI14>50, SMA 진입/청산)을 이어받아 normalized ATR20<3.5% 진입 국면 필터를 추가. 실제 S2 수익률 **+71.0612%**, MDD **16.5292%**, 63 청산. 해당 부모 G10은 수익률 **+84.8166%**, MDD **16.5292%**. 추가 ATR 필터의 독립된 위험 개선 없음.
- 실제 GPT S7은 ATR 국면 필터만 제거: 수익률 **+84.8166%**, 127 이벤트(체결 총수는 동일하지만 fill/equity hash는 다름), 상태 `DIRECTION_MATCHED_DEVELOPMENT_ONLY`. G11 counted 원장 SHA `a6507174f8af14fd90638b506b4fe31d53e2dbe6a7b928cf107a949548cd3aa6` 및 다음 G12 부모 COUNTED_S7_CHILD G4 정상.
- 모두 **같은 QQQ 2020~2025 개발 데이터**만 재사용했다. 투자 우위·인과·독립 PIT/OOS 검증으로 해석하지 않음. 서버 무인 LLM 호출 및 실거래 주문은 수행하지 않음.

## 발견된 결함과 수정

- 저장된 S7 보고서를 읽어 자식 전략을 재생하는 기존 경로는 G6/G7/G10/G11 모두 실제 equity hash와 일치했다.
- 그러나 실제 G11의 feature-bearing S7 자식을 **운영과 분리된 두 번째 SQLite 복제본에서 G12 부모로 선정**해 계획(95% 투자비중)과 GPT 형식 진단을 제출하면, S2는 정상이나 세대 커밋 시 `saved inherited S2 evidence cannot replay`가 발생했다.
- 원인: `_inherited_from_evidence` 재구성은 COUNTED 원본의 전략 해시만 비교하고, 부모가 `COUNTED_S7_CHILD`인 경우 원본 S7 보고서·가설·출처 해시로 서명된 신호 벡터를 되살리지 않았다.
- 수정 코드: `application/academic_checkpoint_service.py`, `research/llm/ledger_donors_v3.py`. 모든 재생 호출에서 세션 ID를 명시하고, 이전 세대 번호/출처 Evidence/부모 전략 해시/선택 S7 lineage hash 및 저장 report hash를 확인한 뒤 `replay_counted_s7_child` 검증을 통과한 **그 S7 자식 자체**를 부모로 사용한다. 최종에는 원래 정식 세대의 audit hash와 비용 포함 최종 자산을 그대로 검증하며 불일치 시 fail-closed. 기존 원장 행을 변경·삭제하거나 오류를 무조건 무시하지 않는다.
- 코드 커밋: `54de464` (GitHub Push).
- 동일 DB 복제 시나리오 재시험: G11 S7 선택 → G12 95% 투자비중 S2 → 정식 G12 진단 커밋 → 별도 S7 검증 저장 → G13 `AWAITING_PLAN` 정상. **이 두 세대는 분리된 복제 DB 테스트로, 실제 GPT 운영 원장에 가산하지 않음.**
- 회귀: 관련 `pytest 69 passed`, repository Ruff PASS. P2 보호 및 과거 세대 증거 검사 유지.

## 운영 반영과 안전 확인

- 배포 직전 원장 SQLite 3개를 `state/moon-http/operator-backups/t4-g11-promoted-feature-s7-predeploy-20261024/`에 온라인 백업(각 integrity OK/manifest hash 보존). Quant 전용 서버만 재시작.
- 기존 OAuth/고정 URL 미변경. Quant 보호된 MCP 미인증 401, 대시보드 200; 실제 MCP `11/100 AWAITING_PLAN`, head SHA 불변.
- 대시보드 `proof_chain_ok=true` (GPT 11/100), 기존 G452 452/452 및 G552 552/552 모두 proof true, 저장 SHA·SQLite integrity 유지. 실거래/OOS 승인 false.
- 후속 우선순위: 새 피처를 가진 자식이 여러 차례 반복 승격되는 경우의 시간/캐시 최적화 및 자동 회귀 추가. P3 모델 무인 추론 경로는 승인된 프로바이더 권한 확보 전에는 미완료.
