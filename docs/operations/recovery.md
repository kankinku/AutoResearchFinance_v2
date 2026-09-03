# Recovery and rebuild

- A failed job remains `FAILED` with its error; inspect the job ID before retrying.
- Reopen the immutable manifest and verify its experiment hash before reusing a cache hit.
- If a state write is interrupted, read the JSON snapshot and compare its checksum with
  the recorded audit input hash. The state writer uses a temporary file and atomic replace.
- Rebuild a cache only from durable experiment manifests. Do not infer results from a
  partial worker log or overwrite an existing result without a matching hash.
- A sealed-OOS or live-gate failure requires manual intervention. It is never recovered by
  downgrading the zone, disabling a gate, or selecting the previous Champion silently.

## ResearchIntent 복구

Codex 자동연구 응답은 canonical typed operation 계약을 통과해야 한다. 조건을 추가하거나
교체하는 operation은 `Condition` 객체를 사용해야 하며, `regime_filters.0`처럼 리스트 원소를
add 대상으로 지정하거나 조건 위치에 boolean·list·빈 객체를 넣은 응답은 `INTENT_VALUE_TYPE`
또는 `INTENT_PATH_TARGET` 오류로 백테스트 전에 거부된다.

복구 agent가 반환한 payload의 SHA-256 서명이 같은 세대에서 이미 실패한 서명과 같으면
추가 Codex 호출을 생략하고 `repair_skipped_duplicate` 이벤트를 남긴다. 오류와 처리 결과는
`state/system/repair-knowledge.jsonl`에 append-only로 쌓인다. `FALLBACK`은 부모 Strategy IR을
변경하지 않고 평가한다. 이 과정은 연구를 계속하기 위한 오류 격리이며 전략 성능 성공을
의미하지 않는다.
