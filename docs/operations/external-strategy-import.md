# 외부 전략 가져오기 운영 절차

## 목적

외부 GitHub 전략을 현재 하네스의 Strategy IR로 변환하고, 중복 여부와 백테스트 가능 여부를 확인한다. 이 절차는 모의투자 주문도 실행하지 않는 연구 전용 절차다.

## 기본 명령

로컬 파일 또는 디렉터리:

```powershell
python cli.py import-strategies --source path\to\strategy.py --strategies-dir strategies
python cli.py import-strategies --source path\to\repo --strategies-dir strategies
```

GitHub 저장소:

```powershell
python cli.py import-strategies `
  --repo https://github.com/ORG/REPO.git `
  --ref main `
  --strategies-dir strategies
```

KIS의 기존 10개 builder preset:

```powershell
python cli.py import-strategies `
  --repo https://github.com/koreainvestment/open-trading-api `
  --ref main `
  --kis-presets `
  --strategies-dir strategies
```

먼저 확인만 하려면 `--dry-run`을 추가한다. 가져오기 결과의 `normalized` 수와
`review_required` 수를 확인한 뒤 실제 저장을 수행한다.

## 처리 규칙

1. 저장소는 임시 디렉터리에 clone하고 지정한 ref의 실제 commit을 기록한다.
2. Python은 실행하지 않는다. AST와 리터럴 구조만 읽는다.
3. KIS `builder_state`는 등록 메타데이터, 지표, 진입·청산, 위험 설정을 Strategy IR로 변환한다.
4. `StrategyDefinition`의 동적 builder나 custom Lean처럼 IR로 표현할 수 없는 동작은 폐기하지 않고 `REVIEW_REQUIRED`로 저장한다.
5. 중복은 원본 경로가 아니라 정규화된 의미 지문으로 판정한다.
6. `strategies/imported`에는 전체 분석 기록을, `strategies/normalized`에는 변환된 IR을 저장한다.
7. `strategies/catalog.json`에는 비밀정보가 없는 상태·출처·중복·검토 사유만 기록한다.
8. 가져오기 성공은 백테스트 성공이나 Champion 승격을 의미하지 않는다.

## 확인 방법

```powershell
python -m pytest tests/strategy_import tests/integration/test_kis_strategy_import.py -q
python cli.py import-strategies --repo https://github.com/koreainvestment/open-trading-api --ref main --kis-presets --dry-run
```

대시보드의 `전략 카탈로그`에서 다음을 확인한다.

- 전략 ID와 출처
- `변환 완료` 또는 `검토 필요`
- `신규`, `완전 중복`, `부분 중복`
- 동적 실행 필요 등 변환 불가 사유

API 키, APP secret, 계좌번호, `.env`, raw source dump는 결과에 저장하거나 출력하지 않는다.
