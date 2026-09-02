# Mimir 명령 인터페이스 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PowerShell과 기존 `quant>` REPL에서 `Mimir /research 20`을 사용할 수 있도록 공통 명령 디스패처를 추가한다.

**Architecture:** `runtime/mimir.py`가 독립 명령의 slash 문법과 설정 경로를 해석하고 기존 Codex provider 및 자동연구 함수를 호출한다. `runtime/terminal.py`는 REPL 입력의 `Mimir` 접두어만 기존 명령으로 정규화하여 연구 로직을 중복 구현하지 않는다.

**Tech Stack:** Python 3.10+, argparse, pytest, Pydantic 기반 기존 연구 runtime, setuptools console script.

---

### Task 1: 직접 명령 디스패처 테스트

**Files:**
- Create: `tests/runtime/test_mimir.py`

- [ ] **Step 1: 직접 명령의 slash 정규화 테스트 작성**

`/research`, `/status`, `/help`, `/chat`가 내부 명령 이름으로 변환되고, 빈 명령과 잘못된 세대 수가 거부되는지 테스트한다.

- [ ] **Step 2: 경로 우선순위 테스트 작성**

명령줄 경로가 `.env`와 마지막 연구 상태보다 우선하고, 마지막 상태의 `config`가 fallback으로 사용되는지 테스트한다.

- [ ] **Step 3: 테스트가 RED인지 확인**

Run: `python -m pytest tests/runtime/test_mimir.py -q`

Expected: `ModuleNotFoundError` 또는 아직 구현되지 않은 dispatch 함수 오류.

### Task 2: 직접 Mimir 구현

**Files:**
- Create: `runtime/mimir.py`
- Modify: `pyproject.toml`
- Test: `tests/runtime/test_mimir.py`

- [ ] **Step 1: slash 명령과 연구 설정 해석 구현**

`Mimir /research N`을 양의 정수로 검증하고, 다음 순서로 `source`, `data`, `series_data`를 선택한다.

```python
explicit option > MIMIR_* setting > state/system/research_loop.json config
```

누락 시 실행하지 않고 필요한 설정 이름을 포함한 `ValueError`를 반환한다.

- [ ] **Step 2: 기존 runtime 연결 구현**

연구는 `CodexExecProvider.from_env`, `ResearchDirector`, `run_autoresearch`를 직접 호출하고, 상태는 `DashboardStateReader`, 대화는 `CodexChatProvider`를 재사용한다. KIS order client는 import하거나 호출하지 않는다.

- [ ] **Step 3: console script 등록**

`pyproject.toml`에 다음 entry point를 추가한다.

```toml
[project.scripts]
mimir = "runtime.mimir:main"
```

Windows에서는 명령 이름의 대소문자를 구분하지 않으므로 설치 후 `Mimir`로 호출할 수 있다.

- [ ] **Step 4: 테스트 GREEN 확인**

Run: `python -m pytest tests/runtime/test_mimir.py -q`

Expected: 모든 Mimir dispatch 및 안전성 테스트 PASS.

### Task 3: 기존 REPL 별칭 연결

**Files:**
- Modify: `runtime/terminal.py`
- Modify: `tests/runtime/test_terminal.py`

- [ ] **Step 1: 실패 회귀 테스트 작성**

`parse_terminal_command("Mimir /research 20")`가 `TerminalCommand("research", ("20",))`을 반환하는 테스트를 추가한다.

- [ ] **Step 2: 접두어 정규화 구현**

대소문자를 무시하고 정확한 `Mimir` 접두어를 제거한 뒤 기존 slash parser로 전달한다. 일반 문장 내부의 `Mimir` 문자열은 변경하지 않는다.

- [ ] **Step 3: 기존 REPL 테스트와 함께 실행**

Run: `python -m pytest tests/runtime/test_terminal.py tests/runtime/test_mimir.py -q`

Expected: 전체 PASS.

### Task 4: README 사용법 반영

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 설치 명령과 직접 실행 명령 추가**

`python -m pip install -e .` 후 `Mimir /research 20`을 실행하는 흐름과 `python -m runtime.mimir /research 20` fallback을 기록한다.

- [ ] **Step 2: REPL 사용법과 기본 경로 설정 추가**

`.env`의 `MIMIR_SOURCE`, `MIMIR_DATA`, `MIMIR_SERIES_DATA`와 `state/system/research_loop.json` fallback을 설명한다.

- [ ] **Step 3: 미지원·안전 동작 명시**

무한 반복·실전주문·자동 주문은 지원하지 않으며, `/stop`은 강제 종료가 아니고 `Ctrl+C`가 즉시 종료 방법임을 명시한다.

### Task 5: 통합 검증 및 커밋

**Files:**
- Modify only files listed above

- [ ] **Step 1: 직접 도움말 실행**

Run: `python -m runtime.mimir /help`

Expected: Mimir 명령 사용법 출력.

- [ ] **Step 2: 전체 검증**

Run: `python -m pytest -q`, `ruff check .`, `python -m mypy .`, `git diff --check`

Expected: pytest PASS, Ruff PASS, MyPy no issues, diff check clean.

- [ ] **Step 3: 변경 파일만 원자적 커밋**

```powershell
git add runtime/mimir.py runtime/terminal.py pyproject.toml tests/runtime/test_mimir.py tests/runtime/test_terminal.py README.md
git commit -m "feat: add Mimir command interface"
```
