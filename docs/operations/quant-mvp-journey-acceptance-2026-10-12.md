# Quant Autoresearch — GPT 연구 시작 UX 후속 작업

- 기준일: 2026-10-12
- 작업 목표: 실제 ChatGPT MCP가 사람이 요청한 전략 계열 및 종목으로 입력을 고르고, 기존 preflight → start → status → report 경로를 최소 단계로 수행할 수 있게 한다.
- 기존 서버/인증/DB/도구 18개 스키마는 유지한다. 실제 주문 권한 추가 없음.

## 발견한 문제

이전 get_research_brief.research_inputs.sources에는 source_path 및 strategy_id만 있었다. 이 구조로는 'QQQ 역추세 전략을 실험해줘' 같은 사용자 요청에서 실제 등록된 전략의 유형을 확인하기 어렵다.

이전 data_paths는 프로젝트 안의 Parquet 확장자만 찾았다. 손상 파일, series 파일, validation/sealed OOS 데이터가 경로 목록에 포함될 수 있어 연구 입력 후보로 잘못 소개할 위험이 있었다.

## 구현한 개선

1. sources의 기존 source_path 및 strategy_id를 유지하고 family, indicators(이름·종류만), numeric_parameter_paths를 추가한다. 실제 Strategy IR 안에 있는 period 항목만 숫자 변경 대상으로 제공한다.
2. datasets에는 개발 영역 Parquet로 읽기 검증된 데이터만 표기한다. zone, symbols, timeframe, bars, quality_status, point_in_time_verified를 표시한다. 봉인/검증 영역 데이터는 원시행을 읽기 전에 metadata 검사로 제외한다.
3. data_paths 원래 필드는 유지하되 유효한 datasets만 반영한다. ready_for_batch는 검색된 전략 및 유효 개발 데이터의 존재 여부만 의미한다. 실제 실행 허용은 기존 preflight에서 다시 판단한다.
4. 기존 18개 MCP 도구 및 input schema는 바꾸지 않는다. 플러그인 스킬의 '먼저 get_research_brief, 다음 preflight' 워크플로를 그대로 재사용한다.
5. 테스트용 격리 워크스페이스에서 하나의 사용자 연구 의도(추세 전략/Q​​QQ/세 가지 파라미터 설정)를 MCP 도구 5종(get_research_brief, preflight_research_batch, start_research_batch, get_research_batch_status, get_research_batch_report)을 사용해 실제 종단 검증한다. 이것은 **모델의 자연어 이해 자체에 대한 사용자 인터뷰 테스트가 아니다**.
6. 사용자 데이터 키·실거래·봉인 OOS 접근 없음.

## 미완료 / 조건부 후속

- 실제 사용자가 모호한 전략 이름(역추세, 평균회귀 등)을 제시했을 때 정확히 한 가지만 질문하고 전략 선택을 마치는 UX는 연결된 모델을 대상으로 사용자 관찰 테스트가 필요하다.
- 개발 데이터 자체는 PIT/법인행위 원본이 독립 검증된 것은 아니며, 시뮬레이션 결과가 실제 투자 적격성을 증명하지 않는다.
- 코드가 읽는 전체 데이터 파일 수가 크게 늘어나면 catalog 캐시 또는 개발 전용 리스트 조회를 다시 설계한다. 지금은 단일 QQQ 개발용 파일과 제한된 200 경로로 충분하다.

## 원격 GitHub 게시 상태

- 원격: https://github.com/kankinku/AutoResearchFinance_v2
- 로컬 브랜치: docs/mcp-phase3-5-1-state-inventory
- Moon 호스트에서 HTTPS git push 시: "could not read Username" 인증 실패.
- 연결된 GitHub 앱에 쓰기 권한은 있으나, 대량 소스 파일 전송 방식은 안전 검사에서 차단됨.
- 원격 GitHub 게시 및 PR/merge는 아직 **미완료**. 성공하기 전에는 원격 반영됐다고 기록하지 않는다. 인증 키를 챗에 재공개하거나 강제 push하지 않는다.
