# Quant V3 지표·차트 통합 A17 — 정식 릴리스 게이트 재진단 (2026-11-01)

**상태:** 개발 브랜치 개선·관측, 공식 Release `NO-GO`; `main` 미병합, 서비스 미배포, 독립 OOS 미접근, 주문 OFF.

## 원인과 실제 개선

- 호스트 PATH에 `uv` 실행 파일이 없어 `task_validate(profile=release)`가 exit 127로 중단되었다. **기존 호스트에 보관돼 있던 uv 0.13.6 실행 파일을 `/usr/local/bin/uv`에 설치**했으며 `uv --version`으로 확인했다. 기존 Moon/Quant 프로세스와 URL·OAuth, Git 저장소의 의존성 잠금 파일은 변경하지 않았다.
- `uv run --locked --extra dev ruff check .`: **PASS**. 공식 Moon `task_validate(profile=release)`도 Ruff는 PASS, 그다음 Mypy에서 실패. 실패 근거: `.venv/lib/python3.12/site-packages/numpy/__init__.pyi`의 Python 3.12 `type` 구문이 프로젝트 Mypy Python 3.10 대상으로 파싱되지 않아 중단. Python 3.12 기본 설치 결과 NumPy 2.5.3·Pandas 3.0.6이 선택됨.
- Python 3.10.22를 별도로 설치하고 격리 환경(`/tmp/quant-chart-py310-20261101`)에서 lock을 변경하지 않고 `mypy .`를 실행. **35개 파일·309 오류**. 타입 검사 대상 370 파일(벤더 소스 `ta/*`, 오래된 `scripts/*`, 일부 연구·테스트·application). Python 3.12 강제 대상에서도 **35개 파일·308 오류**. 릴리스 전체 통과로 보고하지 않음.
- 이번 통합에서 수정한 `dashboard/service.py`와 신규 `scripts/v3_chart_verified_p9_bridge.py`는 타입 명시 방식을 정리했다. 코드 동작은 보존하며 명시적으로 `dict[str, Any]` 반환 변수를 선언해 전체 mypy의 `redundant-cast` 경고와 좁힌 import 진단의 `Any` 반환 충돌을 동시에 없앴다. 변경한 Python 파일 두 개의 좁힌 Mypy 검사 PASS. **미확인 전체 오류를 무시하도록 설정/검사 기준을 완화하지 않음.**
- 3.10 격리 환경에서 실제 Lab P9 결합·차트 및 scope-governance 관련 `13 PASS`(차트 9+거버넌스 4). 기본 등록 487개+차트 연구 44개 총 531개 구성, QQQ 실제 개발 1508봉 결합, OOS/주문 미접근. 예전 `195 PASS / 1 SKIP` 확대 검증은 그대로 유효.
- 전체 `python -m pytest -q`: Python 3.12 lock 환경에서 시도했으나 도구 작업 상한 **300초에서 SIGTERM, 약 40% 진행 중단**. 종료 코드 0의 전체 실행 결과가 아니므로 전체 PASS로 보고하지 않음. 원본 연구 원장 및 서비스 상태 불변.

## 아직 차단된 수락 게이트

1. 프로젝트 Mypy의 Python 3.10 대상/NumPy stubs·typed dependencies 호환 전략을 명시하고 전체 기존 타입 오류를 실제 수정해 정상 통과. `mypy .` 명령 축소나 Python 3.12로만 검사 대상을 바꾸어 문제를 숨기지 말 것.
2. 전체 Pytest 환경·장시간 실행을 끝까지 완료하여 실패/스킵을 전수 보고. 300초 중단은 완료로 계산 불가.
3. 독립 검토/CI 및 원본 운영 대시보드 브라우저에서의 인증 포함 접속 검증 후에만 main 병합/배포 검토.
4. 기존 300세대 연구 원장·부모/해시·MCP/OAuth·실거래 OFF·sealed OOS 보호 유지, 새 연구 세대 0.

**권고:** 릴리스 검증이 끝나기 전에는 Draft PR에서 검토. 전체 타입 오류/전체 테스트를 해결하지 않은 브랜치를 보호된 main에 바로 병합하지 않음.
