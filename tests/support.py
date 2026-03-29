from __future__ import annotations

import os

_ALLOWED_ENV_NAMES = (
    "APPDATA",
    "COMSPEC",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
)


def build_subprocess_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    for allowed_name in _ALLOWED_ENV_NAMES:
        for actual_name, value in os.environ.items():
            if actual_name.upper() == allowed_name:
                env[actual_name] = value
                break
    env["FINANCE_AUTORESEARCH_ENV_FILE"] = ""
    for name, value in (overrides or {}).items():
        env[name] = value
    return env
