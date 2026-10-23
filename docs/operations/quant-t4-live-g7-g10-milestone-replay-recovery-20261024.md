# Quant T4 — 실제 ChatGPT 연구 G7~G10 및 지표 계승 replay 복구

작성 기준: 2026-10-24 KST. 기존 ChatGPT MCP 세션 `14626d55fb2b461faa485df911920071`, QQQ 2020~2025 **비PIT 개발 데이터**. 본 회차의 G7~G10은 ChatGPT가 매 세대 ResearchIntent 및 손실-ID 기반 DiagnosticResponse를 실제 제출하고 정식 세대·S7 보고서가 증거 원장에 기록됐다. 서버가 별도 모델을 무인 호출했다는 뜻이 아니다.

## 실행 성과

| 세대 | V2 부모 | 실제 counted S2 후행 비용 반영 수익률 | MDD | 청산 거래 | S7 개입과 개발 비교 |
|---|---|---:|---:|---:|---|
| G7 | G2 COUNTED_GENERATION (+91.12%, MDD21.36%) | **+93.83%** | 20.24% | 74 | 신규 causal RSI14>40 진입 필터 제거 시 +91.12%, 75건으로 환원 |
| G8 | G1 COUNTED_S7_CHILD (+84.35%, MDD19.55%) | +74.61% | 17.73% | 73 | mixed: RSI14<70 신규 필터 및 포지션 비중 90%. S7은 비중만 100%로 변경해 +84.35%, MDD19.55%; 비용 반영 자산곡선 달라짐 |
| G9 | G4 COUNTED_S7_CHILD (+55.57%, MDD15.95%) | +83.18% | 26.06% | 73 | 진입을 EMA-positive로 완화. S7에서 SMA-positive 필터 추가는 `NO_OBSERVED_EFFECT` (실제 체결·성과 동일) |
| G10 | G7 COUNTED_GENERATION (+93.83%, MDD20.24%) | +84.82% | 16.53% | 63 | RSI14 임계값 40→50. S7에서 50→40으로 복원하면 +93.83%, MDD20.24%, 149 vs127 fill events |

측정된 G7의 개발 수익률 개선이나 G10의 낙폭 감소는 **독립 PIT/OOS 성능 검증이 아니며** 전략 유효성·미래 수익을 보장하지 않는다. 2020~2025 기간 QQQ 매수·보유 누적 비교는 약 +187.77%로, 현재 후보가 상대 초과 수익을 입증하지 못했다. G8은 리스크 사이징 변화이고, G9는 조건 변경이지만 S7 조건 개입이 무효임을 확인했다.

## G10 커밋 후 장애 — 원본 원장은 그대로

G10의 GPT Diagnosis를 제출하는 호출은 불명확한 `ACADEMIC_CHECKPOINT_REJECTED`를 반환했다. 실제 원장 확인 결과 G10의 counted generation은 이미 저장됐고, G10 S7 보고서는 아직 저장되지 않은 상태였다. 다음 G11 context 재구성에서 `saved inherited S2 evidence cannot replay`가 발생하여 get/reconcile이 정상 응답하지 못한 것이 원인이었다. SQLite 자체 integrity는 OK였다.

세부 원인: 기존 P0/P1 신규 등록 RSI feature는 G7에서 최초 계산·서명됐고, G10은 그 **동일 지표 벡터**를 상속하여 조건 임계값만 변경했다. G10 실행 시에는 G7에서 서명한 replay/hypothesis hash를 유지했으나, `_inherited_from_evidence()`가 G10을 원본 AlgorithmPlan에서 직접 다시 컴파일하여 **같은 경제적 체결과 최종 자산에도 불구하고 다른 replay provenance**를 계산했다. 저장 감사 trace hash만 달라 거부됐다. 저장된 G10 `measured_final_equity=18481.655284373388`는 직접 재생산과 정확히 같았으며, 원장 변조나 미래 데이터 탐지는 아니었다.

## 수정과 복구 근거

- `application/academic_checkpoint_service.py`의 `_inherited_from_evidence`는 원본 AlgorithmPlan 직접 컴파일 감사를 먼저 시도하고, 불일치할 때에만 **동일 원장 내의 서명된 이전 COUNTED 부모**를 확인한다. `source_generation<current_generation`, 이전 source evidence SHA 및 parent strategy SHA가 모두 맞으면 해당 부모를 먼저 비용·체결 재생산한 뒤 원래 저장된 feature replay를 계승해 자식 규칙을 복원한다. 끝에서 **G10 기존 `audit_hash`와 final equity를 그대로 비교**하고, 불일치하면 여전히 fail-closed다.
- 모든 서비스 호출은 서명된 `history`를 전달한다. V3 donor checkout도 동일 경로 사용. 과거 증거 SHA, 조건, 전략 IR, DB나 G10 counted generation을 수정하지 않았다.
- 일반화된 단위 회귀는 등록된 feature가 부모에 추가되고 자식이 조건 임계값만 변경하는 경우를 재현하며, 원본 replay와 해시 일치를 보증하고 source evidence SHA를 위조하면 예외로 거부한다. 관련 pytest **56 PASS**, repository Ruff PASS, donor 모듈 mypy PASS. Service 전체 mypy 실행에서는 기존 범위의 정적 타입 진단 8건이 남아 있어 전체 mypy PASS로 주장하지 않는다.
- 수정 커밋 `6a257a6`, 브랜치 `feat/quant-parent-portfolio-20261021`, GitHub Push 완료.
- 운영 원장 복구 직전 SQLite 3개를 온라인 백업 `state/moon-http/operator-backups/t4-g10-inherited-rsi-replay-recovery-20261024/`에 별도 저장하고 SHA256·`integrity_check`를 확인했다. Quant **전용** 8787 서비스만 코드 갱신 재기동, 기존 OAuth·고정 HTTPS URL·Moon/대시보드 유지.
- 인증된 MCP `evaluate_algorithm_experiments(session_id, generation=10)`로 **G10 S7만 복원·검증**했다. 보고서 SHA `57c65125fd0ac81bef2751478454183f00065f96a412d476d80356f44850b441`, G10 기존 counted evidence SHA `a8e8e8d3d0b7e00f5ea1c9b1bcbcbec5876b3370ce64f3d2ee61764a1f451be1` **불변**. 저장된 DiagnosticResponse 그대로 재생해 S7 자식 누적 +93.83% vs G10 원본 +84.82%, 실제 fill events 149 vs127로 측정됐다.

## 최종 상태

- 실제 MCP `get_algorithm_research`: **10/100**, `AWAITING_PLAN` G11, 다음 부모 **G10 COUNTED_GENERATION**(+84.82%, MDD16.53%)을 V2가 선정. 원장 S7 보고서 **1~10 전부 10건**, 별도 규칙 기반 100세대는 본 실측에 합산하지 않음.
- 기존 /academic/ 대시보드: live GPT 10/100 `proof_chain_ok=true`; 별도 과거 G552 및 G452 뷰도 각각 552/552, 452/452 `proof_chain_ok=true`. 원래 G452, G552 SHA 및 SQLite integrity 유지.
- OAuth 인증 없는 `/quant/mcp` 접속은 401(정상 보호), 기존 대시보드 API는 200, 주문 및 sealed OOS 둘 다 OFF.
- P3 서버의 무인 GPT 모델 호출은 아직 미완료. 현재 진행한 G7~G10은 **이 ChatGPT 세션이 모델로서 직접 계획과 진단을 작성·제출**한 회차다. 실제 거래나 독립 경제적 우위 검증 완료로 서술하지 않는다.
- 남은 개선: 기존 COUNTED 부모의 신규 feature vector reconstitution는 복구됐으나, 향후 '신규 feature를 가진 COUNTED_S7_CHILD'의 상속 재생까지 포괄하는 별도 보안 검증을 우선해야 한다. 증거 변경이나 무검증 원장 수리로 우회하지 않는다.
