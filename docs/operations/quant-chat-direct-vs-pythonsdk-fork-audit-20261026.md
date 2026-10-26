# Quant 비교 전수조사 — 채팅형 Quant vs PythonSDK Fork

**작성일:** 2026-10-26 KST
**분석 범위:** Quant AutoResearch만. 별도 Star 프로젝트 제외.
**분석 기준:** 실제 운영 중인 채팅형 Quant 코드 `bfd72057a52cb82f88decf481fbf547b52718750`, PythonSDK Fork의 마지막 기록 커밋 `d0c08627b7dd3972cceb8c310c34620225205886`.
**롤백:** 통합 개발 브랜치에서 2026-10-26 **최근 8시간 이내** 첫 부모 계보의 18개 커밋 내용 취소. 추적 가능한 *새 복원 커밋* `29e8527bb1cb1dff756b0bc5674bde3b8e6aee61`. 기존 PythonSDK Fork의 코드/미커밋 작업, 운영 서버/원장/OAuth/고정 URL 및 다른 브랜치 불변.
**문서 성격:** 코드를 실제 비교한 기능별 전수조사와 전체 변경 파일 목록. 모든 차이 파일 **99개**를 별도 TSV에 나열했지만, 모든 실행 경로의 운영 품질과 모델 비용을 실험으로 입증한 것은 아님.

## 1. 결론부터: 어떤 구조를 유지해야 하나?

**정답은 현재 채팅에서 직접 Quant MCP 도구를 호출하는 구조를 유지하는 것**입니다.

- **채팅형 Quant:** 사용자가 이 대화에서 "다음 연구"라고 말하면, **이 대화의 GPT**가 연구 방향을 결정하고 Quant MCP를 호출합니다. Quant가 Python으로 백테스트·증거기록을 수행하고 GPT가 돌아온 결과를 판단합니다. 연구를 위해 **별도 Codex 모델 세션을 만들어 호출할 필요가 없습니다.**
- **PythonSDK Fork:** 별도의 `openai_codex` 모델 스레드를 만들어 각 세대의 `plan`과 `diagnosis`를 작성하도록 실험한 경로가 있습니다. 그래서 지금 대화 외에 **Codex SDK 사용량/제한**이 발생할 수 있습니다. 이 방식으로 계속 연구를 돌리는 것은 사용자가 피하려는 방식입니다.
- **중요한 구별:** 채팅형 Quant에도 MCP 프로토콜의 **서버 라이브러리인 SDK**가 사용됩니다. 그것은 툴 연결 구현이지, 유료 Codex 모델을 새로 호출하는 `openai_codex` SDK와 **다릅니다**. MCP 서버 라이브러리를 삭제하거나 OAuth를 다시 등록할 이유는 없습니다.
- **한계:** ChatGPT 대화 자체에도 사용량·대화 길이 제한이 있으며, 채팅형으로 바꾸면 같은 대화에서의 100~500세대가 자동·무제한 보장되는 것은 아닙니다.

## 2. 실제 비교 대상과 증거

| 구분 | 채팅형 Quant (현재 운영 기준) | PythonSDK Fork (별도 보존) |
|---|---|---|
| 코드 기준 SHA | `bfd7205` (2026-10-24) | `d0c0862` (2026-10-26 00:16) |
| 실행 위치 | `AutoResearchFinance_v2-fresh-research-20261021` | `AutoResearchFinance_PythonMCP` |
| 누가 연구 방향을 결정? | **현재 ChatGPT 대화의 GPT** | 선택형 **별도 Codex SDK 모델** 또는 외부 콜백 |
| 주요 통신 | ChatGPT ⇄ Quant MCP (고정 URL·OAuth) | Python MCP·stdio/SDK fork-local 실험 |
| 투자 백테스트 | 동일 계열 Quant 원장/학술 연구 엔진 | 기존 Quant 코드를 기반으로 별도 추가 게이트 |
| 기록/재개 | 세대 원장·checkpoint·S7 | 기존 기능 외 모델 출처/서명·조정/복구 추가 |
| 100세대의 의미 | 매 세대 GPT 판단이 필요 | 별도 모델 호출 또는 테스트 콜백이 필요; mock 100은 진짜 GPT 100이 아님 |
| 독립 2026 OOS | 봉인·검증 별도 | 봉인·검증 별도 |
| 주문 | OFF | OFF |
| 오늘 이후 사용 방침 | **유지** | **삭제하지 않되 모델 반복 호출용으로 사용하지 않음** |

**두 소스의 파일 수준 전체 비교:** PythonSDK Fork는 운영 채팅형 Quant보다 **54개 커밋 뒤에 별도로 진행된 계보**이며, `git diff` 기준 **99개 파일이 다릅니다: 신규 86개·기존 변경 13개**, 약 13,379줄 추가와 52줄 제거입니다. 저장소 차이는 Python SDK 호출기뿐 아니라 Quant 실험 규칙·검증·데이터 준비·문서·테스트까지 포함하므로 **Fork 전체가 불필요하다는 뜻이 아닙니다.** 파일별 99개 변경의 전체 목록은 [`quant-chat-vs-pythonsdk-fork-file-inventory-20261026.tsv`](quant-chat-vs-pythonsdk-fork-file-inventory-20261026.tsv) 참조.

## 3. 기능별 전수 비교 (핵심 영역 14개)

| 영역 | 채팅형 Quant에서 가능? | Fork에서 달라진 점 | 사용자 관점의 결론 |
|---|---|---|---|
| ① **GPT가 연구 계획 작성** | 이 채팅 GPT가 MCP `get_algorithm_research`/`submit_algorithm_plan` 사용 | `CodexStructuredDecisionHost`가 별도 Codex `thread.run`으로 JSON 생성 가능 | **별도 모델 호출 경로 불필요** |
| ② **결과를 GPT가 진단** | `submit_algorithm_diagnosis`, GPT가 현재 채팅에서 판단 | Codex가 diagnosis마다 별도 턴 사용 가능 | **채팅 직접 유지** |
| ③ **백테스트·거래비용** | Quant 엔진이 계산 | 주된 연구엔진은 공유하며 Fork에 추가 평가 모듈 존재 | 공유 핵심 엔진 활용 |
| ④ **세대 이어하기/중단** | 원장과 checkpoint·중복 제출 검증 존재 | 별도 `t4_checkpoint_orchestrator`/재조정 경로 추가. 이 경로의 모형 100세대는 실제 GPT 100세대 아님 | 이미 되는 부분 재구현 금지 |
| ⑤ **S7 대조 실험** | 기존 Quant S7 존재 | Fork의 선택형 `P4-3` S7 사전 품질검사·반복거절 증거 강화 | 가치 있으나 SDK 모델 호출과 별개 |
| ⑥ **부모 전략 계승** | 기존 검증 계승·부모 선택 경로 | `generalization_parent_v1` 추가로 연도·상황·중복 고려 | 연구 품질 기능만 별도 검토 가능 |
| ⑦ **가짜 방어전략 제거** | 기존 최소 거래/부모 게이트 존재 | `P4-1` 시장 노출률·거래수 보정 비교 | 신규 세션 선택형, 운영 반영 미확인 |
| ⑧ **시장·비용 스트레스** | 원래 개발 백테스트/QQQ 비교 경로 있음 | `p4_cost_regime_stress`, `historical_robustness`, `p4_random_candidate_control` 추가 | 모델 SDK 없이 활용 가능한 연구 평가 아이디어 |
| ⑨ **모델 판단 진위** | GPT가 현재 대화에서 도구를 직접 호출 | Fork는 서명 수집기·receipt 검증(`P4-2`) 추가, Codex 자체 메타데이터는 독립 인증 아님 | 분리 운영과 서명은 연구 증거 보강일 뿐 추가 모델 호출을 정당화하지 않음 |
| ⑩ **지표 조건·단위** | 기존 전략/기술지표 컴파일 | `t4_feature_units` 범위·실제 체결 확인 보강 | 유효한 안전성 개선이지만 기존 운영 변경 승인 전 검증 필요 |
| ⑪ **데이터/QQQ 재현성** | 연구 DB/해시/QQQ 비교 기준 이미 존재 | Fork는 별도 2020~2025 QQQ 일봉 1,508개 개발 자료 pin/import | 서로 다른 세션 성능을 수익률만으로 비교 금지 |
| ⑫ **장기 연구 기억** | 기존 세대 역사·`cross_generation_memory`·연구 요약/문맥 크기 제한 존재 | 이번 오후 별도 통합 실험 M0/M1의 생성된 기억 검색은 **복구 대상으로 제거**; Fork D3/D4와 혼동 금지 | 유용성 인정, **새 SDK 반복 구조 없이 추후 재평가** |
| ⑬ **대시보드·연결** | 운영 중인 고정 URL·OAuth 및 기존 대시보드 | Fork에 일부 대시보드 재구성·원장 감사 등 차이 존재 | 운영 서버, 사용자 미커밋 수정 미접촉 |
| ⑭ **LLM 비용/사용량** | 별도 Codex 모델 SDK 호출 불필요. ChatGPT 자체의 사용량 제한은 남음 | SDK 실제 연구 로그에 다수 토큰·턴 사용량 기록 | **Fork를 기본 연구 실행자로 사용하지 않음** |

**중요한 범위 경계:** Fork의 P3/P4 보완 기능들은 별도 개발 코드·테스트로 존재하지만, 오늘의 롤백 후 **현재 운영 채팅형 Quant에 전부 적용되었다는 뜻이 아닙니다.** 안전하다고 판단되는 것은 모델 호출 의존성을 제거한 별도 검증 작업 이후에만 도입해야 합니다.

## 4. 가장 중요한 실제 비용 증거

- `docs/operations/python-mcp-20gen-real-codex-development-audit-20261025.md`에 기록된 **Fork의 기존 실험 20/20세대**: SDK 로그에는 **53개 모델 출력 이벤트**, **1,715,590 토큰**이 적혀 있습니다. 재시도·실패 결과가 포함돼 있습니다.
- 이 수치는 **SDK 로컬 로그에 집계된 토큰**이며 실제 청구액, 독립적으로 서명된 제공자 호출 증빙 또는 2026 샘플 외 성과를 증명하는 자료는 아닙니다.
- 20세대를 넘어 100~500세대를 동일 방식으로 계획 없이 반복하면 SDK 사용량 부담이 커질 가능성이 있습니다. 실제 비용 비례 추정치는 하지 않습니다.
- Fork의 20세대 연구는 **운영 채팅형 Quant의 68세대와 데이터·세션·프로세스가 다릅니다.** 20세대와 68세대의 수익률을 직접 비교하는 것은 부적절합니다.
- 별도 Codex SDK 호출을 없애는 것은 사용자 목표에 맞지만, ChatGPT 채팅의 사용량·토큰 소비까지 0으로 만드는 것은 아닙니다.

## 5. 최근 8시간 롤백이 정확히 무엇을 했는가?

- 검사 시점 2026-10-26 약 20:16 KST로부터 최근 8시간(약 12:16 이후)에 통합 브랜치 첫 부모 경로로 들어온 **18개 커밋**이 대상. 범위에는 14:25~14:27의 3개 소스 병합과 14:27 이후 코드·문서·메모리 검색 등이 포함됩니다.
- 소스 자체는 `git restore --source=bfd7205 --staged --worktree`로 복구하고 **이력을 삭제하거나 `reset --hard`로 원격을 강제 덮어쓰지 않았습니다.** 복원 커밋 `29e8527`을 별도 통합 브랜치에 Push했고 로컬/원격 SHA 일치 확인. 그 커밋의 **Git tree SHA = 운영 채팅형 기준 `bfd7205`의 tree SHA** (파일이 정확히 동일함).
- 복구 차이는 **151개 파일**, 20,897줄 제거·65줄 복원. 이 151개는 *통합 브랜치와 복구 기준 간 차이*이지, 원본 Fork에서 물리적으로 151개 파일을 삭제했다는 뜻이 아닙니다.
- 기존 개별 연구 브랜치/과거 기록은 그대로 있고 `AutoResearchFinance_PythonMCP`의 `d0c0862` 및 **미커밋 4개 파일**은 변경·삭제하지 않았습니다. 운영 Quant의 dashboard 미커밋 변경 파일/백업, 세션 DB, 승인키, OAuth, `8787` 서버 프로세스 및 공개 URL도 건드리지 않았습니다.
- 최근 8시간 내의 추가 SDK lease/feature parity, M0/M1 handoff·조회, 오늘의 통합 관련 설계서는 통합 브랜치의 *현행 작업 트리에서 제외*되었고 Git 과거 커밋에 남아 있습니다. 10월 24~25일 이전 별도 브랜치에서 쌓은 연구 작업은 해당 브랜치에서 보존됩니다.

## 6. 무엇을 남기고 무엇을 하지 말아야 하나?

**그대로 남길 것:** 채팅에서 직접 쓰는 32개 Quant MCP 도구, 현재 GPT 계획·진단과 Quant 계산의 역할 분리, 실험/세대 해시·S7·재개 기능, 실주문 OFF, 2026 OOS 봉인, 기존 OAuth·URL·대시보드.

**이번에 다시 만들지 않을 것:** 별도 Codex SDK가 GPT를 호출하고 Moon 또는 Quant를 대신 운영하는 자동 루프, SDK 전용 모델 세션, 사용량이 큰 반복 프롬프트를 구동하기 위한 SDK 중심 압축·재호출 계층.

**향후 정말 필요한 개선만:** 사용자가 **현재 ChatGPT 대화에서** “다음 세대 진행”을 요청하는 구조를 유지하면서, 하나의 Quant MCP 호출에서 기존 계산·원장 재조회·요약을 더 효율적으로 처리하고, 매번 재전송하는 자료가 있는지 확인. 별도의 Codex 모델 호출은 기본값으로 사용하지 않음. 경제적 효과·OOS 적격성은 실제 근거로만 판단.

## 7. 검증과 재현

확인한 근거:

- `git log --first-parent`의 최근 8시간 커밋 18개와 해당 commit/tree hash.
- 복원 전 `git diff bfd7205 a3c45bc`: 총 **151개 파일**, 복원 후 `git rev-parse HEAD^{tree}`와 `bfd7205^{tree}` 비교 `MATCH`.
- `git diff --name-status bfd7205 d0c0862`: **99개 파일(86 A + 13 M)** 전부 [`TSV 파일`](quant-chat-vs-pythonsdk-fork-file-inventory-20261026.tsv)에 기록.
- 모델 호출 실제 코드: Fork `application/t4_codex_structured_model.py`의 `Codex.thread_start`/`thread.run`/`token_usage`, Fork `application/t4_checkpoint_orchestrator.py`의 별도 콜백 및 mock 거절 분기.
- ChatGPT용 MCP: `integrations/chatgpt_mcp_sdk.py`의 32도구 `ChatGPTMCPAdapter`·`OAuth`; 별도 모델 호출 없음.
- 연구·S7·선출의 차이: `application/academic_checkpoint_service.py`와 Fork 추가 `research/llm/generalization_parent_v1.py`, `s7_quality_gate_p4_3.py`, `model_provenance_v1.py`, `research/indicator_engine/p4_cost_regime_stress.py`.
- 실험 수치: Fork 독립 감사문서 `python-mcp-20gen-real-codex-development-audit-20261025.md` (원본 Fork에만 존재, 삭제되지 않음).
- **복구 후 회귀 검증:** 채팅형 Quant MCP, 실제 개발 데이터 학술 세션, 중복 제출 재생·동일 세션 재개·원장 기억 관련 **40개 pytest PASS**, 저장소 전체 `ruff check .` PASS, 게시되는 MCP 도구 **32개**, SDK 모델 반복 실행용 신규 파일 3개가 현행 복원 트리에서 존재하지 않음 확인. 전체 저장소 pytest/전체 mypy 및 실제 GPT 연구 호출은 실행하지 않았습니다.
- **운영 읽기전용 검사:** 현행 원본 `cycles.sqlite`의 100세대 목표 중 **68개 완료**, 대기 상태 `AWAITING_PROVIDER`; gateway에서는 **다음 계획 대기**. 데이터 변경/세대 추가/신규 모델 호출 없음.
- 검증 대상은 커밋된 소스이며 Fork에 남아 있는 **미커밋 4개는 파일 메타데이터와 비변경 여부만 확인**했습니다. 그 내용을 무시하고 Fork가 운영과 완전히 일치한다고 주장하지 않습니다.

**한계:** 파일 단위 전수 비교를 수행했지만, 모든 99개 파일을 실행해 품질을 평가하거나 기존 Fork의 P4 플래그 활성 상태를 실제 운영에 재현하지 않았습니다. 그 단계는 독립 과제로 남습니다. 기존 데이터·실거래/OOS·공개 연결은 의도적으로 변경하지 않았습니다.
