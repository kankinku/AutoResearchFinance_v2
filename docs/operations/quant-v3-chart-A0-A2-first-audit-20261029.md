# Quant V3 · 차트·엘리엇 A0~A2 전수조사 1차 실측 보고

- 시점: 2026-10-29T10:43:51.528286+09:00
- 기준 HEAD: `e3fa3ef699f252f52bbb5fa24140bdfea1a6c95f` / 분리 브랜치 `research/v3-chart-audit-20261029`.
- **A0 확인**: Moon 접속 복구; 별도 clean worktree 확보. 기존 +40개는 원래 브랜치에서 커밋 전 **등록 475개, 신규 40개** 상태 보존. Chart 브랜치는 **447개 / 동일종목 OHLCV 후보 421개 / 외부·전문 입력 26개**, Chart 12개. 현재 **+40 / +12 미병합**. 예상 조합 487은 검증된 실제 개수가 아님.
- **A1 FeatureSpec 목록 검사**: **447개 모든 등록 feature 행을 JSON에 기록**(이름·계열·계산기·입력·기간·출력·수식·소스·라이선스·실행 관찰). 합성 480봉 개발용 데이터에서 421개 계산 및 1바 prefix 확인. 예외 0개, 비유한/길이/접두부 위반 0개.
- Chart 12개 중 합성 경로에서 이벤트 0건: 8개; 반전 추세 480봉에서 0건: 8개. *한두 합성 경로 이벤트 부재는 수학적으로 영구 불능 증명이 아님*. 실제 시장 이벤트 빈도/OOS 수익은 미검증.
- 정확히 같은 480봉 계산 결과를 보인 feature 그룹: 25개 (수학적 완전 동등성 **아님**).
- **A2 원문/오픈소스 규칙 후보**: 현재 12개 + 아직 구현되지 않은 18개 = **30개 행별 공식·근거·미지원·라이선스 상태**. 소스 참고문헌 5건을 명시하되 원본 코드 복제·적법성 인증을 주장하지 않음.

## 재현된 결함 (핵심)

1. **A1-F01 / P1** 역헤드앤숄더: `[100, 110, 100, 110, 100]`처럼 어깨·머리 가격이 같아야 무효인데 실제 +1 반환. 반대 방향 헤드앤숄더는 동일한 동치 구조에서 0 반환하여 수평 뒤집기 대칭성 위반. 원인: 음수 좌표로 뒤집고 `c > max(a,e)*1.03` 검증. **A7 필수 수정**.
2. **A1-F02 / P1** 가틀리: XABCD `[100,120,107.64,112.4,104.28]`에서 `CD/BC = 1.705882`; 참고 기준의 CD/BC 상한 1.618을 넘지만 계산기가 +1 반환. B/XA와 AD/XA만 확인. **A5 비율 매트릭스/PRZ 필수 수정**.
3. 1~5파 완성 후 탐지만 지원(A6), ABC/WXY 복합 유형 제한(A6), 피벗 확정/후보/무효화를 0/±1로 압축(A4/A8), 공통 고정 민감도(A4), 넥라인 돌파 불검사(A7), 전체 end-to-end 양성 OHLC 패턴 fixture 부재(A9).

## 현재 의미와 차단 조건

- **전수조사의 대상 범위(등록 447개 + 로컬40 후보 + 패턴후보18)를 분류했지만**, 외부 원전별 세부 수식 검증·전략 가치 증명은 아직 끝나지 않은 A2 후속 과제다.
- 구체 원본 조건/라이선스가 충족되기 전 신규 후보 18개를 추가 등록하지 않는다. 하모닉 상표/상업적 사용 제한은 별도 확인이 필요하다.
- **Moon 공식 release 검증: VALIDATION_FAILED** — `uv run --locked --extra dev ruff check .` 호출이 `uv: command not found` (exit 127)로 중단. 별도 venv에서 수행한 Ruff/pytest/scoped mypy PASS와 구분.
- 실제 StrategyIR 실거래 활용 금지, 2026 sealed OOS 비접근, 원래 연구 기록/계보·OAuth·MCP URL·orders OFF 무변경.
- **다음:** A2 원식별기별 ratio/validator oracle 채우기 → A3 시점별 prefix/no future 데이터 누수 정밀 감사 → A4 공통 pivot API 수정. P1 오탐 2건 교정은 먼저 별도 테스트/소스 버전으로 진행하고 전체 회귀 후 승격.

## 근거 파일

- A0: `docs/operations/quant-v3-chart-A0-baseline-20261029.json`
- A1: `docs/operations/quant-v3-chart-A1-feature-audit-20261029.json`
- A2: `docs/operations/quant-v3-chart-A2-formula-source-matrix-20261029.json`
- 코드 수정 없음; 자동 재현: `python scripts/v3_chart_a0_a2_audit.py`; 독립 테스트: `pytest -q tests/core/test_v3_chart_a0_a2_audit.py`.
