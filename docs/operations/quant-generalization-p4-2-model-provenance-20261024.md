# Quant AutoResearch — P4-2 모델 판단 출처·체크포인트 증거 체인

**작성일:** 2026-10-24 (KST)
**상태:** 개발 코드·격리 서명 fixture 검증 PASS / 운영 미배포 / 실제 provider 호출 독립 증명 **미달** / 신규 100세대 실행 보류

## 문제 정의

P4 10세대는 실제 ChatGPT 대화로 작성한 계획 및 진단을 MCP 체크포인트에 제출했지만, 원장에는 provider invocation ID 또는 provider가 서명한 요청/응답 영수증이 없었다. 이를 근거 없이 "LLM이 스스로 API 호출·자동 학습했음"으로 승격할 수 없었다.

이번 구현은 증거의 **세 층을 명시적으로 분리**한다.

1. **검증된 정식 세대와 백테스트:** 기존 canonical counted Evidence/해시/S7. 이 코드는 변경·소급 수정하지 않는다.
2. **외부 캡처 수집기(assertion):** 별도의 공개키를 사전 등록한 외부 서명자가 주장한 `provider`, `model`, `invocation_id`, `prompt_hash`, `response_hash`, `decision_log_hash`, 간략한 의사결정 설명. Ed25519가 검증되면 **그 수집기가 기록했다는 사실만** 확인한다.
3. **provider 자체의 실제 호출 증명:** provider 서명 영수증, 원본 API 호출 로그의 독립 감사, 또는 동급의 신뢰할 수 있는 provider 출처가 있어야 한다. **현재 없음.** 그래서 `provider_signed_receipt_verified=false`, `independent_model_invocation_verified=false`를 고정한다. 테스트에서 임의 서명 키로 만든 fixture를 실제 GPT 호출 증거로 주장하지 않는다.

## 구현 내용

- `research/llm/model_provenance_v1.py`: 신뢰된 Ed25519 공개키 + 캡처 서명 검증; 정확한 세션·세대·phase·체크포인트 토큰/컨텍스트 해시/제출 payload 해시 검증. 서명 없는 제출, 위조, 누락 필드, 다른 key/컨텍스트, 중복 invocation, 연속 hash 변경을 거부한다.
- `application/academic_checkpoint_service.py`: P4-1 연구 opt-in에 추가하여 P4-2 opt-in을 요구. `model_capture_enrollments`에 공개키 SHA와 policy를 새 세션 시작 시 고정. `model_capture_receipts`는 세대별 계획(0)→진단(1) 순으로 순서·서명·선행 receipt hash·정식 counted evidence hash를 묶는 append-only 사이드카. 원본 `cycles.sqlite` 세대 내용은 미수정.
- P4-2 활성 세션의 정상 계획/진단 제출은 **서명 캡처 필수**이고, 같은 checkpoint 재제출도 원래 저장된 캡처와 동일해야 한다. 기존 세션에 소급 opt-in 또는 설정 해제에 의한 다운그레이드 불가.
- `get_algorithm_research` 응답은 `model_capture_audit` 및 현재 `model_capture_context_hash`를 표시. 실제 계획·진단 출력과 외부 수집기 서명 문서가 결합되었는지 재검사한 뒤 반환.
- `integrations/chatgpt_mcp_sdk.py`: 기존 도구 이름·필수 항목 유지, 신규 세션의 signed `model_capture` 필드만 선택적으로 노출(서비스 정책은 P4-2 세션에서 필수).
- `integrations/codex_mcp_core.py`: 새 세션/정확히 지정한 기존 opt-in 세션만 활성화. 구성에 private signing key를 저장하지 않고, 신뢰된 외부 수집기의 **public key만** 읽는다.
- 원장 갱신과 캡처 sidecar는 서로 다른 SQLite 파일이므로 process crash로 canonical generation만 commit된 경우가 가능하다. 이런 경우 `reconcile`이 미서명 세대를 완료 처리하지 못하도록 **fail closed**. 향후 별도 서명 복구 프로토콜 없이는 해당 세션 진행 불가. 자동 서명 발급이나 가짜 호출 증거 복구를 만들지 않는다.

### 개발 브랜치 전용 활성화 예시 (운영에 설정하지 않음)

새 격리 세션에만 다음 변수를 동시에 설정한다.

```text
QUANT_MCP_GENERALIZATION_PARENT_V1_NEW_SESSION=1
QUANT_MCP_P4_QUALITY_NEW_SESSION=1
QUANT_MCP_P4_MODEL_CAPTURE_NEW_SESSION=1
QUANT_MCP_P4_CAPTURE_PUBLIC_KEY_HEX=<사전 고정된 외부 수집기 Ed25519 공개키 32바이트 hex>
```

완료 후 생성용 토글을 모두 0으로 복원하고, 동일 **새** 세션 ID로 연결:

```text
QUANT_MCP_P4_MODEL_CAPTURE_SESSION_ID=<새 32자리 세션 ID>
QUANT_MCP_P4_QUALITY_SESSION_ID=<동일 세션 ID>
QUANT_MCP_GENERALIZATION_PARENT_V1_SESSION_ID=<동일 세션 ID>
```

서명자 private key는 이 저장소·환경·DB에 보관하지 않는다. 서비스 자신이 요청/응답 영수증을 조작하도록 private key를 추가하지 않는다. 기존 OAuth, MCP 고정 URL, 대시보드, 주문/OOS 접근 정책은 불변.

## 검증 근거

- 서명 검증/위조·누락·중복·chain/order·canonical evidence 변경 감지, 체크포인트 반환/재제출, 신분 다운그레이드 및 임의 구버전 enrollment 차단, 모델 캡처 없이 복구해 위장하는 것 차단.
- 테스트: 관련 10개 소스 경로의 **77 passed**. 수정 소스 및 신규 테스트 Ruff PASS, 서명 검증 모듈 Mypy PASS.
- `scripts/quant_p4_verify_10gen.py`로 기존 10세대 P4 외부 격리 상태 재감사: 기존 `p4_verified_report.json`과 **정확히 일치**, report hash `22024e6871c0f905b7afc182bc8837acab9bd79d9f86510a8e635efdee813aeb`. 원본 10/10 세대는 새 모델 증거를 가진 것으로 재명명하지 않았다.
- 서명 샘플은 fixture에서 생성한 임의 개인키로 만든 **시뮬레이션 수집기**다. 실제 LLM 호출이 이루어졌거나 프로덕션 외부 collector가 준비된 것은 아니다.

## 남은 한계 및 후속

1. **P4-2 미해결 게이트:** 독립적인 실 provider 요청/응답 ID·provider signature 또는 외부 수집기 실운영 접속, 제출 전 원본 prompt/decision log 안전한 캡처 경로, 호출 추적 비용·인증 체계. 현재 model/provider 문자열은 collector의 **주장**이며 독립 검증 불가.
2. 실패하여 재제출한 계획/진단의 모든 attempt는 accepted checkpoint sidecar에 남지 않으며, `decision_log_hash`는 외부에서 제시하는 해시라 로그 원문 감사를 이 코드가 대신하지 않는다. 시도별 immutable rejection log와 context/output 보존·redaction 정책 추가 검토 필요.
3. cross-DB crash 후 기록 없는 서명 증거를 복원하지 못하는 세션은 차단됨. 동일 서명자 원본 증거가 **사전에 별도로 내구화**된 경우에 한해 엄격한 복구 프로토콜 설계 필요.
4. **다음 P4-3:** S7 schema/실제 submit 허용 metric 일치, 실험 영향 없는 변이와 중복 실패 원인 피드백, 진단 로그 품질 개선. 이후 P4-4 기간별 일반화·비용 stress. 실제 provider 출처 검증 없이 P5 신규 100세대를 '자율 GPT 연구'로 선언하지 않는다.
