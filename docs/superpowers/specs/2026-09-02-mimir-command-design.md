# Mimir 명령 인터페이스 설계

## 목표

PowerShell에서 `Mimir /research 20`으로 Codex 기반 Paper-only 자동연구를 직접 실행하고,
기존 `quant>` REPL 안에서도 `Mimir /research 20`을 같은 방식으로 사용할 수 있게 한다.

## 범위

- 독립 실행 명령: `Mimir /research 20`, `/status`, `/help`, `/chat`
- 기존 REPL 별칭: `quant> Mimir /research 20`
- 두 진입점이 동일한 연구·대화 구현을 재사용
- 전략·데이터 기본 경로를 `.env` 또는 마지막 연구 상태에서 해석
- 연구는 유한 세대만 허용하고 KIS 주문 기능은 호출하지 않음

## 경로 해석

연구 원본과 데이터는 다음 우선순위로 찾는다.

1. 명령줄 옵션 `--source`, `--data`, `--series-data`
2. `.env`의 `MIMIR_SOURCE`, `MIMIR_DATA`, `MIMIR_SERIES_DATA`
3. `state/system/research_loop.json`의 마지막 `config`
4. 필수 경로가 없으면 명확한 오류를 출력하고 실행하지 않음

`Mimir /research 20`은 현재 작업 디렉터리를 프로젝트 루트로 사용하며, 기존 Codex
실행 provider가 KIS·OpenAI 비밀값을 자식 프로세스에 전달하지 않는 정책을 그대로 따른다.

## 명령 동작

- `/research N`: `run_autoresearch`를 N세대 실행
- `/status`: 기존 대시보드 상태를 JSON으로 출력
- `/chat TEXT`: 읽기 전용 Codex 질의
- `/help`: 사용 가능한 명령과 옵션 출력
- `/stop`: 중지 요청 상태를 출력하며, 동기 실행 중인 연구의 강제 종료는 `Ctrl+C`로 수행

REPL에서 `Mimir` 접두어는 기존 슬래시 명령으로 정규화한다. 기존 `/mode autoresearch`와
연구용 `--source`, `--data` 검증은 유지한다.

## 오류·안전

- 세대 수가 없거나 양의 정수가 아니면 실행하지 않음
- 기본 전략·데이터 경로를 찾지 못하면 실행하지 않음
- `Mimir /research`에서 주문 client, KIS 계좌 client, live mode를 호출하지 않음
- 자동연구는 현재처럼 유한 실행으로 제한

## 검증

- 직접 명령의 slash 명령 변환과 경로 우선순위 테스트
- REPL 안에서 `Mimir /research`가 `/research`로 정규화되는지 테스트
- 연구·상태·도움말·대화 명령 dispatch 테스트
- 잘못된 세대 수·누락된 경로·주문 미호출 테스트
- pytest, Ruff, MyPy 전체 검증
