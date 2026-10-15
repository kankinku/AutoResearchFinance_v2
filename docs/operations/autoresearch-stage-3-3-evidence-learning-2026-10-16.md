# Quant Autoresearch D05 / 3-3 — S7 증거 기반 실패 학습·다음 반증 설계

기준 2026-10-15 UTC / 2026-10-16 KST. 코드 커밋 `5a903e1`, 기능 브랜치 `feat/d05-evidence-learning-20261016` GitHub Push 완료. 기존 운영 MCP 서버 **미배포**.

## 실제 변경 및 확인

- `research/llm/experiment_learning.py` 신규: 이미 저장된 S7 개발 구간 대조실험을 다시 해시 검증한다. 원 세대 `evidence_hash`, 진단 `diagnostic_proposal_hash`, 각 `hypothesis_id`·자식 전략 해시·예측 방향·측정 메트릭, 거래 수·실행 변동을 서로 대조한다. 변조된 보고·불일치·누락 참조는 fail-closed.
- `application/academic_checkpoint_service.py`: 새로운 Plan 제공 시 기초 `research_direction`와 별개로 `experiment_learning`을 생성해 다음 GPT 프롬프트에 넣는다. 기존 세대 증거/실험 보고를 덮어쓰거나 별도 LLM API키를 요구하지 않는다.
- 분류: 관측된 변화 없음, 예측 방향 불일치, 아예 거래가 없어진 자식 전략, 측정 불가능 지표, 개발 구간 일치지만 아직 불확실한 가설, 다중 비교 과대해석 위험. 유형에 따라 `ABLATION`·`PARAMETER`·`RULE_STRUCTURE` 등의 다음 실험 방식 **제안만** 제공한다. 기존 GPT가 작성한 원 가설과 대안 설명을 함께 노출한다.
- 중복 자식 전략 해시와 이전 실패 유형을 알려주되, 근거 없이 자동 전략·미래 데이터를 생성하거나 승격하지 않는다. 출력 최대 최근 12개 비교·지양할 자식 해시 20건, 세대 최대 100개. 실패 학습은 기존 불변 세대/S7 로그에서 필요할 때 재구성되므로 새 임의 메모리 원장 없음.
- S7 개발 구간에서 방향이 맞았다는 사실은 **인과 설명 또는 실제 알파 입증이 아님**. 실제 GPT가 제안을 수용하는지, 임의 탐험·무작위 대조군/반증 성과 또는 매매 수익 향상은 검증하지 않았다.

## 실제 검사 / 다음 순서

- T0 신규 `tests/research/test_experiment_learning_d05.py`: **17 PASS**. 원본 반증·대안 제시, 상태별 실패 방향, 무거래 자식, 다중 비교 주의, 해시·메트릭·실행 수 변조/불일치 거부, 반복 child hash, 실측 없는 세대의 미측정 분리, 외부 모델을 흉내 낸 2세대 Plan→Diagnosis 컨텍스트 유지 확인.
- T1 관련 선별 회귀: 신규 D05 + 기존 S8 + 기존 MCP 세션 `51 PASS`. Ruff 변경 파일 PASS, Mypy 관련 2개 소스 PASS, Git diff 정적 검사 PASS.
- T2 전체 MCP 32개 실호출, T3 전체 회귀, T4 실제 GPT 10/100세대+중단 복구, T5 시점 원본·OOS·거래비용·무작위 비교 수익성, T6 페이퍼트레이딩 등 미실행.
- **다음 D06 / 4-1:** QQQ/SPY 등 복수 자산의 일봉 시점·거래 캘린더 정렬, 시점별 데이터 가용성 제한과 StrategyIR 다자산 연구 검증.
- 그 뒤 D07 MCP 32개 계약, D08 소스 병합·서버 배포·롤백, V01~V07 최종 검증 순서.

기존 `https://project-moon.taild689f9.ts.net/quant/mcp`, OAuth, 저장된 연구/가격 원장, sealed OOS 격리, 실거래 주문 비활성·외부 GPT MCP 기본 방식 모두 불변.
