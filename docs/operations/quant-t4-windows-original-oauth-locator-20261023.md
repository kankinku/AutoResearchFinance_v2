# Quant T4 — Windows Docker 호스트 원본 OAuth 상태 탐색

**날짜:** 2026-10-23 KST
**상태:** RECOVERY BLOCKED — 기존 원본 인증 파일 확인 대기, 인증된 신규 GPT 세대 0/10.

## 업무 범위
T4(Q02/Q06/Q15/Q17)의 기존 ChatGPT↔Quant MCP 연결 복구. 기존 OAuth 승인키/고정 URL/등록 DB를 유지하며, 새 OAuth 등록·유료 API 자동 전환·Docker 재시작·주문·봉인 OOS 접근을 하지 않는다. 승인된 순서는 V05→T4 GPT10/100→V01~V04→V06→V07 그대로.

## 직접 확인한 사실
- 연결된 Qaunt_Autoresearch 상태 조회는 여전히 내부 오류.
- 현 Moon 컨테이너의 /shared/moon-workspace, /var/lib/project-moon, 접근 가능한 / 파일명 검사 결과 실제 Quant 승인키·고정 URL·클라이언트 DB를 확인하지 못했다. /tmp/pytest-of-root의 OAuth 파일들은 테스트 픽스처로 실제 인증 자료 아님.
- 활성 Supervisor는 dashboard-only, nginx에 /quant/mcp 없음, Quant 8787 서버가 떠 있지 않음.
- Linux Moon에서는 Windows Docker 호스트 및 현재 마운트되지 않은 원래 Windows 프로젝트/볼륨을 조사할 수 없음.
- 별도 OpenAI API 실행 경로는 OPENAI_API_KEY와 **유료 실행 명시 승인** 필요. 자동 대체 금지.

## 새 Windows 호스트 탐색기
scripts/find_original_quant_oauth.ps1: PowerShell 5.1+용 **완전 읽기 전용 원본 위치 탐색기**.

- Docker inspect의 project-moon-local /shared 바인드 마운트 Windows 원본 경로를 자동 검색 시작점으로 사용. 사용자 기존 과거 프로젝트/백업은 SearchRoots 옵션으로 추가.
- 동일한 state/moon-http 아래 oauth/approval-key, oauth/public-base-url, research/oauth/quant-oauth.sqlite 세 파일이 함께 있는지만 확인.
- 존재 상태가 일부이면 PARTIAL_IDENTITY_DO_NOT_START, 세 파일 후보가 있으면 CANDIDATE_TRIPLET_PRESENT_UNVERIFIED. 파일 3개 발견만으로 기존 클라이언트 인증이 유효하다고 주장하지 않는다.
- 바이너리/인증키/URL/등록 DB 내용은 출력하거나 수정하지 않고, 바인드 마운트와 지정 루트만 제한적으로 재귀 검색. MaxDepth/MaxDirectories 상한으로 불완전 검색은 별도 구분.
- 키 재발급·복사·삭제·새 OAuth 등록·서비스 시작/중지는 없음.

Windows Docker Desktop 호스트 PowerShell에서 기존 프로젝트 체크아웃을 열고, 다음 명령을 실행한다.

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\find_original_quant_oauth.ps1

지정된 다른 과거 프로젝트 폴더를 포함하려면 아래와 같이 경로를 바꾼다. 경로는 예시이지 사용자 경로가 아니다.

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\find_original_quant_oauth.ps1 -SearchRoots "D:\HistoricalResearch"

파일 내용/토큰/키/URL 값은 공유할 필요 없다. STATUS와 세 파일의 PRESENT 여부, 원본이 발견된 상태 루트 위치만 확인한다.

## 검증 및 한계
- 신규 tests/operations/test_quant_windows_auth_locator_contract.py 및 기존 Quant OAuth 안전 검증 관련 테스트 **26 PASS**; Ruff 신규 파일 검사 PASS.
- 현재 Linux Moon에 PowerShell 실행기가 없어 **실제 Windows 동작 테스트는 NOT RUN**. 코드 정적 계약 테스트는 Windows 호스트 탐색 성공을 증명하지 않음.
- 기존 Quant MCP 연결은 여전히 복구되지 않음; 인증 GPT 신규 세대 0/10. G452/G552/OAuth/주문·OOS/운영 서비스 변경하지 않음.
- 후보가 발견되면 기존 issuer, 승인 DB, 저장소 원본 여부 및 원장 출처를 비공개 읽기 전용으로 검증한 뒤에만 동일 승인 신원으로 배포 복구를 검토. 운영 서버를 먼저 새로 띄워 자동으로 인증을 바꾸는 것은 금지.

## 다음 게이트
Windows 호스트 원본 인증 파일 경로 확인 → 기존 issuer/클라이언트/원장 보존 검증 → 동일 Quant MCP 정상 응답 확인 → 실제 GPT 계획·백테스트·진단·S7·후속 세대 원장 10세대 검증.
