# Quant T4 — 실제 ChatGPT→MCP 3세대 진화 회차 실증 (2026-10-27 KST)

**범위:** `T4-REAL-GPT-CYCLES-G84-G86`; Q02, Q05, Q06, Q07, Q08, Q09, Q14, Q15, Q17, Q20. 기존 20문답·범위 잠금 및 V05→T4→V01~V04→V06→V07 순서 유지. 사용자 지시에 따라 기존 GPT 발전/다중 부모 엔진을 **교체하지 않고** 실제 외부 ChatGPT 도구 입력으로 기존 83/100 체크포인트를 전진시킨다. 빠른 고정 계획 배치로 대체하거나 기존 Evidence를 덮어쓰지 않는다.

## 완료 기준과 실제 결과

기존 세션 `14626d55fb2b461faa485df911920071`: **83/100 AWAITING_DIAGNOSIS → 86/100 AWAITING_PLAN**. 각 세대마다 ChatGPT가 실제 손실·비용·수익·서명된 결정 ID를 검토하고 typed 진단/연구 계획을 기존 OAuth MCP `submit_algorithm_diagnosis` / `submit_algorithm_plan`에 제출. 기존 개발용 재생 부모 선정/계승 검증, S2 체결변경 검증(`require_execution_change=true`), S7 변경-대조 실험(`require_signal_change=true`), 증거 커밋 사용.

| 세대 | 검증된 기존 부모 | 제출한 구조 가설과 원인 분석 | 실제 개발 구간 전략 결과 | 같은 세대 S7 통제 실험 |
|---|---|---|---|---|
| G84 | 이미 제출된 G60 계열 부모/계승 계획; EMA 방향 보강 | ADX 약 20~21의 손실 진입을 근거로 ADX>25 체결 차이 실험 | 누적 +49.19%, MDD 12.39%, 57거래 | MDD 12.3937%→12.3849% (−0.0088%p), 비용 반영 최종자산 14,919.14→14,424.29 (악화) |
| G85 | 과거 G79 검증 재생 부모, 기존 개발 +197.81%, MDD 23.10% | G79에 EMA>0 국면 필터 추가(교차 부모 가설); 큰 손실의 지연 종료를 근거로 RSI 출구 45→48 S7 | +174.01%, MDD 24.46%, 40거래 | MDD 24.4633%→25.0354% (+0.5721%p), 최종자산 27,401.30→18,409.65 (악화) |
| G86 | 과거 G53 검증 재생 부모, 기존 개발 +109.17%, MDD 14.86% | RSI>50 국면 필터 추가; 잔존 손실 진입 ADX20.48/26.07에 대한 ADX>30 S7 | +74.24%, MDD 18.02%, 56거래 | MDD 18.0193%→27.2469% (+9.2276%p), 최종자산 17,423.51→12,762.25 (악화) |

**세대 정의:** G84/G85/G86은 각각 실제 GPT 진단·(G85/G86) GPT 연구계획·개발 백테스트·S7 후속 분석·기존 Academic MCP Evidence에 기록됐으므로 순수한 random batch 완료가 아니다. G84 계획은 요청 전 이미 스테이징되어 있었고 이번에 실제 GPT 진단으로 마감되었다. G85와 G86은 이번 ChatGPT 세션이 Plan과 Diagnosis를 모두 생성·제출했다. 3회 중 어느 것도 S7 후보의 경제성 개선이 증명되지 않았다.

**부모 계승 보존:** G85는 재생 검증된 G79, G86은 재생 검증된 G53, 다음 G87는 재생 검증된 G60을 선택하도록 기존 `DETERMINISTIC_VERIFIED_PARENT_LANE_ROTATION` 규칙이 실제 전환. 이는 기존 전략 부모 선택·재생의 작동 증거이며, **신규 S7 자식의 자동 승격 성공 증거는 아님**. 개선 없는 S7을 임의 계승하지 않음.

## 실제 증거 및 경계

- `get_algorithm_research` 최종: 86/100, `AWAITING_PLAN`, 각 G84~G86의 **서로 다른** `evidence_hash`·`diagnostic_context_hash` 및 1개씩 서명된 S7 가설이 역사에 존재. 다음 개발 부모 G60 `replay_verified=true`.
- `academic-gpt-checkpoints/gateway.sqlite`: `experiment_reports` G84~G86 정확히 3개, 각 보고서 내부 S7 실험 1개; `generation_timings` 3개. `cycles.sqlite`, `gateway.sqlite` 읽기 전용 `PRAGMA integrity_check=ok`. SQLite는 WAL을 사용하므로 메인 DB 파일의 SHA만으로 진행 또는 불변을 판정하지 않는다.
- `orders_enabled=false`, `independent_oos_approved=false`, 원래 GPT 전략 계획·부모 경로·OAuth/MCP 도구 수 32·봉인 OOS/검증 게이트 변경 없음.
- 서버 독립 모델 호출 증빙 필드 `real_model_connection_verified=false`; 실제 ChatGPT 대화가 Plan/Diagnosis를 외부 MCP로 제출한 것은 이 채팅의 도구 기록으로 증명되나, 서버 단독의 서명된 provider call attestation 또는 무인 GPT 연구로 과장하지 않는다.
- QQQ 2020~2025년 재사용 개발 데이터에 대한 성과다. PIT/기업행동 as-of·2026년 독립 OOS·선정편향·동일 예산 랜덤 통제 개선 효과 검증이 아직 불완전하다. 투자 GO 또는 최고 전략 경신을 주장하지 않는다.

## 다음 필수 작업

(1) 기존 G87 AWAITING_PLAN에서 실 ChatGPT 판단 반복, (2) 10세대 연속 수행 및 증거·대시보드 본래 GPT 세션 반영, (3) GPT 상호작용 비용·세대 타임아웃과 변경 효과를 랜덤 대조와 비교, (4) 충분한 증거 후 100세대 실증. 기존 고속 배치와 기존 부모 계승 코드를 삭제하거나 평가 임계치를 낮추지 않는다.
