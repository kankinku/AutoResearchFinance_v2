# T4 — 실제 ChatGPT→Quant MCP GPT 연구 세대 1/1 완료 (2026-10-23 KST)

## 목표와 상태

**T4 / Q02·Q06·Q07·Q08·Q09·Q17·Q20.** 신규 사용자 승인 OAuth로 재연결된 Quant_AutoResearch 앱의 실제 도구 흐름을 검증했다. 기존 승인 단계 V05→T4 실제 GPT 10→100세대→V01~V04→V06→V07은 유지한다.

**완료 판정:** 동일 인증 MCP 도구로 모델 작성 AlgorithmPlan 제출 → 실제 개발용 S2 비용/체결 감사 → 실행된 실제 체결 ID에 기반한 ChatGPT 작성 DiagnosticResponse 제출 → 서버에서 세대 영속 커밋·S7 통제 비교까지 **신규 독립 세션 G1 1/1 완료, S7 1/1 측정 완료**. 이 대화의 GPT가 제안·진단을 작성하고 MCP로 제출했다. 서버가 모델 출처를 독립적으로 증명한 것은 아니며 `real_model_connection_verified=false`, `model_autonomy_verified=false`다. **무인 10세대 자율 실행 완료/진화 효과 입증 아님.**

## 원장·시점·서비스

- 신규 격리 OAuth MCP 연구 세션: `6fc5ad6e1f5b4f5a993bb420908e51dd`, 최종 `status=COMPLETED`, `checkpoint_phase=COMPLETED`, `completed_generations=1`, `requested_generations=1`.
- 데이터: `data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet` 개발용 QQQ 일봉(1,508봉), SHA `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`. **비PIT 개발용**이며 독립 OOS 미승인. 별도 market-data 관리 API는 DATA_IDENTITY_MISMATCH로 거절했지만 **AcademicMCPCheckpointService.start 경로는 데이터 스키마와 기 검증된 S6 인디케이터 증거를 통과해 실제 세션 생성**.
- 원래 보호 연구 원장 불변: G452/452 증거 끝 SHA `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`, G552/552 증거 끝 SHA `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`. 두 SQLite `PRAGMA integrity_check=ok`. 새 G1은 과거 G552의 자동 승계 세대가 **아니다**.

## 실제 GPT G1 전략과 비용 차감 S2 결과

Plan `gpt_volatility_guard_trend_g1`은 서버 제공 스키마에 따라 생성됨. 첫 국면은 Parkinson variance ≤0.00018일 때 SMA50 이중추세와 EMA20 방향에 1:1 투표, min_score=0.5. 둘째 국면은 SMA 방향 양수일 때 252봉 시계열 모멘텀과 20봉 눌림목에 1:1 투표, min_score=0.5. 모두 불충족하면 FLAT. 100% 현금 기반 장기 포지션만 허용하며 GPT 생성 코드/보호 모듈/주문 접근 없음.

| 지표 | G1 원래 계획 | 동일 개발기간 QQQ 비용 차감 buy-and-hold |
|---|---:|---:|
| 누적 수익률 | +94.8359% | +187.7724% |
| 연복리 CAGR | +11.7991% | +19.3334% |
| MDD | 27.9850% | 35.6172% |
| 청산 거래 | 31 | 기준은 진입 후 보유 |
| S2 총 비용 | 634.0456 USD | 8 USD |
| 최종 평가자산(1만 USD 시작) | 19,483.5882 USD | 28,777.2411 USD |
| 시장 노출 | 72.0159% | 100% 보유 가정 |

S2 `strategy_hash=80d16049a1e1f2b526f5ef08ac057dac889985f54d4e0198661b863ea768074a`, `audit_hash=c0fa26db3363caaf304537b014b7530067a11d3acf39ee22367f1889dbdbc6e5`; 전체 체결 이벤트 63, 창 내 청산 31. 반복적으로 0.5 단독 투표에 진입한 손실 예시 `80d16049a1e1-T-000056` (손익 -894.09 USD; 진입 결정 `80d16049a1e1-D-001268`)와 `80d16049a1e1-T-000036` (-624.72 USD)를 실제 audit observations에서 인용. 역인과·국면효과 가능성을 함께 기록.

## 실제 GPT 진단 → S7 통제실험

- `diagnostic_context_hash=b0af0bb562c08254a29292c8ab45e947e4be678f768315b0a89535a7d4c21702`
- hypothesis `g1_weak_vote_entry_ablation`: 다음 한 가지 entry rule을 `plan_vote_score > 0.75`로 변경해 **두 추세 투표의 동의 여부를 더 엄격히 검사**, 동일 부모의 exit/regime·원본 데이터·비용 정책 유지. 반증 가설: 약한 투표보다 시장 반전이 주요 손실 원인이어서 수익을 훼손할 수 있음. 예측은 **거래 수 감소**이며 수익성 개선을 약속한 것이 아님.
- `submit_algorithm_diagnosis(require_signal_change=true)` → **G1 커밋 및 S7 자동 평가** 성공. `evaluate_algorithm_experiments(generation=1)` 재조회에서도 동일 record 반환, 재실험을 새 세대로 집계하지 않음.
- S7 실제 child: 닫힌 거래 **18건(31→18, -13)**; parent 비용 **634.05 USD**, child **360.03 USD** (-274.01 USD); child 누적 수익률 **+49.4931%** (parent +94.8359% 대비 -45.3428%p), 최종 평가자산 **14,949.3068 USD** vs 19,483.5882 USD. 매수·매도 필 trace 변경, fill count parent 63 / child 37. `status=DIRECTION_MATCHED_DEVELOPMENT_ONLY`: **예측한 거래 감소는 확인됐으나 투자 성능은 악화**. 동일 개발 데이터 관측이지 독립적 인과·실전 수익 입증 아님.
- counted generation evidence SHA `0e80dbedf6a378be08bf195476a2cec109cdd139f2c61a7fa5ef60d0d35ad1d0`; immutable S7 `record_hash=b5c52e53e6c1d10a639626ed8b8e293ffd897abf20b8ed4a01d419c500b7e634`; final `proposed_hypotheses=1`, `tested_hypotheses=1`, `all_proposed_hypotheses_measured=true`.

## 이번 검증의 성과와 다음 정지조건

- **통과:** 재승인 Quant 앱 실제 MCP 읽기 및 연구 쓰기 도구 → 1세대 GPT 계획·실측 S2 → 감사 ID와 정확한 context/audit/dataset/strategy 해시에 묶인 진단 → S7 동일 원본 비교와 evidence 기록 → 완결 보고서 조회. 기존 원장 손상 없음.
- **미검증:** 독립적인 GPT provider 출처 인증, **자동 무인** 10세대 실행/재시작 복구, 후보 선별·부모 자동 계승의 실제 전방효과, 무작위 대조군, 독립 PIT·OOS, 실전 경제적 우위. 신규 생성 G1은 수익률이 QQQ보다 낮고 S7 child 성과는 원본보다 열세.
- **다음 고정 작업:** 이 실제 MCP 경로를 사용해 독립 10세대 GPT 계획/진단을 **연속으로** 수행하되 실패·중복·코스트·S7 증거와 계획 변화의 관련성을 추적. 반드시 새로 요청된 10세대와 이전 개발용 G452/G552를 분리. 10세대 완결 후 100세대와 무작위 대조군 판단. API 유료 모드로 자동 전환하지 않음, 실주문/OOS 여전히 불가.
