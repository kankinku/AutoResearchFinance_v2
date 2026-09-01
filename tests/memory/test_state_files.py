from __future__ import annotations

from pathlib import Path

from memory.state_files import StateFileStore


def test_state_file_store_writes_atomically_and_reads_checksum(tmp_path: Path) -> None:
    store = StateFileStore(tmp_path)

    checksum = store.write("frontier", {"families": {"momentum": "c1"}})
    loaded = store.read("frontier")

    assert loaded.payload == {"families": {"momentum": "c1"}}
    assert loaded.checksum == checksum
    assert not list(tmp_path.glob("*.tmp"))


def test_state_file_store_rejects_invalid_json_name(tmp_path: Path) -> None:
    store = StateFileStore(tmp_path)

    try:
        store.write("../escape", {})
    except ValueError as exc:
        assert "name" in str(exc)
    else:
        raise AssertionError("path traversal should be rejected")
