# Quant T4 — 기존 대시보드 ↔ GPT MCP 연결 + 100세대 별도 비교 실험 (2026-10-24 KST)

## 최종 구분 (가장 중요)

| 실행 범주 | 실제 완료/목표 | 의미 | 현재 상태 |
|---|---:|---|---|
| ChatGPT가 직접 AlgorithmPlan / DiagnosticResponse를 작성한 인증 MCP 진화 세대 | **5/100** | 계획 작성 → 비용 반영 S2 / 실제 체결 증거 → ChatGPT 진단 → S7 측정 → 부모 선택. 개별 세대별 모델 개입은 이 대화에서 수행, 서버의 독립 모델 provenance/무인 자동화는 검증되지 않음 | G6 `AWAITING_PLAN`, evidence 해시 보존 |
| 별도 GPT 1세대 파일럿 | 1/1 | 이전 파일럿 검증 전용, 위 5/100에 합산하지 않음 | 원장 보존 |
| GPT가 *한 번* 계획한 이후 로컬 결정적 탐색 작업자가 수행한 고정 탐색 비교군 | **100/100** | 100세대 반복 백테스트. **매 세대 GPT 재설계·진단은 없음, 자율 GPT 실험으로 계수 금지** | 완료/증거 보존 |

**실제 GPT 연구 100/100 완료 아님.** 현재 Quant MCP는 ChatGPT를 모델 클라이언트로 사용한다. 서버에 외부 GPT 자동 호출 수단은 없고 OpenAI API 키·독립 유료 호출 승인도 없으므로 무인 100 GPT 세대를 자동으로 실행할 수 없다. 단순 코드/규칙 생성 반복을 GPT 세대로 위장하지 않는다. 순서 V05→T4 GPT 10/100→V01–V04→V06→V07 유지.

## 기존 대시보드 실제 연결

원래 스타일·HTML/CSS/JS를 사용하고 Windows 노출 URL을 유지하는 8082 원본 UI `https://project-moon.taild689f9.ts.net/academic/`의 기존 `scripts/fresh_original_dashboard.py`가 고정 552세대 통제 원장만 기본으로 읽는 문제가 있었다.

- 수정 `scripts/fresh_research_dashboard.py` 기본 source를 현재 Quant MCP의 **명시적으로 고정된** `state/moon-http/research/academic-gpt-checkpoints` 내 session `14626d55fb2b461faa485df911920071`로 변경. 원본 G452, 고정 탐색 clone G552 및 DB를 변경하지 않고 모든 SQLite 읽기는 URI `mode=ro`, `PRAGMA query_only=ON`. 다른 세션 자동 선정/원장 혼합 금지.
- 기존 웹 UI `/academic/`와 `/quant-research/` Basic Auth 및 기존 정적 UI 유지. 새 원장을 `source_kind=GPT_AUTHORED_MCP_CHECKPOINT_DEVELOPMENT`, `GPT_PROVENANCE_NOT_ATTESTED`로 노출하여 직접 제출한 연구와 무인 자동화 증명을 구분.
- 과거 원장은 같은 서버 읽기 전용 GET `/academic/api/status?cohort=historical`(기존 552 원장) 및 `?cohort=original`(452)로 보존. UI에서 링크로 접근 가능. 재표시용 백테스트 입력이 아니라 검증된 SQLite 스냅샷 수치.
- 수정 테스트 17 PASS + repo Ruff / Mypy PASS; 대시보드 서버 8082 supervisor만 재기동, 페이지의 원래 성과 그래프 ID 유지, 기존 Quant MCP 및 Moon /mcp·/health 영향 없음. 실제 8082 HTTP 응답: 현재 5/100, source GPT, proof_chain_ok true; 역사 데이터 G552 552/552, G452 452/452, 모두 증거 체인 true. 배포 소스 커밋 `e9811ea` origin push.

## 실제 GPT 세션 10→100 목표 안전 확장

G1~G3의 GPT 계승/증거를 유지하기 위해 새 100세대 세션을 만들지 않고 같은 `14626d55fb2b461faa485df911920071`를 정확하게 **3/10→3/100**으로 확장. Operator-only `scripts/extend_completed_academic_session.py`은 원본 MCP 8787을 중지한 뒤 수정해야 하며, 부트스트랩 OAuth를 새로 발급하지 않음.

- 첫 시도는 구형 카탈로그 파일 `catalog.sqlite` 및 `catalog-s6-v1.sqlite`를 실제 운영 환경에 없는데 필수로 요구해 **확장 전** 차단됨. 실패 당시 session 3/10 및 해시 불변. 만들던 불완전 backup 폴더는 수정/삭제하지 않고 격리 상태 그대로 유지.
- operator backup helper를 재검토해 실제 current 필요한 `gateway.sqlite`, `cycles.sqlite`, `catalog-s6-v2.sqlite`만 필수로 하고, 있으면 구 카탈로그도 백업, 없는 파일을 인위적으로 생성하지 않음. 백업 대상은 검사 **후** 생성. 추가 계약 + 운영 연장 테스트 **11 PASS**, 루프 정상 복구.
- 두 번째 시도는 DB 3개를 별도의 0700/0600 operator backup에 안전 복사한 뒤 **같은 세션 ID에서 목표 100으로 변경 성공**; 응답 `completed=3`, `requested=100`, 마지막 G3 Evidence 해시 `826ba5c3cef9020182597f9cda99b596842352350b966a163e9b16319568851d` 보존. Quant 8787 재기동 후 미인증 401 확인, OAuth 재연결 유지. 수정 커밋 `37b5347` origin push.

## 실제 GPT G1~G5 (현재 5/100)

원본 시장 데이터 `data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet`; dataset hash `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`. 2020~2025 동일 비PIT 개발 데이터, QQQ 비용 반영 매수/보유 +187.77%; 독립 PIT/OOS 미승인.

| 세대 | GPT가 제출한 실행 전략 변경 | 실제 S2 수익률 | S2 MDD | S7 진단 실험 및 수익률 | 선택 |
|---|---|---:|---:|---|---|
| G1 | SMA 상승 국면, EMA/20일 돌파 투표 | +73.47% | 23.38% | 청산을 느린 SMA 방향 전환으로 교체: S7 +84.35%, 거래 81→73 | S7 자식 다음 부모 |
| G2 | G1 S7 계승, 진입을 SMA 상승 신호로 조정 | +91.12% | 21.36% | 진입 EMA 추가: S7 +84.35%, 거래 75→73 (수익 후퇴) | G1 S7 부모 유지 |
| G3 | 부모에 '투표 모두 꺼질 때' 빠른 청산 추가 | +73.47% | 23.38% | 투표 임계값 조기 청산 강화: S7 **-49.19%**, MDD **51.59%**, 체결 871 vs 163 | 거부 |
| G4 | 진입 신호 2개가 모두 일치하는 경우만 허용 | +24.83% | 19.03% | 빠른 EMA 청산 S7 +55.57%; 그래도 G1 S7 미달 | 거부 |
| G5 | 상승 돌파를 이익 실현 신호로 해석하는 청산 추가 | +32.45% | 21.86% | 돌파 청산만 제거한 S7 +84.35%, 거래 215→73, 비용 $4298.29→$1729.82 | 동일 논리 복원 자식 |

현재 GPT G5 기록 `0914e43fde14c5607cf22d1b0e6bc6dce306bb7d7ba0e65ca71d51732756fff5`. 총 **5개** 유효 GPT 세대만 완료·S7 계승 기록. G6 `AWAITING_PLAN`, token `9eb07a6e51954e9f9de964daaa6562a0`; 원장 해시 변동/가짜 신규 세대 없음. 모든 새 계획은 개발-only, 100% 현금기반 포지션, 실거래 주문 OFF.

## 비교용 고정 탐색 100세대 배치 (별도 상태/기준)

`mcp__Quant_AutoResearch__preflight_research_batch` 사전 검사 `READY_WITH_WARNINGS`: 데이터 PIT 원본 미검증·회사행위 보정 불확실. GPT가 **한 번** 작성한 파라미터 탐색 의도, 전략 `strategies/normalized/0a805e67c88e16da-4.json`(`golden_cross`), SMA fast 기간 [5,7,9,12,15,18], slow [20,25,30,40,50,60], 손절률 [3,4,5,7,9], 시드 20261024, 세대당 8후보, QQQ 데이터 동일. 이후 **local deterministic worker** 실행, 매 세대 GPT 호출하지 않음.

- Batch job `817d3bbc200c4c66a60adc3b804b62b5`, research_run_id `2cdbde61011542899d4dd1a732f41123`.
- 서버 최종 `COMPLETED 100/100`, 누적 실행 150.947초, unique candidate_hashes **177**, 평가 인스턴스 **177**, 탈락 후보 **177**, 승격 부모 **0**, 중복 후보 회피 **623건**, 중복 후보 외 신규가 없었던 세대 **45**. 자체 적응 가설 적용/재계획 **0**, `adaptive_replanning_enabled=false`. 무인 GPT 추론/자율성 검증 아님.
- 결과 해석: 제시한 탐색 공간·현 비용/데이터·필터 제약에서 우수 후속 전략 없음. 시장에서 전략 발견이 불가능하다는 일반화 금지. 분할/조정·PIT/OOS 미검증과 다중비교 편향 명시.
- 주문 OFF, OOS 승인 false, original G452/G552 원장 미개입.

## 신규 feature 표본 혼합 결함과 안전 경계

G6 GPT 제안은 새 등록 feature `normalized_atr_percent`를 `feature_selections`로 추가해 20일 ATR%와 기존 SMA 필터의 국면 조합을 설계하려 했으나, `_stage_inherited_plan`이 **기존 replay.feature_values**만 재사용하면서 새 alias 벡터를 계산·hash bind하지 않아 `KeyError: natr_pct_20`가 발생. 해당 제안은 **커밋되지 않았고 G6 checkpoint는 유지**.

- 보호 BacktestEngine은 수정하지 않고 `inherited_effective_signal_hash` 사전 필드·시계열 바인딩 검사 추가. 미지원 신규 feature가 참조되면 `INHERITED_FEATURE_BINDING_MISSING`로 **재시도 가능한 안전한 거부**. 서버는 기존 인증 URL 유지, GPT에게 오류 코드/안전 설명을 반환하되 raw 예외·개인 경로·토큰 은닉. 테스트 45 PASS / Ruff PASS / Mypy PASS; 코드 `3a611b7` origin push, Quant 8787 재기동 후 실제 MCP 동일 G6 제안 재제출로 `INHERITED_FEATURE_BINDING_MISSING` + `retry_same_checkpoint=true` 검증. 세대 여전히 5/100, 원장 마지막 해시 변함 없음.
- **중요:** 신규 지표의 실제 완전 계산·replay·S2·S7·승격 계승 **미구현**. 이 조치는 오류로 서버가 실패하거나 미래 data leak을 발생시키지 않도록 차단하는 안전책이며, 기술 기능 완성이라고 표기하면 안 됨.
- 앞으로 T4에서는 replay-verified 신호를 통합한 등록 새 지표 합성 컴파일러 설계·검증이 별도로 필요. 안전 가드 우회나 모든 feature가 자동으로 LLM에게 사용 가능하다는 주장은 금지.

## 검증·다음 작업

- 기존 G452 및 G552 원장은 건수 각각 452/552, SQLite integrity OK, 로그인 Moon/Quant 및 보호 게이트 그대로.
- 현재 사용자가 여는 **기존 대시보드 /academic/**는 실제 GPT 연구 `5/100` 결과·QQQ 비교·원장 증거를 보여주고, 별도 원장 100/100은 자신의 batch API에서 확인한다. 같은 차트에 100 규칙 실험을 합치지 않는 것이 올바른 계산.
- 다음: GPT G6~G100 진정한 계획·진단·S7 증거 연속 실행(현 MCP는 서버에서 ChatGPT 추론을 호출할 수 없고 별도 유료 API도 승인·키 없으므로 무인 100 GPT 실행 불가), 출처 인증·모델 자율성 운영 루프 완성, inherited 신규 feature compilation, 부모 전략 비교 정책 개선, 독립 PIT/OOS validation 후 성과 결론.
