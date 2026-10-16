# T4 연구 대시보드: 계승 StrategyIR 호환성 복구 (2026-10-17 KST)

## 증상과 직접 확인한 원인

2026-10-17 현재 운영 Quant MCP 연결은 정상이고 연구 세션 `2ba41aaeacd547319cfbf7e6f266ad11`의 정식 완료 세대는 로컬 35/100, 전체 135/300, 상태 `AWAITING_PLAN`이다. 브라우저의 대시보드 HTML은 HTTP 200이나 localhost 8081~8085 `GET /api/academic/overview`가 500이었다.

읽기 전용 학술 원장 관찰기 `dashboard/academic_monitor.py`는 모든 세대의 `algorithm_plan`을 dict로 취급했다. P0-3B의 정식 G134/135는 **`algorithm_plan: null`, `inherited_strategy_ir: {...}`** 구조이며 `plan.get(...)`에서 `AttributeError`가 발생했다. 고장은 대시보드/API 계층이며 연구 엔진 오류나 연구 세대 중단이 아니다.

## 개선 작업 및 안전 경계

- 기존 AlgorithmPlan 세대와 P0-3B StrategyIR 계승 세대를 별도로 구분. 새로운 세대는 계승 IR 모델 ID 및 부모 원세대 로컬 ID를 노출하며 StrategyIR 콘텐츠 SHA-256을 봉인된 세대 전략 해시와 교차 검사한다. IR/세대 원장/S7 증거 해시가 일치하지 않으면 503 fail closed, 성과를 꾸며 보여주지 않는다.
- 오래된 `campaign-101-300.json`의 `current_local_completed=33`은 당시 스냅샷 설명이다. 해당 값을 진행률로 사용하지 않고 **실제 cycles.sqlite 세대 35, 이전 세션 100/100 완료·100개 증거 행·데이터 해시와 campaign lineage**를 확인하여 별도 전체 진행률 135/300을 만든다. 서로 다른/확인 불가능한 세션은 로컬 35/100만 표시.
- 표시: 전체 135/300, 세션 35/100, 표·그래프·최고/최근 세대의 글로벌 번호, 읽기 전용·실주문 OFF·자율 worker 미검증 메시지를 구별. 기존 3초 재조회/QQQ 최초 시가 매수 후 최종 종가 평가(배당 제외)/세대별 경과시간·S7 측정 상태 유지.
- **운영 MCP 및 cycles/gateway DB는 읽기 전용으로 접근**. OAuth·MCP URL·32 tools·실주문/OOS 관련 코드 변경 없음. dashboard 서버는 `127.0.0.1`으로만 바인딩하며 localhost 외부 네트워크 접근이나 자동 연구 시작 기능 없음.
- 프로그램 목적은 화면/관찰 버그 수정. 원래 사용자 20문답 T4 단계를 무인 연구 완료라고 주장하지 않는다. 실제 연구 **G136 계획 대기**는 실험 실행 중 상태가 아니다.

## 검증 및 배포 기록

- TDD: 기존 수용 테스트에 실패한 세대 IR-null 테스트 추가 및 두 증거 해시 위변조 거부 테스트. 재현된 오류 `AttributeError('NoneType' ... 'get')` 수정.
- 연구 원장 없는 CI 픽스처: 21 PASS, 1 SKIP(비추적 과거 QQQ 원본 파일이 테스트 worktree에 없음). SQLite origin 검증 및 오래된 campaign 카운터 무시 테스트 추가.
- Ruff 전체/전체 MyPy와 전체 pytest는 릴리스 전에 실측해 결과를 추가 기록한다.
- 배포 후 `/api/academic/overview` **HTTP 200**, 읽기 전용 data source와 135/300, G134~G135 IR 이름/수익률, QQQ, S7, 주문 0을 재조회한다.


## 실제 배포·사후 검증 (2026-10-17 KST)

- 코드 커밋 `bec864a`(G134/135 IR-null read + SHA 재검증 + 글로벌 카운터), `8e7d17e`(브라우저 JS 캐시 갱신) 모두 GitHub 브랜치 `fix/t4-academic-dashboard-inherited-ir-20261017` Push.
- 소스의 **clean detached SHA `8e7d17ef4f66f3cda9a4cf42a4ce3c145a317e71`**를 별도 대시보드 worktree에 고정. 연구 MCP(8787)·원장·OAuth·32 tool·주문 관련 서비스는 재시작하지 않았음.
- 기존 8081~8085 다섯 읽기 전용 localhost 대시보드 프로세스를 개별 교체, 각 요청 `GET /api/academic/overview` **HTTP 200 / `OK` / 135/300 글로벌 / 로컬 35/100 / `AWAITING_PLAN` / 계승 IR / S7 미측정 0 / orders_enabled false** 대조 확인. 임시 preview 8086은 종료. `127.0.0.1` 전용이므로 사용자의 Windows 브라우저에서 같은 주소로 접근할 수 있는지는 별도 포트 전달에 좌우되며 이 작업에서 외부 노출/인증 변경 없음.
- 브라우저 내 표시 보정: 세대 표/그래프/최근·최고 세대의 100 offset, 현재 세션 표기, 구 세대까지 읽고 해시 검증하는 실패 차단, 새 academic.js 버전 질의. 별도 상주 GPT 실행기가 없음을 구분. 타이밍 평균은 실제 Plan→S7 실측 기록(당시 세대 기준)이며 **GPT 다음 입력이 언제 올지 예측하지 않는다**.
- 테스트: 대시보드 관련 pytest **22 PASS**, Ruff 전체 **PASS**, Mypy 전체 **267소스 PASS**, Node JS 문법 검사 PASS, 라이브 DB를 읽기만 한 TestClient와 실 서버 GET PASS. 전체 저장소 pytest는 **413 PASS·2 FAIL·1 SKIP 시점에 중단**(전체 PASS 아님). 두 실패를 배포 전 기존 고정 소스 SHA `2251d49`에서 독립 재실행해 **둘 모두 그대로 재현**: (1) Phase0 라우트 계약 테스트에 원래 있던 academic 읽기 전용 경로 추가분이 누락, (2) 무시된 개발용 QQQ 원본 Parquet가 테스트 소스 작업공간에 없어서 BatchRequestError. (2)는 원본에서 QA 전용 작업공간으로 안전하게 복사 후 단독 테스트 **PASS**, 나머지 (1)는 기존 대시보드 기능과 구형 Phase0 계약 간 충돌로 **미해결**. 이 작업에서 공개 계약 기준을 완화하거나 테스트를 수정하지 않음.
- 운영 한계: 기존 dashboard 5개는 각각 별도 독립 OS 프로세스이며 현재 컨테이너 supervisor에 대시보드 자동 재시작 정책이 설치돼 있지 않다. 서버 전체 재시작 뒤 자동 복원을 주장하지 않음; 영속 supervisor/외부 접속은 별도 접근·보안 결정 대상.
