# Quant [12/16] V01~V04 독립 PIT/OOS 실증 준비·구역 격리 검증

**검토일:** 2026-11-10 · **상태:** DATA_ACCESS_FIX_VERIFIED / INDEPENDENT_OOS_BLOCKED

## 확인된 자료와 실행 경계
- 신규 실제 QQQ DEVELOPMENT/SEALED_OOS 가격 원본, 독립 공급자 발표 시각/기존 값의 시점별 revision 이력, 독립 corporate-action 공개 시각·원본 배당/분할, 확정 유동성/스프레드 비용, 이전과 겹치지 않는 OOS 기간/데이터의 외부 증거가 현재 Moon 마운트에 없어 **독립 실제 OOS 0회**. 데이터가 저장소에서 보이지 않는다고 영구 삭제되었다고 단정하지 않는다.
- 사용자 승인으로 이전 G1~G150 및 과거 선택 전략은 **새 G1의 부모·기억·성과에 계승하지 않음**. Task 11 설계에서 언급한 구 G94/96/106 등의 별도 독립 성과 검증도 현재는 자료/시점 증거 부재로 **NOT_RUN**.
- `assess_historical_vintage`는 현재 캡처가 과거 결정 시각보다 늦으면 차단하고, 타임존/거래일 종가/미발표 증빙을 `UNATTESTED_SNAPSHOT`으로 분류한다. `audit_qqq_corporate_asof` 역시 배당·분할의 ex-date나 최신 조정 가격을 당시에 발표된 값으로 인정하지 않는다. `sealed_oos_precommit`은 DEVELOPMENT 후보만 독점 쓰기로 봉인하며 봉인 OOS 가격을 열지 않는다.

## 테스트로 재현한 구역 접근 결함과 최소 수정
- **RED:** `DataZone`은 `str, Enum`으로 정의되어 있다. 기존 `InMemoryDataProvider.read(zone, role=...)`의 `zone is DataZone.SEALED_OOS` 검사에 문자열 `"sealed_oos"` 전달 시 `is` 검사는 실패하지만, 하단 딕셔너리에서는 `"sealed_oos" == DataZone.SEALED_OOS`이므로 봉인된 OOS 값을 찾을 수 있다. `role="research"` 및 `role="promotion_validation"`의 SEALED_OOS 우회, VALIDATION 우회, zone 라벨과 실제 데이터 라벨 불일치 경로를 새 테스트로 재현했다.
- **GREEN:** `core/data/access.py`는 먼저 `DataZone(zone)`으로 정규화·검증하고, **정규화된 열거형**으로 권한 검사를 실시한다. 실제 반환 데이터 `selected.zone`이 요청한 구역과 같지 않으면 거부한다. 기존 승인된 `promotion_gate`의 실제 SEALED_OOS 읽기는 계속 가능하지만 `research` / 일반 검증 역할은 계속 차단. 지원하지 않는 문자열이나 null/숫자 입력도 `DataAccessDenied`으로 fail closed. 외부 읽기 권한 확대 없음.
- 기존 `ResearchPermissions`/실주문 비활성, 기존 OOS sealed 데이터 존, StrategyIR/정본 평가/세대 경계, ChatGPT 32 MCP / OAuth URL, 데이터 스냅샷/벤더 계약 **변경 없음**.

## 실제 검증 결과
- 새로운 우회 방지·라벨 불일치·입력 오류 회귀를 포함한 `tests/core/test_data_zones.py` **15 PASS**.
- 데이터 구역·가격 출처·OOS 사전 봉인·데이터 시점·기업행동·공개 증빙·캡처 이력·원본 거버넌스 **68 PASS**.
- `ruff check .` **PASS**, 수정 `core/data/access.py` mypy **PASS**, `git diff --check` **PASS**.
- 전체 `pytest -q -x -p no:cacheprovider`: **458 PASS, 1 FAIL** 후 중단. 선행 단계와 동일한 `tests/dashboard/test_fresh_original_dashboard.py::test_readonly_sqlite_bridge_matches_original_contracts`가 이 worktree에 없는 `state/moon-http/fresh-20261021/session-id.txt`를 요구해 `FileNotFoundError`. **전체 수트 PASS 아님**. 새 OOS 구역 코드가 직접 실패했다는 증거는 없음.
- 증거는 통합된 **합성 fixture 및 계약 테스트**. 실제 독립 OOS 데이터·실수익률·신규 GPT 10/100세대·독립 평가가 성공했다는 주장은 허용되지 않는다.

## 실제 OOS 수행을 위한 결손 전제(차후 독립 검증)
- 최초 연구 결과를 보기 **전에** 신규 코호트의 데이터 SHA/기간·공급자 정본 공개 시점·기업행동/가격 수정 이력과 공개 시각·독립 OOS 출처/접근 권한·슬리피지/비용/유동성·벤치마크·선택 전략/사용 평가기/통과 기준을 불변 원장에 고정해야 한다.
- 외부 독립 데이터 담당자가 실제 공급자 증거를 준비하기 전 `promotion_gate`를 연구자에게 전달하거나 실제 `SEALED_OOS` 결과를 연구 메모리/S7/S8 또는 다음 세대에 복귀시키면 안 된다.
- **상태:** 코드 권한 우회 결함 수정 완료, 독립 데이터 및 PIT 증거는 계속 **BLOCKED**, 실 OOS 평가 **0회**, 봉인 OOS 연구 접근 **0건**, 주문 **0건**.

다음 [13/16] Task 12: V06 실주문 OFF 상태의 연구 신호/종이매매 안전성 검사. T4 실모델 및 독립 OOS가 미완료였다는 사실은 릴리스 판정까지 분리 유지.
