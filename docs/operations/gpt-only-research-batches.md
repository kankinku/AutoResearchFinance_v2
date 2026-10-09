# Quant Autoresearch: GPT 전용 세대 배치 운영 (2026-10-10)

## 운영 원칙

사용자가 **"N세대 진행하고 결과는 나중에 물어볼게"**라고 요청하면, ChatGPT는 연결된 Quant MCP에서 전략·Frontier·데이터를 조회해 유효한 단일 ResearchIntent와 세대 수(1~100), 세대별 후보 수(1~64)를 지정한 다음 **`start_research_batch`를 한 번 호출한다.** 서버는 별도 Python 워커에서 N세대까지 결정론적 변경·평가를 실행하며 **Codex CLI, 별도 LLM, 외부 AI API를 호출하지 않는다.**

사용자가 대화를 종료하거나 중간에 다른 질문을 해도 서버 워커는 계속 작동한다. **사용자가 완료 여부를 다시 물으면** `get_research_batch_status`(가장 최근 작업 또는 job_id)로 상태를 확인하고, 완료 시 `get_research_batch_report`로 실적을 확인한다. 서버는 자동으로 새 채팅 메시지를 보내지 않는다.

- `start_research_batch`: `source_path`, `data_path`, `intent`, `generations`(필수), `count`, `method`, `seed` 및 검증 한계 파라미터. 파일 경로·데이터·부모 전략·feature·변경 연산은 연구 엔진이 검증한다. 한 번에 실행할 수 있는 배치는 1개이며, 시작 직후 `job_id`, 상태, 검증된 소요 시간 추정값을 반환한다.
- `get_research_batch_status`: `job_id` 생략 시 최근 배치. QUEUED, RUNNING, COMPLETED, CANCELLED, FAILED, INTERRUPTED 상태와 완료 세대 수, ETA 근거, ETA 초 및 ISO UTC 완료 예상 시각 반환. 한국어 최종 답변에는 KST로 변환한다.
- `get_research_batch_report`: 각 세대별 실제 실행 초, 후보 수, 퍼널 상태별 건수, Evidence로 검증된 전략 승계 ID, 총 측정 시간. `final_report_ready`가 참인 완료/중단 상태에서만 최종 결과로 표현한다. 중간 조회는 중간 보고로 명확히 구분한다.
- `cancel_research_batch`: 중단 요청만 기록하며 현재 평가 세대는 완료된 뒤 중단한다. 이미 기록된 Evidence는 지우지 않는다.
- `get_research_evidence`: 서버가 생성한 `research_run_id`로 불변 평가 증거 별도 점검.

## ETA 산식

1. 동일 연구 방식(`method`)의 최근 최대 40개 **실측 세대 소요 시간**을 보관한다. 후보 수(`count`)에 비례해 보정한 중앙값으로 최초 시간을 예측한다.
2. 이번 배치가 실제로 세대를 완료하면 최근 최대 7개 세대 소요 시간의 중앙값을 이용해 보정한다.
3. `예상 남은 초 = 측정 기반 예상 세대별 초 × 남은 세대 수`. 서버는 UTC 절대 시각도 제공한다. ETA는 데이터량/복잡도/캐시/CPU·GPU 자원 상태에 따라 달라지는 **근사치이며 완료 보장이 아니다**.
4. 기록이 전혀 없으면 허위 예상 시간을 만들지 않고 `eta_basis=insufficient_data`와 ETA 없음으로 보고한다.

## 세대별 GPT 판단 여부

- GPT는 **시작 시** 가설·허용된 변경 조건을 판단한다. 장시간 백테스트 동안 추가 GPT 호출은 없다.
- 서버는 각 세대 후 **불변 Evidence로 확인된 eligible successor만 후속 부모 전략으로 채택**한다. 단순 평가 응답만으로 champion 승격하거나 sealed OOS를 통과시킬 수 없다.
- 매 세대 GPT가 새로운 가설을 작성해야 하는 **동적 LLM 재계획**은 현재 배치 실행 계약이 아니다. 그 경우 배치를 여러 짧은 단위로 나누어 사용자가 결과를 요청할 때 GPT가 다음 가설을 작성한다.

## 중단·보안·데이터

- SQLite(`state/.../system/gpt-research-batches.sqlite`)에 배치 메타데이터, 상태, 시간 기록이 저장된다. 실제 평가 Evidence는 기존 체인에 저장된다. 로컬 비밀·계좌 정보·인증 토큰은 응답/DB에 저장하지 않는다.
- 워커/호스트가 강제 종료되면 `INTERRUPTED`로 기록하고 남아 있는 완료 세대를 보고한다. **자동 재개는 미구현**이므로 중단된 세대를 이미 완료했다고 주장하지 않는다.
- 별도 GPT MCP 서버는 기존 Moon의 고정 `https://project-moon.taild689f9.ts.net/quant/mcp` 경로와 Quant 전용 OAuth 인증을 사용한다. 기존 Moon 서비스 및 자격 증명을 변경하지 않는다.
- `orders_enabled=false` 유지. 일반 전략 연구만 허용하며 KIS 실거래 주문, sealed OOS 승인 권한 없음.
- 구 CLI `autoresearch`, `research-intent`, `terminal`, Mimir local research/chat는 제거하거나 실행 차단됐다. Codex 로컬 subprocess 구현은 호환성 실패 안내 이외에는 존재하지 않는다.

## 검증

`tests/integrations/test_gpt_research_batches.py`: 실제 subprocess N세대 실행, 상태·Evidence 및 시간 기록 검증; 두 번째 실행에 과거 실행시간 사용; 잘못된 부모/권한 외 인수/허용 범위 바깥 N세대 거절.

`tests/integrations/test_chatgpt_mcp_stdio.py`: 실제 공식 MCP 연결에서 도구 목록 및 연구 실행 검증.
