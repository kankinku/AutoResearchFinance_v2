# T4 원본 G100→G150 연구 계보 정정 (2026-10-27 KST)

## 사용자 정정과 작업 범위

사용자는 "추가 50세대"를 **우수 개발 후보 G94(+206.81%)가 포함된 원래 100세대 연구의 G101~G150 연속 연구**로 명시했다. 이전 작업에서 신규 50세대 세션 `3178d812...`를 만든 것은 명백한 잘못된 해석이며, 기존 연구를 이어간 것으로 보고해서는 안 된다. 본 수정은 T4 Q02/Q05/Q06/Q07/Q08/Q09/Q14/Q15/Q16/Q17/Q20의 기존 목표/계보 복구에 한정한다. 사용자가 새로운 제품 목표 또는 OOS/실거래 권한을 승인한 것이 아니다.

## 보존되는 연구 및 독립 실험

- **원본** `14626d55fb2b461faa485df911920071`: 연구 완료 G100 → 원본 세션 동일 ID로 150세대 확장. 확장 전 G100 증거 헤드 `a6d7d7fa0755c7c151b12a169c0667f2c6e890c45cc1a7cac6d7ce5853ea9e38` 검증; G94 +206.8109713155% / MDD 22.6697108876% / 35거래 보존. 개발용 NON-PIT만 사용.
- **잘못 생성한 별도 세션** `3178d8127836481c94b3c5da2962411a`: 45/50 `AWAITING_PLAN`, 증거 헤드 `f250ac183372cb5a548507d91dc7d4d811e3929fa9fb65270f418f30a8824d0e` 그대로 보존. 기존 100세대에 합산하거나 G101~G145로 번호를 바꾸지 않음. 이 실험은 원본 진화 성적이 아님.
- 위 두 연구를 가짜로 이어붙이지 않으며 최고 후보/부모 후보는 원래 100세대의 동일 원장에서 다시 선택하도록 함.

## 수정 절차

1. `tests/integrations/test_academic_same_session_extension.py` 기존 same-ID extension 5 PASS. 원본 100/100 `COMPLETED`, `all_proposed_hypotheses_measured=true`, 미결 계획 없음, gateway와 cycle DB `PRAGMA quick_check=ok`, 다른 학술 gateway `RUNNING` 없음, 실주문 비활성 검증.
2. Quant 전용 MCP PID 3314의 gateway 쓰기를 `SIGSTOP`으로 일시 중단하고 **기존 스크립트** `scripts.extend_completed_academic_session`로 원본 100→150 extension. SQLite 온라인 백업 경로 `state/moon-http/backups/g100-to-g150-correction-20261027-same-session` (보호된 비공개 상태 폴더). 확장 후 동일 세션 ID, 동일 G100 증거 헤드, `100/150 AWAITING_PLAN` 확인. `SIGCONT`로 동일 PID 복귀. Quant URL/OAuth/설치 플러그인/주문 설정/별도 연구 원장 변경 없음.
3. 대시보드의 기존 `latest-created-session`만으로는 새로 등록된 **잘못된 50세대**가 원본 extension보다 앞서므로, 명시적 작업자 활성 세션 파일 `state/moon-http/research/config/active-dashboard-session.json`을 도입. 활성 ID와 선택 시점 최신 SQLite 세션 rowid를 보존. 최신 rowid가 활성 시점 이후로 늘어나면 새 세션으로 자동 전환(이전 신규 연구 탐색 방식 유지). 잘못된/부정확한 ID는 fail closed. 다른 세션의 원장/계보 변경이나 가짜 150세대 합산 없음.
4. Supervisor 관리 8081/8082 대시보드만 재시작하고 새 코드 활성화. 조회 8081·8082 모두 원본 `100/150`, 후속 G101 제출 후 `101/150` 및 증거 연결 true. 이전 별도 50세대는 `45/50`으로 그대로 확인.
5. 실제 ChatGPT MCP Plan→Diagnosis로 G101 1세대 수행. 선택된 signed S7 개발 부모(기존 G67)에서 G94 참조 RSI14>48 regime entry 필터 1개를 검증해 G101 **+197.2453%**, MDD **23.2323%**, 35거래(개발 데이터) 기록. G101 증거 헤드 `02f77477d111b55e80c53b36c3c6f858daf14ea148526430a6974d5e2ed2804e`, `previous_evidence_hash`=G100 헤드. RSI exit45→43 S7 대조 **수익 178.9734%, RETURN_WORSE**로 자식 승격 없음. `get_algorithm_research`/웹 8082 `101/150 AWAITING_PLAN` 확인.

## 검증/제약

- 활성 세션 선택 관련 신규 테스트 2 PASS(운영 활성 원본 선택, 향후 신규 세션 생성 후 전환, 잘못된 선택 오류), 기존 대시보드 회귀 및 same-ID 연장 검증 **총 26 PASS**.
- Ruff 변경 코드 PASS, mypy 변경 Python 소스 PASS, SQLite chain true. 이전 전체 mypy 오류 51건은 범위 밖이며 개선된 것으로 주장하지 않음.
- 기존 2026년 비PIT 개발 데이터 반복 선택의 편향과 독립 OOS 부재는 그대로. G101 결과는 개발 백테스트이고 실전 승인/수익성 증명이 아님.
- 완전 자동 무인 GPT 50세대 수행은 검증되지 않음. 최종 완료까지 **남은 49세대는 실제 Plan/Diagnosis 루프로 별도 실행되어야** 하며 수행되지 않은 세대를 완료로 계수하지 않는다.
- 기존 고정 URL, OAuth, PCP, Quant MCP 정체성, Moon 원래 인프라, 주문/OOS 안전 경계 미변경. 테스트·코드·운영 보존, 잘못 만든 독립 연구 계보 삭제 금지.

## 다음 허용 범위

G102~G150을 **동일 원본 세션**에서 각 GPT 가설/계획→비용 반영 백테스트→진단·S7→증거 계승으로 진행, G94 최고 기록 보존, 발전 여부는 엄격한 동기간 QQQ 비교와 미사용 OOS에서 별도로 평가. 다음 고정 순서 V05→T4→V01–V04→V06→V07 불변. 유지되는 사업 목표는 개별 QQQ 수동 최적화가 아닌 완전자율 연구 엔진 검증.
