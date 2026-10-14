# S6 1차 — 버전 고정형 지표 확장 및 알고리즘 실제 연결

기준일 2026-10-14. 20문답의 **지표 라이브러리 확대와 LLM의 복합 알고리즘 설계 능력**을 향한 초기 단계. 이 버전은 **외부 오픈소스 패키지 대량 연동이 아니라 기존 오픈 수식의 소규모 검증된 자체 구현**이다. 검증 없는 TA-Lib/Pandas-TA 설치 또는 출처/라이선스 미확인 코드 복사는 수행하지 않았다.

## 신규 단일 자산 연구 신호 4종

| ID | 역할 | 정의·예외 |
|---|---|---|
| `sma_pullback_20` | 롱 평균회귀 후보 | 마지막 완료봉의 종가가 해당 20봉 단순 평균보다 낮으면 1 |
| `dual_sma_trend_50` | 롱 추세 후보 | 12봉(50//4) SMA가 50봉 SMA보다 높으면 1 |
| `ema_direction_20` | 롱 추세 후보 | 20봉 초기가격의 단순 평균으로 지수평균의 초기값을 고정한 뒤, alpha=2/21로 갱신하고 종가가 지수평균보다 높으면 1 |
| `range_low_reclaim_20` | 지지선 회복 가설 후보 | 오늘 저가가 과거 20봉(오늘 봉 제외) 최저가를 깨고 오늘 종가는 그 수준 위에서 마감할 경우 1 |

모든 지표는 `signal[t]`가 **오늘까지 완료된 봉**만 읽고 실제 주문 판단·체결은 다음 봉부터 가능하다. 수학 정의·입력 OHLC 검증·워밍업·독립 수식 검사·접두사 계산 불변·결정론을 확인해야만 `PROPOSED→VERIFIED`로 승격된다. 신호는 이진 롱 진입 **투표 재료**이며, 단독 매수 권유/성과 입증이 아니다.

### 출처·라이선스 및 검증 경계

- 기존의 Brock·Lakonishok·LeBaron(1992, 기술적 이동평균 및 거래 범위 규칙) DOI를 **기초적인 규칙 연구 배경**으로 참조한다. 이 4가지 변형이 논문에서 그대로 제안·검증되었다거나 그 논문의 기대수익을 재현했다고 주장하지 않는다. EMA·풀백·저점회복은 엔진 실험을 위한 명시적인 파생 아이디어다.
- 새 DOI나 가짜 인용 횟수는 만들어내지 않는다. 외부 GitHub 코드 또는 TA-Lib 바이너리를 가져와 라이선스 관리 없이 공급하지 않는다. 패키지 공급자·라이선스·버전 고정/수정 내역을 추적할 수 있는 범용 오픈소스 어댑터 통합은 **S6 다음 범위로 남긴다**.
- 원래 `ACADEMIC_SIGNALS` 7개(그중 복수 `PROPOSED` 포함)는 변경하지 않고 별도 `S6_SIGNALS` 4개로 보관하며, 신규 전체 카탈로그에는 **11개 후보(7+4)** 가 생긴다. `cross_sectional_momentum`은 PIT 다자산 구성 정보가 없으므로 여전히 `PROPOSED`, 자동 승인 금지.

## 기존 연구와의 재현성 경계

기존 `AcademicCycleService`는 데이터 해시와 카탈로그 스냅샷 해시로 세션을 잠근다. 같은 카탈로그 DB에 새 후보를 삽입하면 과거 시작된 세션은 전체 카탈로그가 달라져 **검증 오류가 발생**한다. 이를 막기 위해 다음과 같이 분리한다.

- 기존 세션: `catalog_version='s3-v1'` 및 기존 `catalog.sqlite` (자동 DB 열 추가 시 기존 행에는 명시적 default). 이전 4개 기존 verified 지표와 3개 미인증 후보 상태 유지.
- 신규 세션: `catalog_version='s6-v1'` 및 **별도** `catalog-s6-v1.sqlite`. 기존 시드 7개+신규 4개; 운영용 `AcademicMCPCheckpointService`가 신버전의 미검증 4개를 정해진 독립 계산 검증을 통과할 때만 승인. 신규 세션에서 기존 certified 4 + 신종 4 = **8개 VERIFIED** (이 중 이진 진입 6개, regime/risk 2개).
- 시작 시 각 세션 행의 catalog version이 **고정**되고 `start`, `get`, `submit_plan`, `submit_diagnosis`, `resume`, `evaluate_experiments` 모두 해당 버전으로 역참조한다. 옛 세션은 확장 후에도 변경되지 않으며, 중간 버전 변경은 카탈로그 해시가 달라 실패한다. 새로운 카탈로그를 나중에 추가할 때도 별도 버전을 만든다.
- 기존 `/quant/mcp`의 URL·OAuth 등록·이미 저장된 원장·Sealed OOS·KIS 주문 경로는 변경하지 않는다. MCP 도구 수는 기존 **32개 그대로**, 신규 알고리즘의 선택지는 기존 API의 `verified_indicators`에 추가된다.

## 개발 자료 기능 검사

- 기존 QQQ 2020~2025 개발용(1,508개 봉)에서 새 지표를 모두 조합한 `AlgorithmPlan`을 canonical StrategyIR/backtest/decision audit로 실행: **68개 체결, 1,508개의 의사결정, 다음 봉 체결·hash replay 성공**.
- 개별 신호 warmup (첫 값 인덱스): pullback=19, dual SMA=49, EMA=19, reclaim=20. QQQ 자료에서 각 신호 활성 봉: 496, 1,008, 1,002, 57. 이는 주가 데이터가 변경되면 달라질 수 있으며 전략 수익성 수치가 아니다.
- 관련 테스트: seed 멱등성, 등록 검증 전 사용 금지, 계산 수치·prefix 인과성, 새 알고리즘의 실제 체결·리플레이, 이전 세대 동일 카탈로그 조회, 잘못된 버전/변조 입력 거부.

## 남은 작업

정식 오픈소스 인디케이터 팩의 출처·버전·라이선스·실행 적합성·수식 기준을 확인한 **제한된 어댑터** 추가, 지표 역할/동적 매개변수와 포지션 조절 범위 확장, 실제 외부 GPT가 새로운 지표를 자동 선택하며 학습하는 다세대 호출 수락 테스트, 다자산 OOS/현금 수익 가능성 검증은 미완료다.

## 1차 최종 검증

- **전체** `pytest -q -p no:cacheprovider`: **1,363 passed / 0 failed / 431.24초**.
- 전체 `ruff check .`: 통과. 전체 `mypy .`: **225개 Python 소스 파일** 통과.
- S6 계산/보안 및 기존 MCP 통합 기능 회귀 검사 63개 통과. 전체 기존 자동 연구 및 원장 테스트와 충돌 없음.
- 프로덕션 SQLite를 수정하지 않고 별도 임시 DB로 백업 복제한 기존 QQQ 2세대 `COMPLETED` 세션을 재조회하여 `s3-v1`, 완료 세대=2, 기존 증거 해시 유지 확인. 같은 복제본 내에서 새 `s6-v1` 세션을 시작하고 VERIFIED 8개, 새 4개 모두 포함, 기존 세션 증거 불변 확인.
- 위 상태의 새 신호는 계산/구현 검증에 합격한 것이지, 기존 논문 전략을 실전에서 재현했다는 의미가 아니다. 기존 MCP URL은 유지할 계획이며 배포·인증 실제 재검사는 별도.

## 운영 배포 및 기존 OAuth·세대 해시 보존 검증

- 개발 커밋 `cdad02a3bfc3538c8b7a6747d0c4e36f42058de2` GitHub push. 고정 실행 Worktree: `/shared/moon-workspace/AutoResearchFinance_v2-quant-mcp-runtime-cdad02a`, 이전 `e073810` 코드 디렉터리는 보존.
- 운영 런처 별도 브랜치 `deploy/quant-mcp-s6-stable-url` 커밋 `3cedb58`, GitHub push. 기존 복구 기준 브랜치, nginx route, 공개 OAuth issuer, 키·승인 DB·기존 세션 원장 데이터 경로는 변경하지 않음.
- 기존 MCP URL **`https://project-moon.taild689f9.ts.net/quant/mcp`**: 인증 없는 요청 **401**, resource metadata의 URL 동일. 인증된 기존 Quant Autoresearch 앱의 `get_research_brief` 및 `get_workspace_status` 실제 호출 결과 **도구 32개, `READY`, 주문 비활성** 확인. 사용자 재등록 및 OAuth 재승인 요구하지 않음.
- 실제 운영 state의 기존 S4 QQQ 2세대 완료 세션을 `s3-v1`으로 재조회. 기존 두 세대의 `evidence_hash` 및 결과 동일. 새 `catalog-s6-v1.sqlite`로 8개 검증 지표(진입6·레짐/위험2) 등록 후 같은 과거 세션의 조회·증거 해시가 계속 동일함을 확인했다.
- 개발 검사 **1,363 passed**, Ruff/Mypy 통과. 단, **새로운 GPT가 S6 4종을 실제로 선택하고 여러 세대에 걸쳐 개선하는 실모델 호출 테스트는 수행하지 않았으며 수익성 우위를 주장하지 않는다.**
