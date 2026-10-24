# Quant AutoResearch — P3-B S7 계승 전략 일반화 평가 / 신규 세션 한정 부모 선정 연결

**2026-10-24 KST · 상태: 개발 브랜치 구현 및 격리 실데이터 검증 / 운영 배포·신규 세대 연구 미실행**

## 배경과 변경
기존 P3-A는 실제 GPT가 counted generation으로 저장한 StrategyIR만 ex-post 연도별 평가할 수 있었고, S7 실험에서 생산된 **서명 계보 자식**은 제외되었다. 또 실제 부모 선택 프로세스에 연결되어 있지 않았다.

이번 구현:
1. `application/generalization_parent_preview.py`의 `preview_mixed_parent_generalization`: 동일 QQQ DEVELOPMENT 가격/기존 비용·다음 봉 시가에 대해 (세대 번호, 선택적 S7 hypothesis ID)로 지정된 **정식 세대 전략과 S7 자식**을 함께 원본 엔진으로 전수 재생. `AcademicCycleService.get`이 generations Evidence 체인을 점검하고, `_inherited_from_evidence`는 상속된 부모 지표 벡터·계보·전체 감사를 점검한다. `replay_counted_s7_child`가 실제 S7 sidecar 원본 해시·실험 해시·자식 IR 및 next-open 거래비용/체결 일치를 독립 재검사. 새 `audit_inherited_decisions`로 S7 자식의 모든 신호/거래/비용 해시를 보존해 기간별 연구 평가의 입력으로 사용. 원본 generation Evidence나 S7 원장은 변경하지 않는다.
2. `research/llm/generalization_parent_v1.py`: `COUNTED_S7_CHILD`도 `source_generation/source_evidence_hash/source_report_hash/hypothesis_id/child_strategy_hash`를 묶은 canonical `counted-s7-child-origin-v1` SHA-256 증거와 child full-audit hash를 충족하면 후보로 받는다. 선정 결과에 부모 종류, 자식 계보 해시, lane strategy SHA를 기록. 독립 OOS/거래 활성화는 항상 false.
3. `application/academic_checkpoint_service.py`: 명시적 `generalization_parent_v1=True`와 기존 `parent_portfolio_v2=True` 동시일 때만 새 세션 `start()`에서 `generalization_enrollments` 정책/데이터 해시를 등록. 이후 실제 `_choose_counted_generation_portfolio`의 완전 검증 후보군에서 고정된 최대 8개 후보(기존 Pareto lane·성장·S7 child)를 꺼내 별도 읽기전용 SQLite source → 임시 SQLite 복제본으로 재감사 및 2021~2025 기간별 비교. 선택된 기존 `COUNTED_GENERATION` 또는 `COUNTED_S7_CHILD`의 canonical selection proof/parent_quality를 그대로 보존한 채 `generalization_receipt`를 `selection_hash`에 결합한다. 기존 `parent_selections`에 이미 고정된 선택이 있다면 재선정 없이 **기존 hash 검증 후 그대로 반환**한다. 새 정책을 넣은 세션은 등록 행이 없으면 거부해 이전 연구에 대한 사후 적용 차단.
4. `integrations/codex_mcp_core.py`: 새로운 ADMIN 환경설정 `QUANT_MCP_GENERALIZATION_PARENT_V1_NEW_SESSION=1`은 **새 연구 시작** 시 enrollment 허용, 기존 조회는 `QUANT_MCP_GENERALIZATION_PARENT_V1_SESSION_ID=<32 lowercase hex>`와 정확히 일치할 때만 P3 선택 활성화. 오류 있는 ID/토글은 시작부터 거부. 기본 설정은 모두 OFF. 기존 `QUANT_MCP_PARENT_PORTFOLIO_V2_SESSION_ID` 의미 유지. 인증/OAuth, 고정 URL, MCP registration, 거래권한/OOS 상태를 변경하지 않는다. **위 환경변수는 개발 코드만 지원하며 운영 배포에는 설정하지 않았다.**

## 실제 68세대 캠페인 복제본 재현
- 개발 QQQ 2020-01-02~2025-12-31, 1,508 일봉, RAW non-PIT.
- source: 기존 `cycles.sqlite`/`gateway.sqlite`/`catalog-s6-v2.sqlite`를 SQLite read-only `backup`으로 임시 디렉토리에 복제; 복제본에서 단계별 감사 수행.
- G64 정식 세대: 전체 수익 +188.53%, MDD 24.13%.
- G61 `g61_paired_falsification`의 서명 S7 child: 누적 +173.42%, MDD 24.16%, 최악 연도 QQQ 대비 초과수익 약 -17.61%p (G64 약 -19.14%p). 자식의 연구·출처 해시는 source generation/S7 보고서에서 재현. 동일 실제 데이터로 두 후보 기간별 평가 성공.
- 실제 `AcademicMCPCheckpointService._scoped_generalization_selection` 호출에 위 두 검증 후보를 공급해 `COUNTED_GENERATION G64`를 성장 경로로 선택, `COUNTED_S7_CHILD G61`을 방어 경로에 유지. `scoped-ex-post-parent-selection-v1` 수령 hash `ffb6973eadf604b0cacb408a627901d32203a3070a31d59a3ec591f122cb33d1`.
- `_scoped_generalization_selection`의 **신호 해시 동등성 검사** 강화 후 G61의 S7 child signal hash를 정식 production 계산과 동일하게 구성하여 재시험: `SIGNAL_PARITY_PASS`, 같은 비교 receipt hash 재현. 2026년 자료는 새 세션 `start()`와 P3 후보 비교 진입점 모두에서 개발 데이터로 허용하지 않는다(2025-12-31 상한).
- 이 결과는 원장에 **부모를 실제로 고정하거나 G69을 진행한 것이 아니며**, 새 세션을 개설하지 않은 오프라인 통합 시험이다. S7 결과는 원본 개발 데이터 ex-post이며 OOS로 표시할 수 없다.

## 안전·회귀 검수
- 검증 범위: 실제 source generation/S7 변이 replay, 타임스탬프, 비용·시장 데이터 동일성, 다차원 Pareto/자료기간 조건, 등록된 **새로운** 세션에만 opt-in, 기타 session 및 기등록 pin 영향 없음, 잘못된 S7 hypothesis/report/lineage SHA 실패, 운영 root 밖 상태 복제, OOS/주문 비활성.
- 2026년 사용자가 먼저 관찰한 구간은 재사용 참고 자료일 뿐 신선한 OOS가 아니므로 **시험·학습에 사용하지 않음**. 등록형 최신 데이터 공급자도 아직 없음.
- `pytest` 연구·거버넌스·운영범위 회귀 **97 passed**, `ruff check` 수정 코드 PASS. `mypy` 새 일반화 선택기 단독 PASS. `mypy application/generalization_parent_preview.py` 경로에서는 기존 `application/academic_checkpoint_service.py`/ `precommit_rejection_feedback.py`에 존재하던 별도 타입 진단이 확인되어 전체 모듈 Mypy PASS는 주장하지 않는다.
- 남은 별도 게이트: 운영 시스템 전체 시험, 신규 세션 실제 10세대 GPT 연구 실험(P4), 성능/세대 실측과 실 인증 환경에서의 정책 설정, 2026 이후 봉인된 독립 미래 데이터 검증 및 OOS 승인. P3-B 코드가 존재한다는 사실만으로 실사용 성과가 높아지지 않는다.

## 향후 순서
1. P4 새 격리 research session의 **실제 GPT 10세대** 계획·S7·원장·부모 해시/비용·중단재개 검증 (운영 이식 전에).
2. 지표 계산/비용·Pareto 기준·모델 provenance를 더 확인하고, 10세대에서 성능 악화/증거 불충분 시 수정 및 회귀.
3. 승인된 새 100세대 연구 세션 별도 실행. 기존 `14626d55fb2b461faa485df911920071` 68/100 및 G452/G552 이력은 보존하고 재사용하거나 재계수하지 않는다.
