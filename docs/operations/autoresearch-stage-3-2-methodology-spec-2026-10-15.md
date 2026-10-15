# Quant Autoresearch D03 / 3-2 방법론·권리 검토 및 비실행 수식 명세

기준: 2026-10-15 UTC. 코드 커밋 `52c5bfb`, 브랜치 `feat/d03-paper-review-spec-20261015` GitHub Push 완료. 운영 서버에는 미배포.

## 구현
- `paper_methodology.py` 신규. Crossref DOI별 원본 메타데이터 해시와 결합된 검토 기록·연속된 개정 버전·충돌/변조 검사.
- 접근 수준: `UNAVAILABLE`, `ABSTRACT_ONLY`, `FULL_TEXT_REVIEWED`; 이용권리 상태: `UNKNOWN`, `RESTRICTED`, `OPEN_LICENSE_CLAIMED`, `PERMISSION_CLAIMED`. 모두 **입력한 주장 기록**이며 독립적인 권리 보증이나 외부 원문 내용 판정이 아니다.
- 안전한 FormulaNode 타입: OHLCV 필드·상수·lag·rolling 및 사칙연산·log; 명세 깊이/연산자/지연·미래참조 제한. Python 소스 문자열/임의 import/eval로 실행하지 않으며 카탈로그 지표를 자동 등록·VERIFIED 승격하지 않는다.
- Full-text-reviewed 기록이 있고 그 기록의 해시와 일치해야 수식 초안을 비실행 버전으로 저장할 수 있다. 원문 검토 자체를 자동으로 수행하거나 사실 확인하지 않는다.
- CLI: `list-paper-review-queue`, `record-paper-method-review --json-file`, `propose-paper-formula --json-file`, `list-paper-formulas --doi`. 입력은 로컬 JSON 최대 16KB·symlink 거부. OAuth·MCP 도구 개수·실주문·원장 변경 없음.
- Moon의 기존 실제 Crossref 연구 DB를 읽기 전용 조회한 결과 `Time series momentum`, `Volatility-Managed Portfolios` 등 후보 상위 5건 모두 `METHOD_REVIEW_REQUIRED`, 라이선스 `UNKNOWN`, 작성된 수식 0개, 계산기 승인 false. 허위 검토 기록 생성 없음.

## 테스트 및 잔여
- T0/T1 **14 PASS**: 신규 D03 8개+기존 S9 문헌 6개. 검토 단계 차단, 수식 버전·충돌·데이터 변조 검출, AST 연산자·미래 데이터 차단, CLI 입출력, Crossref 기존 회귀.
- Ruff 변경 경로 PASS, Mypy 2개 변경 소스 PASS, Git diff 검사. T2 MCP 전 기능 실호출, T3 전체 저장소 Pytest, T4 GPT 10~100세대, T5 PIT/OOS·수익성과 T6 페이퍼·최종 승인은 미실행.
- **다음 D04 / 3-1:** 검토 수식·안전한 구현 및 독립 수치 참조·버전 고정된 지표 계산기 경로. 이후 D05~D08 개발, V01~V07 최종 검증.

기존 Quant MCP 주소/OAuth, 운영 프로세스, sealed OOS, 실주문 금지 불변.
