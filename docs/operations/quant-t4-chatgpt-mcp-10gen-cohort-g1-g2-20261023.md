# Quant T4 — 실제 ChatGPT 지휘 10세대 신규 코호트: G1~G2 + 오류 복구 연동 (2026-10-23 KST)

## 실제 상태
- 새 별도 MCP 연구 세션: `14626d55fb2b461faa485df911920071`. 요청 **10세대**, 현재 **2세대 커밋**, `AWAITING_PLAN`(G3), 고정된 체크포인트 `196c25c7648f4faba5fe4e18045ed814`.
- 기존 독립 G1 파일럿 `6fc5ad6e1f5b4f5a993bb420908e51dd` (1/1)은 이 10세대에 **합산하지 않음**. 같은 세션 번호를 연장하는 공식 operator-only 경로는 Quant MCP worker 중지를 요구하므로, 기존 연결을 끊지 않기 위해 승인된 새 10세대 세션을 시작.
- 개발 데이터 `data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet`, QQQ 1,508봉 `dataset_hash=f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`. **비PIT/동일 개발 기간, 독립 OOS 아님.** 비교군 QQQ 비용 차감 buy-and-hold +187.77%. 전체 주문·실거래 OFF.
- ChatGPT가 실제 MCP 계획 및 S2 근거 진단을 작성·제출. 엔진 독립 모델 공급자 provenance와 **무인 자동 실행은 미검증**. GPT 판단을 모사한 scripted generation이라고 표시하지 않음.

## Counted 실험 결과

| 세대 | GPT 제출된 실행 전략 | 비용 차감 개발 수익률 | MDD | 청산 거래 | 실제 S7 단일 개입 | S7 자식 개발 성과 |
|---|---|---:|---:|---:|---|---|
| G1 | SMA 상승 국면 + EMA 방향/20봉 돌파 1:1 투표(>=50%) | +73.47% | 23.38% | 81 | 기존 빠른 청산을 느린 `sma_direction<=0`으로 대체 | **+84.35%**, 73청산, 비용 1,729.82달러(부모 1,775.35달러). 개발 수익 개선 |
| G2 | G1 S7 자식 계승 후, 진입만 `sma_direction>0`으로 확대·청산 유지 | +91.12% | 21.36% | 75 | EMA 긍정 확인을 재추가하여 진입 감소 측정 | **+84.35%**, 73청산, 비용 1,729.82달러(부모 1,792.60달러). 거래는 줄었지만 수익 후퇴 |

- G1 Evidence SHA: `1f773ead91a72dd6ff7f2badfc83246dd7310def9f7690326620c8249b045d49`; S7 report SHA `95d9209855df3319a94c8554e308c61a4c2dba379ea09e566f0465ba5eb79d8e`; G1 후 다음 부모는 S7 `c1_g1_exit_sma_hysteresis`의 전략 SHA `7aaed41fd8bc57a6f2f5f1e28c94d41698534d2faac1a95d00c54456356484c6`.
- G2 Evidence SHA: `97cd53387ec7300605e9e7823827a8669162cc9f55d6be2c825242cafd229d06`; S7 report SHA `4cb414f11ba1f1e91e511e7ed53bdaf19640aeea2aa47747ca15675554e3612d`. G2 S7 자식의 개발 총수익률은 G1 S7 자식과 같았고 G3 부모 선택은 **G1 S7 자식 유지**, G2 원래 counted 후보 +91.12%는 다음 `selected_development_parent`가 아님. 향후 선정 정책에서 counted 원래 S2 후보를 다룰지 별도 설계 검토 필요: 현재의 선택 결과를 수익 최적화 완료로 오해하지 않는다.
- 각 S7은 본 연구 세대가 반환한 실제 비용 차감 체결·보고서이고, 인과 검증/실전 수익 입증이 아님. 추후 여러 전략 비교를 하면 과최적화 위험과 독립 검증 단계가 필요함.

## 실제 GPT 실패-증거 자동복구 장애와 코드 개선

G2 GPT 첫 제안 `ADD_RULE entry.conditions.1`이 잘못된 연산 경로인데 MCP는 에러 사유를 `tool request failed`로만 제공. 경로를 `entry.conditions`로 교정한 후에도 **실제 체결·자산곡선이 기존 부모와 완전히 같아서** `UNCHANGED_CANONICAL_FILLS`로 거절됨. 두 오류 **G2 세대 소비 없음, 동일 토큰 유지**. 후자의 구체 원인은 독립 disposable SQLite 백업에서 S2 preflight를 재생해 검증했으며 운영 증거 DB에 수동 보정/우회 없음.

신규 `integrations/codex_mcp_sdk_server.py`가 AcademicMCP checkpoint 도구에만 안전한 allowlist 에러 코드를 반환한다. `INTENT_PATH_TARGET`, `UNCHANGED_CANONICAL_FILLS`, `DUPLICATE_*`, `P2_PRECOMMIT_RISK_REJECTED`, `P3_SEMANTIC_PREFLIGHT_REJECTED` 시 입력 내용/예외 문구를 노출하지 않고 **같은 토큰으로 실행 가능한 새 가설을 제출**하도록 안내. 미분류 오류는 상세정보 없이 `ACADEMIC_CHECKPOINT_REJECTED` 처리, 위험 게이트는 유지. 추가 보안/오류 테스트 6 PASS, 확대 MCP 통합/계보 테스트 **39 PASS**, 전체 Ruff PASS, 수정 모듈 Mypy PASS. 코드 커밋 `fdd1cea` origin 푸시.

**실서버 배포 확인:** Quant 전용 loopback 8787 프로세스만 코드 갱신 재기동, 기존 nginx/고정 HTTPS 주소/Moon 자체 `/mcp`/OAuth 핀·DB/대시보드 건드리지 않음. 기동 중 일시 502 후 정상 서비스 복귀. 실제 `submit_algorithm_plan` 잘못된 경로 smoke 제출 결과 `error_code=INTENT_PATH_TARGET`, `retry_same_checkpoint=true`, `orders_enabled=false` 명확히 반환; G3 원장 상태는 재조회 시 변함없이 AWAITING_PLAN/2 of 10/동일 token.

## 보존과 다음 단계
- 기존 G452/452 head `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`; G552/552 head `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`, 이 작업은 해당 상태 디렉터리에 쓰지 않았음. 별도 작업에서 읽기 전용 integrity 검증 완료.
- 현재 G3는 `InheritedResearchIntent` / G1 S7 child를 신뢰된 부모로 선택한 **대기 중**. **10세대 2/10, 미완료 8세대**. 향후 각 세대 S2 audit→GPT diagnosis→S7→원장 해시 체크를 반복. 확장 전 부모 선택 정책이 역사상 더 높은 counted 원본 G2(91.12%)를 제외하고 있는 이유를 분석, 후보의 독립성·위험·비용을 유지한 공정한 비교를 검토.
- **무인 연속 실행·외부 모델 출처 인증은 여전히 미검증**, 기존 T4 10/100→V01~V04→V06→V07 단계·봉인 OOS·live OFF 유지.
