# Recovery and rebuild

- A failed job remains `FAILED` with its error; inspect the job ID before retrying.
- Reopen the immutable manifest and verify its experiment hash before reusing a cache hit.
- If a state write is interrupted, read the JSON snapshot and compare its checksum with
  the recorded audit input hash. The state writer uses a temporary file and atomic replace.
- Rebuild a cache only from durable experiment manifests. Do not infer results from a
  partial worker log or overwrite an existing result without a matching hash.
- A sealed-OOS or live-gate failure requires manual intervention. It is never recovered by
  downgrading the zone, disabling a gate, or selecting the previous Champion silently.
