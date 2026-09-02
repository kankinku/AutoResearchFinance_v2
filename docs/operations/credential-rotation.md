# Credential rotation and containment

No credentials are committed in the tracked repository. Ignored local files such as `.env` are outside this scanner and require separate local secret-store/environment verification. This is a research harness; live order capability remains absent
and research must remain paper-only.

## Scanner CLI contract

The scanner inspects Git-tracked files only. It does not claim to inspect the
full filesystem, ignored local files, or user-owned `.omx` logs.

Exit codes are stable for automation:

- Exit code 0 means clean: no findings were detected.
- Exit code 1 means findings: one or more credential-like findings were detected.
- Exit code 2 means scan error: tracked files could not be enumerated or read.

Each run ends with a machine-readable line in this form:

`SECRET_SCAN_SUMMARY {"files_scanned": <integer>, "findings": <integer>}`

The JSON object contains the integer fields `files_scanned` and `findings`.
`files_scanned` is the number of unique Git-tracked paths; checking both the
current worktree and the Git index does not count a path twice.

For an unterminated PEM, redaction is fail-safe and bounded. An embedded
JSON/string closing quote or an explicit blank-line boundary permits removal of
the contiguous valid PEM body lines, including short final lines. Without one
of those boundaries, it removes only the header and first valid body line, then
preserves the following line. A following base64-looking line is not silently
consumed when no boundary establishes that it belongs to the PEM; ambiguous
material must be handled as exposed evidence and the scanner does not consume
arbitrary remainder text. The reusable helper raises `UnsafeRedactionError` before returning output for an ambiguous multi-line fallback—including a short first body line followed by a base64-looking line; callers must not persist or output the original text and must quarantine the event.

## When credential-like material is found

Treat a possible credential as exposed even if the match is uncertain. This
applies to `.omx` logs and to any tracked or untracked artifact. The scanner is
an aid, not proof that an external system is safe.

1. Revoke or disable the old KIS/API credentials in the external provider.
2. Issue replacement credentials with the minimum required permissions.
3. Update the external secret store and the environment used by the research
   process. Do not put replacements in this repository.
4. Invalidate sessions and tokens that could have been created with the old
   credentials.
5. Verify that research remains paper-only: no orders, live trading, or order
   capable integration is enabled.
6. Rerun `python scripts/secret_scan.py` from the repository root and inspect
   the result without copying any secret into an issue, commit, or log.

Preserve evidence needed for incident review without copying secrets into new
files. Do not auto-delete or rewrite user-owned `.omx` logs; record only safe
metadata such as the path, finding rule, timestamp, and remediation status.
The scanner and its redaction helper never intentionally print matched values.
