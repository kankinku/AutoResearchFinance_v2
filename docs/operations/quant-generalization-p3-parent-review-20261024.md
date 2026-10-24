# Quant AutoResearch — P3 일반화 평가 기반 부모 비교/선정 v1 (개발 격리 검증)

**작성:** 2026-10-24 KST
**상태:** P3-A 구현·검증 / 실운영 부모 선정 미연결 / 신규 100세대 미실행

## 구현 범위
- `research/llm/generalization_parent_v1.py`: **이미 원본 전체 체결·감사 해시 재생을 통과한 counted StrategyIR 후보만** 평가. 연도별 수익률, QQQ 비용 차감 초과 수익, 최악 연도 MDD, 개발기간 전체 수익률/MDD를 집계한다.
- 전체 수익↑, 전체 MDD↓, 최악 연도 QQQ 대비 초과수익↑, 최악 연도 MDD↓의 Pareto 경계. 성장·최악 연도 낙폭 방어·최악 연도 상대 초과성과 경로로 구분하고 동일 신호 중복 제외. 개별 경로 최상위 후보가 이미 선택됐다면 세 번째는 `PARETO_DIVERSITY`로 명명한다. 2026 및 봉인 데이터 사용 금지.
- 모든 후보의 `dataset_hash`, 개발 종료일, 동일 `year_set` 강제; 연도별 최소 100봉·완료된 연도 3개·합계 완료 거래 10개 미만 등 자료 미흡 시 **fail closed**. 데이터 해시, 원본 계보 해시, full-audit 해시, 연도별 결과 및 report digest 검증. 통계적 유의성 보장은 아니다.
- `application/generalization_parent_preview.py`: **격리된 SQLite 복제본**의 `AcademicMCPCheckpointService`와 `AcademicCycleService.get`을 사용해 generation chain 및 S7 부모 벡터를 원본 코드로 재생 후 새 비교기에 공급하는 read-only off-line 경로. 기존 원장·선정 테이블에 쓰지 않는다.
- 기존 `research/llm/parent_portfolio_v2.py` 및 `application/academic_checkpoint_service.py`의 실제 부모 선정 경로는 **변경하지 않음**. 기존 pinned selection hash, OAuth/URL, 주문/봉인 승인 상태 유지. 다음 P3-B에서 S7 실험 **자식 자체**의 원본 감사·signed lineage를 포함하고, 새 세션에만 명시적 opt-in 연결 후 통합 테스트할 것.
- 현 비교기는 `source_kind=COUNTED_GENERATION`만 허용, `COUNTED_S7_CHILD`는 source evidence/generation이 다르므로 검증 계약 확장 전 **거절**. 비교 결과를 새 부모로 조용히 승격하면 안 된다.

## 실제 68/100 개발 원장 read-only 복제 비교
- 개발 QQQ 2020-01-02~2025-12-31 RAW 비-PIT, 연도별 별도 현금 초기화, 다음 봉 시가·기존 비용 모델.
- 세션: `14626d55fb2b461faa485df911920071`. 원본 DB source는 `mode=ro` SQLite backup API로 임시 복제하고 임시 clone에서 `_inherited_from_evidence`와 `audit_inherited_decisions`를 수행. 운영 서비스 코드/DB 자체는 변경하지 않음.
- 비교 세대/관측치:

| 원본 세대 | 2020~2025 누적 수익률 | 기간 전체 MDD | 2021~2025 최악 연도 QQQ 초과수익 | 연도별 최악 MDD | 플러스 연도 / QQQ 초과 연도 |
|---|---:|---:|---:|---:|---:|
| G64 | +188.53% | 24.13% | -19.14%p | 20.48% | 4/5 · 1/5 |
| G61 | +150.30% | 21.97% | -21.48%p | 17.70% | 4/5 · 1/5 |
| G45 | +138.73% | 20.95% | -24.04%p | 18.42% | 4/5 · 1/5 |

- G64가 수익률/최악 연도 상대 성적 우위. G61은 **연도별 최악 MDD** 17.70%로 나머지보다 낮음. G45는 전체 MDD 최저. 세 개 모두 목적별 Pareto 후보.
- 당시 개발 브랜치 평가에서 차기 번호 69를 **가정**한 부모 선택 rotation은 `GROWTH=G64`, `DOWNSIDE=G61`, 세 번째 `PARETO_DIVERSITY=G45` (기존 "CONSISTENCY"로 오인하는 명칭을 수정). 테스트 스모크에서 가정된 G69 선택은 G45. 이는 **실제 G69 부모 선정이 아니며** 새 100세대나 기존 68/100 원장을 진전시킨 적 없음.
- 실측 비교 selector hash `d6a7cbabe30483465f121220ae19f1ab9820408e387eb5c03d6cd83f6f80d667`은 **fallback 명칭 수정 전 스모크**의 해시이므로 최신 코드의 정식 selection hash로 재사용하지 말 것.
- 비교 결과는 DEVELOPMENT 학습에 사용한 가격 구간의 EX-POST 점검이다. **독립 2026 OOS 통과, alpha, 미래 수익성, 시장 국면 방어 증명이 아니다.**

## 테스트 및 남은 검증
- 새 `tests/research/test_generalization_parent_v1.py`: 동일 조건 순서 불변, 각 lane 중복 없고 방어 후보 보전, 64개 hex digest 및 report tampering, 참조 다르거나 미검증·허위 OOS·잘못된 benchmark, 부족한 데이터 거부. `PARETO_DIVERSITY` 잘못된 "일관성" 포장 방지 추가.
- 사용자의 100세대 연구 자체는 미실행; P3-B 실운영 연동 전에 source 복제본에 대한 보다 폭넓은 integration/regression suite와 S7 child parent 비교 동등성 필요.
- `mypy research/llm/generalization_parent_v1.py` PASS. `mypy application/generalization_parent_preview.py` 직접 실행 시 기존 의존 모듈 `precommit_rejection_feedback.py`, `academic_checkpoint_service.py`의 사전 존재 타입 에러가 발생할 수 있음; 유형별 구분·별도 수정 후 재평가.
- 성적 부진 후보 탈락을 위한 절대 수익 기준은 의도적으로 추가하지 않았으나 표본/비교 불능일 땐 PASS를 꾸며내지 않고 차단한다.
