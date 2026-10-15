# Quant Autoresearch D04 / 3-1 연구용 수식 계산기 및 수치 증거 레지스트리

기준: 2026-10-15 UTC (한국시간 2026-10-16). 기능 브랜치 `feat/d04-safe-research-formula-calculators-20261015`, GitHub 코드 커밋 `3723904` Push 성공, 운영 미배포.

## 구현 결과

- `research/indicator_engine/formula_calculator.py`: D03의 제한된 FormulaNode(AST)로만 표현된 10종 연산(OHLCV 입력, 유한 상수, lag, rolling mean/max/min, add/subtract/multiply/divide/log)을 고정된 연구용 해석기로 계산한다. 임의 Python 실행, 전략 생성, 브로커 주문 호출 없음.
- 타입이 다른 OHLCV, NaN·Inf, 비양수 가격, 일치하지 않는 캔들 구조와 길이, 2048개 초과 자료 및 크기 제한 초과값을 차단. 0으로 나누기와 log의 정의역 오류는 미계산(None) 처리한다.
- 빠른 벡터 단위 계산과 별도 직접 스칼라 재계산을 `math.isclose` 허용 오차로 교차검사하며, 각 봉별 미래 데이터가 섞이지 않았는지 prefix 재계산을 통해 검사한다. 계산 결과는 봉 t 종료 시 알 수 있으며 주문은 최소 t+1 이후만 가능하다는 계약(실제 주문 구현은 없음).
- `formula_numeric_proofs` SQLite 원장은 논문 DOI·공식 이름·개정 번호·방법 리뷰 해시·공식 SHA·입력 SHA·출력 SHA·계산기 버전 및 수치 검사 결과만 기록한다. 원본 가격 데이터는 여기 복제 저장하지 않는다. 같은 입력의 재실행은 멱등, DB 기록 변경과 충돌은 거부하며, 새로운 버전은 별개 증거로 기록한다.
- 상태는 항상 `RESEARCH_NUMERIC_CROSSCHECK_ONLY`, `calculator_approved=false`, `broker_executable=false`, `independent_oos_approved=false`. 사용자가 FULL_TEXT_REVIEWED로 기록한 주장은 실제 독립 원문/권리 확인이 아니며 수치 증거도 논문의 수학적 타당성·전략 수익성을 증명하지 않는다.
- 기존 로컬 CLI에 `preview-paper-calculation --doi --formula-id --revision --input-json-file`, `list-paper-calculation-proofs --doi` 2개 추가. JSON 최대 256 KiB, symlink 거부, 별도 외부 API·주문·MCP URL 변경 없음.

## 실제 테스트와 미실행

T0/T1: `test_formula_calculator_d04.py` 15개, `test_paper_methodology_d03.py` 8개, `test_literature_discovery.py` 6개, **총 29 PASS**. Lagged return·rolling functions·log·사칙연산·범위/결측·미래 봉 변경에 대한 prefix 불변성·독립 스칼라 참조, 변조된 저장 기록 거부, CLI, 버전 갱신, 메서드 리뷰 stale 거부. 변경 소스 Ruff·Mypy PASS 및 `git diff --check` PASS.

T2 실제 GPT 자동 루프에서 새 수식 제안/계산기 API와의 통합은 아직 미구현. T3 전체 저장소 정적/통합 회귀, T4 실제 GPT 10~100세대, T5 실시간점(PIT)·봉인 OOS/거래비용·수익성, T6 모의거래·최종 승인 모두 미실행(후순위). 실제 외부 논문 원문을 읽고 검토하거나 계산기 공식 독립 출판 증빙을 얻은 것은 아님.

## 다음 순서
- **D05 / 3-3:** ChatGPT-MCP 기반 연구 가설과 반증 실험을 연결하고 실패 원인·대조군·진화 제안이 세대 체크포인트에 누적되도록 보강. 기존 OAuth·URL/32개 MCP 도구 계약 유지.
- D06 다자산 엔진 → D07 전체 MCP 통합 → D08 병합·배포 → V01~V07 실증 검증.

현재 프로젝트의 `orders_enabled=false`, sealed OOS 격리, 운영 프로세스/연구 원장/기존 OAuth endpoint를 변경하지 않았다.
