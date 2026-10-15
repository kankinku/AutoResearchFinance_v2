# Quant Autoresearch — 기능 개발 선행 로드맵 재정렬 (2026-10-15)

> 최신 전 단계 현황·잔여 목록·테스트/개발 순서·완료 내역의 상시 관리 기준은 [상시 진행 현황](autoresearch-master-progress.md)이다. 이후 각 작업 완료 시 이 문서를 함께 갱신한다.

## 사용자 우선순위 변경

5단계 작업표의 단계 ID는 보존한다. 외부 데이터 검증 및 독립 수익성 실증(1-1, 1-2, 1-3, 4-2, 4-3, 5-2, 5-3)은 개발이 불필요하게 중단되지 않도록 **마지막 단계**에 배치한다. 개발 중 기본 회귀 테스트, 계약 검증, 위험 권한 차단은 미루지 않는다.

**순서:**

1. **핵심 자율 연구 기능:** 2-2 / 2-3 — MCP/GPT 계획-진단 다세대 이어달리기, 오류 복구 및 연구 원장 기능 완성. 서버 자동 GPT 호출을 기본값으로 변경하지 않는다.
2. **확장 기능:** 3-1 / 3-2 / 3-3 — 학술 지표 계산기, 논문 탐색·후보 등록, 새로운 계산식 제안·버전 관리, LLM 진화 구조.
3. **연구 범위:** 4-1 — 단일 QQQ 외 여러 자산의 개발 데이터 및 지표 조합 연구 기능 확장.
4. **운영 기능:** 2-1 / 5-1 — 기존 ChatGPT MCP 도구 연결 유지, 정해진 브랜치만 통합, 배포 자동화. 기존 URL/OAuth 변경 금지.
5. **데이터 및 최종 검증:** 1-1 / 1-2 / 1-3 / 4-2 / 4-3 / 5-2 / 5-3 — 날짜별 원본 이력, 공급자 실제 발표 시각, 분할·배당 판단시점, 분리 OOS, 비용·통계·페이퍼트레이딩, 최종 운영 승인.

시간/계약에 의존하는 가격 원본 수집은 이미 설치된 별도 운영 절차로 보존하며, 검증 완료까지 거래 승인 및 OOS 승격을 하지 않는다.

## 이번 S9(기존 작업표 3-2) 구현 범위

- `research/indicator_engine/literature_discovery.py`: Crossref **논문 제목 메타데이터만** 가져오는 제한된 API 경로. DOI·연도·저자·학술지·인용수 필터 및 중복 제거.
- SQLite `literature_observations`에 DOI+조회 시각마다 원본 출처 응답 해시·후보 메타데이터 해시를 별도 저장. Git에는 DB와 원본 내용 기록하지 않는다.
- `discover-academic-papers`: 특정 논문 키워드 1회 수집.
- `sweep-academic-papers`: 5개 고정 연구 주제에 대해 최대 8건씩 일괄 후보 수집. HTTP 429 발생 시 추가 호출을 중지하고 그전 결과는 보존, 재시도 주제를 남긴다. `--topic`으로 남은 주제만 다시 실행 가능.
- `list-discovered-papers`: 발견 후보 목록 조회.
- `stage-discovered-paper`: 사람 또는 검증된 연구자가 DOI, 대상 시장, 계산 검토 메모를 명시한 경우에만 *서지 Paper* 레지스트리에 추가. 이 동작도 VERIFIED 계산기나 거래 승인이 아니다.
- 모든 후보는 `REVIEW_REQUIRED`, `calculator_approved=false`, `broker_executable=false`로 출력. 논문 제목만으로 계산식을 생성·실행하거나 외부 Python을 설치하지 않는다.

예시:

```bash
.venv/bin/python -m research.indicator_engine.cli \
 --database state/indicator-engine/s9-literature-20261015.sqlite \
 sweep-academic-papers --limit-per-topic 8

.venv/bin/python -m research.indicator_engine.cli \
 --database state/indicator-engine/s9-literature-20261015.sqlite \
 list-discovered-papers --limit 10
```

**3-2 판정: 첫 기능 구현만 완료, 전체 미완료.** 다음 실제 기능은 후보별 제목·초록·방법/라이선스 검토 큐와 reviewed 수식 → 제한된 안전한 계산기 정의 → 별도 버전 레지스트리 연결이다. 유료 논문 자동 다운로드나 자동 실행·검증 승격은 하지 않았다.

## 운영 제한

기존 `https://project-moon.taild689f9.ts.net/quant/mcp` 연결, 인증, 주문 비활성, OOS 보호, 기존 연구 원장은 불변. 개발 브랜치로만 코드 저장하고, 검토 후 별도 배포한다. 전체 프로젝트 Pytest 장시간 실행과 경제성 검증은 이 기능 구현 다음으로 연기한다.

## Moon 실측 (2026-10-15 14:29 UTC)

- 단건 Crossref 조회에서 `volatility managed portfolios` 후보 5건을 발견해 무결성 해시와 함께 연구 SQLite에 적재.
- 선택한 3개 주제 자동 sweep 중 2개 주제 완료, 신규 관측 12건 추가; 세 번째 `cross sectional stock momentum`에서 HTTP 429를 받아 즉시 중단. 응답 `PARTIAL_RATE_LIMITED`, 미처리 주제 명시, 완료된 원본 관측 유지. 429 이후 재시도 요청을 반복하지 않았다.
- 신규 S9 코드는 22개 관련 단위/기존 인용수 테스트 통과, Ruff와 Mypy 해당 파일 통과. 전체 통합 회귀 및 가치 검증은 이번 우선순위 변경에 따라 후순위.
- 후보는 서지 메타데이터이며 본문·라이선스/계산식 해석·지표 구현 및 유효성 판정은 **미완료**.
