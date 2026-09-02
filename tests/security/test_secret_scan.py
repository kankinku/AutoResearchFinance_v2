from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.secret_scan import (
    EXIT_ERROR,
    EXIT_FINDINGS,
    EXIT_OK,
    UnsafeRedactionError,
    main,
    redact_sensitive_text,
    scan_repository,
    scan_text,
    tracked_files,
)


def _kis_key() -> str:
    return "K" * 20


def _kis_secret() -> str:
    return "S" * 40


def test_scan_text_finds_kis_credentials_without_returning_values() -> None:
    key_name = "KIS_" + "APP_" + "KEY"
    secret_name = "KIS_" + "APP_" + "SECRET"
    text = f"{key_name}={_kis_key()}\n{secret_name}='{_kis_secret()}'\n"

    findings = scan_text(text)

    assert {finding.rule for finding in findings} == {"kis-credential"}
    assert all(_kis_key() not in finding.detail for finding in findings)
    assert all(_kis_secret() not in finding.detail for finding in findings)


def test_scan_and_redact_export_assignments() -> None:
    key_value = "K" * 20
    password_value = "P" * 20
    key_name = "KIS_" + "APP_" + "KEY"
    original = "\n".join(
        [
            f"export {key_name}={key_value}",
            f"export PASSWORD=\"{password_value}\"",
        ]
    )

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {
        "kis-credential",
        "credential-assignment",
    }
    assert key_value not in redacted
    assert password_value not in redacted
    assert redacted == "\n".join(
        [
            "export KIS_APP_KEY=[REDACTED]",
            'export PASSWORD="[REDACTED]"',
        ]
    )
    assert scan_text("Exporting a password is ordinary prose.") == []


def test_scan_and_redact_assignments_at_shell_command_boundaries() -> None:
    values = ("A" * 8, "B" * 8, "C" * 8, "D" * 8)
    password_name = "PASS" + "WORD"
    original = "\n".join(
        [
            f'env {password_name}="{values[0]}";',
            f"echo ok; {password_name}={values[1]};",
            f'true && {password_name}="{values[2]}" || {password_name}={values[3]}',
        ]
    )

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    assert all(value not in redacted for value in values)
    assert redacted == "\n".join(
        [
            f'env {password_name}="[REDACTED]";',
            f"echo ok; {password_name}=[REDACTED];",
            f'true && {password_name}="[REDACTED]" || {password_name}=[REDACTED]',
        ]
    )
    assert scan_text("echo " + password_name + "=" + values[0]) == []
    assert scan_text("run " + password_name + "=" + values[0]) == []


def test_scan_and_redact_unquoted_shell_value_with_comma() -> None:
    value = "abc," + "D" * 12 + "," + "E" * 8
    original = "PASSWORD=" + value

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    assert value not in redacted
    assert "E" * 8 + "\n" not in redacted
    assert redacted == "PASSWORD=[REDACTED]"
    assert scan_text("A comma in ordinary prose, is harmless.") == []


def test_short_realistic_bearer_token_is_detected_without_prose_false_positive() -> None:
    bearer = "b" * 8

    findings = scan_text("Authorization: Bearer " + bearer)

    assert {finding.rule for finding in findings} == {"bearer-token"}
    assert bearer not in findings[0].detail
    assert scan_text("Authorization: Bearer token") == []


def test_scan_text_finds_quoted_json_credentials() -> None:
    value = "V" * 24
    app_key_field = "app" + "key"
    app_secret_field = "app" + "secret"
    text = (
        '{"' + app_key_field + '": "' + value + '", "'
        + app_secret_field + '": "' + value + '"}'
    )

    findings = scan_text(text)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    assert all(value not in finding.detail for finding in findings)


def test_scan_and_redact_bare_credential_names_without_leaking_values() -> None:
    key_value = "K" * 20
    secret_value = "S" * 20
    token_value = "T" * 20
    secret_name = "sec" + "ret"
    original = "\n".join(
        [
            f"{'k' + 'ey'}='{key_value}'",
            '{"' + secret_name + '": "' + secret_value + '"}',
            f"{'to' + 'ken'}={token_value}",
        ]
    )

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    values = (key_value, secret_value, token_value)
    assert all(value not in finding.detail for finding in findings for value in values)
    assert redacted == "\n".join(
        [
            "key='[REDACTED]'",
            '{"secret": "[REDACTED]"}',
            "token=[REDACTED]",
        ]
    )
    assert all(value not in redacted for value in values)


def test_scan_and_redact_prefixed_password_names_without_prose_false_positives() -> None:
    password_value = "P" * 20
    passwd_value = "D" * 20
    password_name = "DB_" + "PASSWORD"
    passwd_name = "db_" + "passwd"
    original = "\n".join(
        [
            f"{password_name}='{password_value}'",
            '{"' + passwd_name + '": "' + passwd_value + '"}',
        ]
    )

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    values = (password_value, passwd_value)
    assert all(value not in finding.detail for finding in findings for value in values)
    assert redacted == "\n".join(
        [
            "DB_PASSWORD='[REDACTED]'",
            '{"db_passwd": "[REDACTED]"}',
        ]
    )
    assert all(value not in redacted for value in values)
    assert scan_text("The password is stored securely.") == []


def test_scan_text_finds_pem_bearer_and_credential_assignment() -> None:
    bearer = "ey" + "J" * 30 + "." + "a" * 30 + "." + "b" * 30
    credential_value = "p" * 18
    private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
    auth_line = "Authorization: " + "Bearer " + bearer
    text = "\n".join(
        [
            private_key_header,
            auth_line,
            "pass" + f"word = '{credential_value}'",
        ]
    )

    findings = scan_text(text)

    assert {finding.rule for finding in findings} == {
        "pem-private-key",
        "bearer-token",
        "credential-assignment",
    }
    rendered = " ".join(finding.detail for finding in findings)
    assert bearer not in rendered
    assert credential_value not in rendered


def test_scan_text_allows_examples_and_short_benign_values() -> None:
    api_key_name = "api" + "_key"
    api_secret_name = "api" + "_secret"
    text = "\n".join(
        [
            "KIS_" + "APP_" + "KEY=your-kis-app-key",
            "KIS_" + "APP_" + "SECRET=<replace-me>",
            "KIS_" + "REAL_APP_KEY=",
            "KIS_" + "REAL_APP_SECRET=",
            "api" + "_key='secret'",
            f"{api_key_name}=your-api-key",
            f"{api_secret_name}=your-api-secret",
            "pass" + "word = 'placeholder'",
        ]
    )

    assert scan_text(text) == []


def test_scan_and_redact_short_non_placeholder_credential() -> None:
    value = "N" * 5
    original = "key='" + value + "'"

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    assert value not in redacted
    assert redacted == "key='[REDACTED]'"


def test_scan_text_ignores_non_literal_mapping_expressions() -> None:
    assert scan_text("{key: record.get(key)}") == []
    assert scan_text("result = {**base, key: value}") == []
    assert scan_text("api_key: str | None") == []


def test_scan_and_redact_line_start_yaml_credentials() -> None:
    api_value = "Y" * 20
    password_value = "P" * 20
    api_name = "api" + "_key"
    original = f"{api_name}: {api_value}\npassword: {password_value} # keep\n"

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    assert api_value not in redacted
    assert password_value not in redacted
    assert redacted == (
        f"{api_name}: [REDACTED]\npassword: [REDACTED] # keep\n"
    )


def test_scan_and_redact_javascript_declarations_preserve_syntax() -> None:
    values = ("J" * 20, "L" * 20, "V" * 20, "E" * 20)
    key_name = "API" + "_KEY"
    password_name = "PASS" + "WORD"
    secret_name = "API" + "_SECRET"
    token_name = "TOKEN"
    original = "\n".join(
        [
            f'export const {key_name} = "{values[0]}";',
            "let " + password_name + " = '" + values[1] + "';",
            "var " + secret_name + " = " + values[2] + ";",
            "const " + token_name + ' = "' + values[3] + '" && run();',
        ]
    )

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    assert all(value not in redacted for value in values)
    assert redacted == "\n".join(
        [
            f'export const {key_name} = "[REDACTED]";',
            "let PASSWORD = '[REDACTED]';",
            "var API_SECRET = [REDACTED];",
            'const TOKEN = "[REDACTED]" && run();',
        ]
    )


def test_function_expression_is_not_a_credential_assignment() -> None:
    value = "F" * 20
    original = 'password = os.getenv("' + value + '")'

    assert scan_text(original) == []
    assert redact_sensitive_text(original) == original


def test_scan_repository_includes_staged_blob_and_counts_unique_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    tracked = repo / "tracked.txt"
    value = "I" * 24
    key_name = "api" + "_key"
    tracked.write_text(f"{key_name}={value}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    tracked.write_text("clean worktree text\n", encoding="utf-8")

    files_scanned, findings = scan_repository(repo)

    assert files_scanned == 1
    assert [(path, finding.rule) for path, finding in findings] == [
        ("tracked.txt", "credential-assignment")
    ]
    assert value not in " ".join(finding.detail for _, finding in findings)


def test_short_parenthesized_credential_is_detected_and_redacted() -> None:
    value = "(" + "R" * 3 + ")"
    original = "token=" + value

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    assert value not in redacted
    assert redacted == "token=[REDACTED]"


def test_redact_quoted_values_with_spaces_preserves_shell_syntax() -> None:
    value = "A" * 5 + " " + "B" * 5 + " " + "C" * 5
    original = '  PASSWORD =   "' + value + '"  # audit\n'

    redacted = redact_sensitive_text(original)

    assert redacted == '  PASSWORD =   "[REDACTED]"  # audit\n'
    assert value not in redacted


def test_scan_and_redact_quoted_shell_values_before_command_separators() -> None:
    values = ("A" * 8, "B" * 8, "C" * 8)
    original = "\n".join(
        [
            'PASSWORD="' + values[0] + '";',
            'PASSWORD="' + values[1] + '" && echo done',
            'PASSWORD="' + values[2] + '" || echo fallback',
        ]
    )

    findings = scan_text(original)
    redacted = redact_sensitive_text(original)

    assert {finding.rule for finding in findings} == {"credential-assignment"}
    assert all(value not in redacted for value in values)
    assert redacted == "\n".join(
        [
            'PASSWORD="[REDACTED]";',
            'PASSWORD="[REDACTED]" && echo done',
            'PASSWORD="[REDACTED]" || echo fallback',
        ]
    )


def test_redact_escaped_json_quoted_value_preserves_valid_json() -> None:
    value = "A\\B\"C " + "D" * 8
    original = json.dumps({"password": value, "status": "ok"})

    redacted = redact_sensitive_text(original)

    assert json.loads(redacted) == {
        "password": "[REDACTED]",
        "status": "ok",
    }
    assert value not in redacted


def test_redact_backslash_escaped_json_object_syntax() -> None:
    value = "E" * 20
    original = r'{\"password\":\"' + value + r'\",\"status\":\"ok\"}'

    redacted = redact_sensitive_text(original)

    assert redacted == r'{\"password\":\"[REDACTED]\",\"status\":\"ok\"}'
    assert value not in redacted
    assert json.loads(redacted.replace(r'\"', '"')) == {
        "password": "[REDACTED]",
        "status": "ok",
    }


def test_redact_sensitive_text_replaces_credentials_and_preserves_other_text() -> None:
    credential_value = _kis_key()
    bearer = "ey" + "J" * 30 + "." + "a" * 30 + "." + "b" * 30
    original = (
        f"keep this\n{'api' + '_key'}={credential_value}\n"
        f"{'Authorization: ' + 'Bearer'} {bearer}\n"
    )

    redacted = redact_sensitive_text(original)

    assert "keep this" in redacted
    assert credential_value not in redacted
    assert bearer not in redacted
    assert "[REDACTED]" in redacted
    assert redact_sensitive_text("ordinary audit event") == "ordinary audit event"


def test_redact_sensitive_text_removes_unterminated_pem_body() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body = "A" * 32
    original = "prefix\n" + header + "\n" + body + "\nnext audit event\n"

    redacted = redact_sensitive_text(original)

    assert redacted == "prefix\n[REDACTED_PRIVATE_KEY]\nnext audit event\n"
    assert body not in redacted


def test_unterminated_pem_preserves_non_base64_audit_suffix() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body = "A" * 3
    suffix = "next audit event"
    original = "prefix\n" + header + "\n" + body + "\n" + suffix + "\n"

    redacted = redact_sensitive_text(original)

    assert redacted == "prefix\n[REDACTED_PRIVATE_KEY]\n" + suffix + "\n"
    assert body not in redacted
    assert suffix in redacted


def test_ambiguous_multiline_unterminated_pem_fails_closed_without_output() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body_lines = ["A" * 32, "B" * 32]
    original = "prefix\n" + header + "\n" + "\n".join(body_lines) + "\nnext audit event\n"

    with pytest.raises(UnsafeRedactionError):
        redact_sensitive_text(original)


def test_unterminated_short_pem_body_is_redacted_and_suffix_remains() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body = "Q" * 3
    suffix = "audit suffix"
    original = "prefix\n" + header + "\n" + body + "\n" + suffix + "\n"

    redacted = redact_sensitive_text(original)

    assert redacted == "prefix\n[REDACTED_PRIVATE_KEY]\n" + suffix + "\n"
    assert body not in redacted


def test_short_pem_body_followed_by_base64_line_fails_closed() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body = "Q" * 3
    ambiguous_suffix = "R" * 32
    original = "prefix\n" + header + "\n" + body + "\n" + ambiguous_suffix + "\n"

    with pytest.raises(UnsafeRedactionError):
        redact_sensitive_text(original)


def test_one_character_pem_body_followed_by_base64_line_fails_closed() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body = "Q"
    ambiguous_suffix = "R" * 32
    original = "prefix\n" + header + "\n" + body + "\n" + ambiguous_suffix + "\n"

    with pytest.raises(UnsafeRedactionError):
        redact_sensitive_text(original)


def test_short_pem_body_followed_by_audit_text_is_redacted_safely() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body = "Q"
    suffix = "audit event: rotation required"
    original = "prefix\n" + header + "\n" + body + "\n" + suffix + "\n"

    redacted = redact_sensitive_text(original)

    assert redacted == "prefix\n[REDACTED_PRIVATE_KEY]\n" + suffix + "\n"
    assert body not in redacted
    assert suffix in redacted


def test_unterminated_multiline_pem_uses_blank_line_boundary() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body_lines = ["A" * 64, "B" * 3]
    suffix = "C" * 32
    original = "prefix\n" + header + "\n" + "\n".join(body_lines)
    original += "\n\n" + suffix + "\naudit suffix\n"

    redacted = redact_sensitive_text(original)

    assert redacted == "prefix\n[REDACTED_PRIVATE_KEY]\n\n" + suffix + "\naudit suffix\n"
    assert all(line not in redacted for line in body_lines)
    assert suffix in redacted


def test_redact_sensitive_text_removes_complete_pem_body() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    footer = "-----END " + "PRIVATE KEY-----"
    body = "B" * 32
    original = "prefix\n" + header + "\n" + body + "\n" + footer + "\nsuffix\n"

    redacted = redact_sensitive_text(original)

    assert redacted == "prefix\n[REDACTED_PRIVATE_KEY]\nsuffix\n"
    assert body not in redacted


def test_redact_complete_multiline_pem_with_short_final_base64_line() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    footer = "-----END " + "PRIVATE KEY-----"
    body_lines = ["A" * 64, "B" * 64, "C" * 3]
    original = "prefix\n" + header + "\n" + "\n".join(body_lines) + "\n" + footer + "\nsuffix\n"

    redacted = redact_sensitive_text(original)

    assert redacted == "prefix\n[REDACTED_PRIVATE_KEY]\nsuffix\n"
    assert all(line not in redacted for line in body_lines)
    assert footer not in redacted


def test_redact_unterminated_pem_in_json_preserves_closing_syntax_and_suffix() -> None:
    header = "-----BEGIN " + "PRIVATE KEY-----"
    body = "C" * 32
    original = '{"private_key": "' + header + r"\n" + body + '", "status": "ok"}'

    redacted = redact_sensitive_text(original)

    assert json.loads(redacted) == {
        "private_key": "[REDACTED_PRIVATE_KEY]",
        "status": "ok",
    }
    assert body not in redacted


def test_redact_sensitive_text_preserves_assignment_separator_and_spacing() -> None:
    value = "Q" * 20
    original = 'prefix\n  "api_key" :   "' + value + '"\n  suffix\n'

    redacted = redact_sensitive_text(original)

    assert redacted == 'prefix\n  "api_key" :   "[REDACTED]"\n  suffix\n'
    assert value not in redacted


def test_redaction_skips_non_standalone_bare_and_yaml_assignments_like_scan() -> None:
    value = "Y" * 20
    original = "inline password=" + value + "\nprose password: " + value + "\n"

    assert scan_text(original) == []
    assert redact_sensitive_text(original) == original


def test_cli_scans_only_tracked_files_and_emits_machine_checkable_redacted_summary(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    tracked = repo / "tracked.txt"
    untracked = repo / "untracked.txt"
    credential_value = _kis_secret()
    secret_name = "KIS_" + "APP_" + "SECRET"
    tracked.write_text(f"{secret_name}={credential_value}\n", encoding="utf-8")
    untracked.write_text(f"{secret_name}={credential_value}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "scripts" / "secret_scan.py"),
            "--root",
            str(repo),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == EXIT_FINDINGS
    assert "tracked.txt: kis-credential" in result.stdout
    assert "untracked.txt" not in result.stdout
    assert credential_value not in result.stdout
    summary = json.loads(result.stdout.splitlines()[-1].removeprefix("SECRET_SCAN_SUMMARY "))
    assert summary == {"files_scanned": 1, "findings": 1}


def test_cli_returns_zero_for_clean_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "clean.txt").write_text("no credentials here\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "clean.txt"], cwd=repo, check=True)

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "scripts" / "secret_scan.py"),
            "--root",
            str(repo),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == EXIT_OK
    assert result.stdout.strip() == 'SECRET_SCAN_SUMMARY {"files_scanned": 1, "findings": 0}'


def test_cli_returns_exit_code_two_for_non_git_root(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "scripts" / "secret_scan.py"),
            "--root",
            str(missing_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == EXIT_ERROR
    assert "secret scan error" in result.stdout
    summary = json.loads(result.stdout.splitlines()[-1].removeprefix("SECRET_SCAN_SUMMARY "))
    assert summary == {"files_scanned": 0, "findings": 0}


def test_cli_argparse_errors_return_exit_code_two_with_summary() -> None:
    script = str(Path(__file__).parents[2] / "scripts" / "secret_scan.py")
    for arguments in (("--unknown",), ("--root",)):
        result = subprocess.run(
            [sys.executable, script, *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

        output = result.stdout + result.stderr
        summary_line = next(
            line for line in output.splitlines() if line.startswith("SECRET_SCAN_SUMMARY ")
        )
        assert result.returncode == EXIT_ERROR
        assert json.loads(summary_line.removeprefix("SECRET_SCAN_SUMMARY ")) == {
            "files_scanned": 0,
            "findings": 0,
        }


def test_cli_argparse_error_does_not_echo_secret_argument() -> None:
    secret_argument = "X" * 24
    script = str(Path(__file__).parents[2] / "scripts" / "secret_scan.py")

    result = subprocess.run(
        [sys.executable, script, "--unknown", secret_argument],
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == EXIT_ERROR
    assert secret_argument not in output
    summary_line = next(
        line for line in output.splitlines() if line.startswith("SECRET_SCAN_SUMMARY ")
    )
    assert json.loads(summary_line.removeprefix("SECRET_SCAN_SUMMARY ")) == {
        "files_scanned": 0,
        "findings": 0,
    }


def test_cli_help_emits_help_text_and_summary() -> None:
    script = str(Path(__file__).parents[2] / "scripts" / "secret_scan.py")

    result = subprocess.run(
        [sys.executable, script, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == EXIT_OK
    assert "usage:" in output
    summary_line = next(
        line for line in output.splitlines() if line.startswith("SECRET_SCAN_SUMMARY ")
    )
    assert json.loads(summary_line.removeprefix("SECRET_SCAN_SUMMARY ")) == {
        "files_scanned": 0,
        "findings": 0,
    }


def test_cli_short_help_emits_help_text_and_summary() -> None:
    script = str(Path(__file__).parents[2] / "scripts" / "secret_scan.py")

    result = subprocess.run(
        [sys.executable, script, "-h"],
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == EXIT_OK
    assert "usage:" in output
    summary_line = next(
        line for line in output.splitlines() if line.startswith("SECRET_SCAN_SUMMARY ")
    )
    assert json.loads(summary_line.removeprefix("SECRET_SCAN_SUMMARY ")) == {
        "files_scanned": 0,
        "findings": 0,
    }


def test_tracked_files_decodes_invalid_git_filename_bytes_safely(
    monkeypatch, tmp_path: Path
) -> None:
    class Result:
        stdout = b"normal.txt\0invalid-\xff.txt\0"

    monkeypatch.setattr(
        "scripts.secret_scan.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    paths = tracked_files(tmp_path)

    assert len(paths) == 2
    assert paths[0].name == "normal.txt"


def test_main_emits_summary_when_tracked_filename_decoding_fails(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    def fail_to_decode(root: Path) -> list[Path]:
        raise UnicodeDecodeError("utf-8", b"x", 0, 1, "invalid")

    monkeypatch.setattr("scripts.secret_scan.tracked_files", fail_to_decode)

    exit_code = main(["--root", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == EXIT_ERROR
    assert json.loads(output.splitlines()[-1].removeprefix("SECRET_SCAN_SUMMARY ")) == {
        "files_scanned": 0,
        "findings": 0,
    }
