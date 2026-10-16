# T4 — QQQ 매수·보유 대비 개발 수익률 비교 (2026-10-16)

사용자 요청에 따라 기존 Quant Autoresearch 연구 모니터에 QQQ 매수·보유 기준선을 추가한 작업. 기존 20문답 범위, ChatGPT MCP URL/OAuth/32개 도구, 주문 비활성, 100세대 연구 상태는 그대로 보존한다.

## 평가 기간과 데이터

- 기존 GPT 100세대 세션 a84a100b15a242269b554282b01d91c9은 30/100 완료, 다음 계획 입력 대기(AWAITING_PLAN). 장애 정지가 아니라 **외부 모델 입력을 기다리는 대기 상태**. 브라우저 모니터의 3초 polling은 모델 연구 실행을 뜻하지 않는다.
- 동일 개발 데이터 QQQ 2020-01-02~2025-12-31, 거래일 1,508, 데이터 계약 해시 328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6.
- 첫날 QQQ 시가 214.40달러, 마지막 종가 614.31달러. 단순 가격 수익률 +186.5252%.
- 평가 모델과 동일한 academic-research-cost-v1 거래비용 정책: 최초 매수 1회 commission 1bp + spread 2bp + slippage 5bp = 8bp 차감. 첫 시가 전액 매수→마지막 종가 보유 평가, 매도하지 않음. 수익률 +186.2961% (초기 자본 10,000달러 가정). 소수점 주식 보유 가능하다고 보는 연구용 기준선.
- 매수 비용 외의 배당금·배당 재투자·주식분할 검증·세금·최종 매도비용은 미포함. QQQ 공식 총수익률을 뜻하지 않는다. 데이터는 Tiingo 최신 수정본·raw·비PIT 개발 구간이며 독립 OOS가 아님.

## 평가 결과

| 후보 | 같은 개발기간 누적수익률 | QQQ 대비 차이 |
| --- | ---: | ---: |
| QQQ 매수 후 보유 (8bp 비용 반영) | +186.30% | 기준 |
| 완료된 30개 중 최고인 25세대 모델 | +109.78% | −76.52%p |

- QQQ 가격 기준선 자체에는 자산 보유 위험이 있으며, 연구 모델은 다음 바 체결/시장 비활성일도 존재하므로 신호 거래조건의 모든 위험이 동일하다고 주장하지 않는다.
- 최고 모델은 30개 후보 중 개발기간 사후 최적을 고른 것으로 선택 편향·다중검정 위험이 크다. 독립 수익성/거래 GO 미검증.

## 구현

- dashboard/academic_benchmark.py: 원래 QQQ Parquet를 read-only로 읽어 세션 dataset_hash·1d/DEVELOPMENT/raw·심볼·기간을 검사하고 값이 일치할 때만 가격 기준선 계산, 불일치/부재는 UNAVAILABLE.
- dashboard/academic_monitor.py: 각 모델의 QQQ 대비 초과수익률(퍼센트포인트), 최고 모델과 최근 완료 모델의 상대 성과를 원래 세대 SHA 검증 후 계산.
- dashboard/static/academic.html, .css, .js: QQQ 매수·보유 지표 카드, QQQ 대비 초과수익률, 30세대 비교표 열, 개발수익률 그래프 위 수동 보유 기준선. 배당 제외 및 연구 구간의 제약 표시.
- 기존 인증된 localhost 경로 127.0.0.1:2999/academic 유지. 변경되는 것은 독립 연구 모니터 코드뿐이며 Quant MCP/연구 원장을 변경하거나 거래 주문을 실행하지 않는다.


## 배포 및 운영 검증

- 기능 코드 커밋 7e64f421e042a96d6d5cbb44070f4657ba82cdf9 를 GitHub 브랜치 feat/t4-qqq-buyhold-benchmark-20261016에 Push.
- 전체 dashboard + 20문답 범위 잠금 관련 49 테스트 통과, Ruff/Mypy/Node 문법 검사 통과.
- 기존 운영 Quant MCP PID 4010, URL/OAuth/주문 정책/연구 DB는 불변.
- 새 읽기 전용 모니터 코드를 고정 Worktree /shared/moon-workspace/AutoResearchFinance_v2-academic-monitor-qqq-7e64f42에 배치해 loopback 127.0.0.1:8082에서 기동; 원래 모니터 127.0.0.1:8081 프로세스는 롤백용으로 보존.
- Nginx 기존 인증·호스트 포트 2999의 연구 화면/API/static 프록시만 8081에서 8082로 전환. Nginx 문법 검사와 reload 통과; 기존 경로 및 비밀번호 해시 불변.
- 실제 8082 HTTP API 200: 30/100, QQQ BENCHMARK DEVELOPMENT_ONLY +186.29614964744627%, 25세대 최고 모델 대비 −76.52056875367555%p, S7 0건 누락. 새 HTML과 JS/CSS 200 확인.
- 기존 게시 포트 2999에서 보호 화면 응답 200 확인, 익명 화면 접속 401, 기존 Moon health 200 및 Quant MCP 익명 401 확인.
- 상태는 검사 중 AWAITING_PLAN에서 일시적으로 INTERRUPTED / CycleStateError를 표시했다가 30/100, AWAITING_PLAN으로 복구됨. 동시 외부 운영 제어 또는 서버 reconciliation 여부는 미확인. 모니터는 읽기 전용이며 자동 실행·복구/주문을 수행하지 않음.
- Windows Firefox 브라우저에서 로그인·렌더링 최종 확인은 사용자가 해야 함. 권장 접속 주소는 http://127.0.0.1:2999/academic (기존 인증 사용). 원래 8081은 여전히 Windows에 포트 게시되지 않음.
