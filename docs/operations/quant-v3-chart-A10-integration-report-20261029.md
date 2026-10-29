# Quant V3 A10 · 별도 브랜치 40개 소스 출력 통합 감사

**상태:** 연구용 통합 브랜치에만 반영. 운영 main/2026 OOS/실거래 변경 없음.
- 구현 커밋 `1e60790eaf189b6ce5d848dc2076f80272c39ec4` / [Draft PR #4](https://github.com/kankinku/AutoResearchFinance_v2/pull/4) (target: `research/v3-chart-audit-20261029`).
- 선택 회귀 248 PASS, Ruff 전체 PASS, 제한 mypy PASS. 공식 릴리스 검사 uv 미설치(exit127)로 FAILED.
- GitHub API mergeable=false 보고: 리뷰/릴리스 승인 없이는 병합하지 않음.
- 원본 미커밋 소스 파일 해시 확인: 4/4 PASS.
- 등록: 기존 447 → 487; 차트 opt-in 기존 491 → 531.
- Cohort 유형: 추가 출력 채널 34 + 신규 수식 채널 6.
- 기존 447 및 chart research 44 FeatureSpec 식별자·등록 의미 보존.
- 40개×4개 절단 시점 = 160개 봉별 인과성 검사 오류 0.
- 40개 typed FeatureRef replay 일치 40/40.
- Pandas-TA Classic MIT 소스 7c669b0 고정. 파라미터 임의 변경 거부.
- 과거 A0–A9의 정량 증거/원본 SHA는 그대로 보존. 435→475
  수치는 기존 원본 작업 브랜치 기준이며 차트 12를 합친 현재 단계는
  447→487이므로 서로 다른 기준을 혼동하지 않음.

## 범위·실사용 미검증

- 기존 40 미커밋 원본을 고치거나 Git에 Push하지 않음.
- 본 통합은 40개의 고유한 신규 투자 전략이나 독립 알파를 뜻하지 않음.
- V05→T4→V01~V04→V06→V07 상위 개발 순서 유지.
- 실제 자율 연구 세대/G 평가, 수익·거래비용, 2026 독립 OOS 미실행.
- 공식 release CI의 uv 미설치 문제 해소 및 코드 리뷰 전 main 병합 금지.

## 증거

- core/features/bulk40_manifest.json (원본 바이트 동일).
- tests/core/test_v3_selected_bulk40.py (역사적 435→475 단언만
  현재 447→487로 보정한 테스트 복사본).
- tests/core/fixtures/v3_chart_a10_premerge_registry_20261029.json.
- tests/core/test_v3_chart_a10_bulk40_integration.py.
- scripts/v3_chart_a10_validate.py.
