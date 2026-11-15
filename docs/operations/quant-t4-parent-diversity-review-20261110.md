# Quant 부모 다양화 opt-in 동등 예산 선택 통제실험 — [9/16]

**날짜:** 2026-11-10 · Task 8 / T4 · **상태: EXPERIMENTAL / selection-only**

## 목표와 실제 범위

기존 150세대 검토 문서는 과거 마지막 25세대 부모의 G94(8), G96(9), G106(8) 집중 현상을 **역사적 문제 제기**로 남겼다. 이 분석은 **과거 DB·원본 전략·당시 성과를 새 연구에 입력하지 않는다**. 동일한 세대 번호 94·96·106은 코드 내부의 **완전히 합성한 후보 식별자**로만 사용한다. 별도 시장 데이터·G150 원장·실제 GPT 호출이 없기 때문에 결과는 실제 연구 성능 실증이 아니다.

기존 개발 브랜치의 `parent_portfolio_v2=False` 기본값과 기존 `choose_development_parent`, `shortlist_counted_generations`, `choose_parent_lane`의 공개 시그니처·체결 비용/노출/거래 수 게이트·부모 원장·S7 해시를 바꾸지 않는다.

## 실증된 결함과 최소 수정

- **RED:** 현행 `verified_parent_lanes`는 서로 다른 실효 규칙 벡터 해시만 비교한다. 다른 규칙 벡터가 **같은 실제 체결/수량/비용**을 만든 경우에도 독립 부모 3개로 취급했다. `tests/research/test_parent_portfolio_v2.py::test_verification_must_have_observed_fill_trace_not_just_distinct_strategy_ir`의 3개 후보 중 두 후보에 같은 체결 해시를 주입하자 수정 전 **실패**.
- **GREEN:** `research/llm/parent_portfolio_v2.py`는 선택 전에 필수 `executed_fill_hash`의 64자리 SHA256 형식을 검증하고, `effective_signal_hash` 및 실제 **체결 추적 해시가 모두 중복되지 않은 후보**만 별도 레인으로 인정한다. 가짜/누락 해시는 fail-closed.
- 이 해시는 임의 GPT 서술이나 StrategyIR 해시에서 생성하지 않는다. `application/academic_checkpoint_service.py::_choose_counted_generation_portfolio`의 기존 full audit `evaluation.trades`에서 `content_hash([asdict(trade), ...])`로 계산하고, S7 직접 자식은 `research/llm/lineage_selection.py::replay_counted_s7_child`가 이미 실제 정본 비용 백테스트로 확정한 `child.trades`를 사용한다. 추가 독립 백테스트 호출/실거래/기존 세대 증거 수정 없이 **opt-in 후보의 서명된 선택 본문에만** 해시가 추가된다.
- 순위는 기존 Pareto/수익·수익-낙폭·저낙폭 세 레인 및 회차별 회전 규칙 그대로. 같은 체결/비용을 만드는 서로 다른 StrategyIR을 ‘신규 거래 전략’으로 중복 집계하지 않는다. 원래의 실제 원장에 지표 필드 추가/마이그레이션하지 않는다.

## 같은 후보·같은 선택 예산 비교

재현 스크립트: `PYTHONDONTWRITEBYTECODE=1 python -m scripts.t4_parent_diversity_equal_budget` (실험 fixture 및 결과 SHA는 [합성 JSON](quant-t4-parent-diversity-synthetic-20261110.json)). 단일 고정 시드 20261110, **동일 합성 후보 4개**, 각 25번의 선택 기회, 후보 확인 슬롯 각 100회. 두 방법 모두 똑같은 후보 집합과 계산 예산을 받는다. 모의 후보의 `replay_verified=True`는 **실행 증명 아닌 테스트 가정**. 비교 대상은 실제 원장/전략이 아니다.

| 비교 | 기존 수익 우선 선택 | opt-in 부모 레인 |
|---|---:|---:|
| 선택 횟수 | 25 | 25 |
| 같은 후보를 검토하는 슬롯 | 100 | 100 |
| 가장 많이 선택된 부모 비중 | 100% (25/25) | 36% (9/25) |
| 부모별 빈도 | 합성 94: 25 | 합성 94: 8, 96: 8, 106: 9 |
| 선택된 가상의 서로 다른 체결 해시 | 1 | 3 |
| 선택된 가상 최저 개발 MDD | 23% | 9% |

후보 순서를 다른 고정 시드로 바꾼 테스트에서도 양쪽의 최종 선택 분포가 동일하다. **이 수치는 선택의 분산과 저낙폭 계열의 보존 가능성**만 보여준다. 유효 **실제** 신규 체결 수/가설 방향 일치율/비용/토큰·LLM API 호출·실제 개선 손익은 **NOT_MEASURED**. 모의 시뮬레이션 비용을 실 연구 비용이 0이라는 뜻으로 주장하지 않는다.

## 실행 증거 및 한계

- 기존 부모 테스트 **16 PASS + 역사 증거 부재 1 SKIP**.
- 버그 RED 재현 후 수정: 부모·상속/메모리 관련 확장 **58 PASS, 7 SKIPPED, 1 DESELECTED**. DESELECTED 대상은 `test_gateway_binds_counted_parent_to_staged_diagnosis`로, 현재 없는 `state/moon-http/research/audits/phase1-20261017-1950/snapshot-manifest.json` 때문에 실패. 같은 테스트는 **수정 전 통합 브랜치에서도 같은 FileNotFoundError 재현**. 7 SKIP은 과거 Moon 원본 증거 미마운트.
- 합성 A/B 비교 **3 PASS**, 누락/잘못된 체결 해시 차단 및 동수 체결 중복에 대한 **6개 신규 회귀 PASS**.
- **전체 스위트:** `pytest -q -x -p no:cacheprovider` → **448 PASS, 1 FAIL** 후 중단. 구형 대시보드의 `tests/dashboard/test_fresh_original_dashboard.py::test_readonly_sqlite_bridge_matches_original_contracts`가 현 마운트에 없는 `state/moon-http/fresh-20261021/session-id.txt`를 읽어 실패. 이전 7단계와 동일, 전체 suite PASS 아님.
- `ruff check .` **PASS**, `mypy --follow-imports=silent` 대상 3개 소스 **PASS**. Gateway 직접 mypy는 선행된 `precommit_rejection_feedback`/checkpoint service 오류를 함께 보고해 전체 타입 PASS가 아님. `git diff --check` PASS.
- 이 테스트로 **실제 투자 성능 개선·독립 GPT 연구 우월성·독립 OOS/PIT·해시 기반 실행 검증 완결·통계 유의성**을 주장할 수 없다. 신규 G1의 시작과 실제 10→100 세대 대조시험은 남았다. 실 시세·원본 운영 DB·구 G150·실주문/운영 배포·실 KIS·OAuth 접근 **0건**.

**판정:** 후보 선택 기능에 대한 체결 중복 방어는 코드 및 로컬 회귀 검사 **PASS**. opt-in 부모 분산 효과는 **합성 선택 비교에서만 확인**. 실제 연구 품질·수익·비용 우월성은 **판단 보류/NOT_VERIFIED**. 기본 `parent_portfolio_v2=False` 유지; 사용자 승인 로드맵 V05→T4→V01~V04→V06→V07, 32 MCP, 인증/주문 OFF 변경 금지. 다음 **[10/16] Task 9**에서 GPT/고정규칙/무작위 동일 예산 본실험 사전등록과 원장 조작 차단을 진행한다.
