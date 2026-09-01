from __future__ import annotations

from scripts.snapshot_frontier import snapshot_payload
from scripts.tag_champion import build_tag_command


def test_lineage_scripts_build_reproducible_snapshot_and_tag_command() -> None:
    payload = snapshot_payload(
        champion_hash="abc123",
        generation=8,
        frontier_hashes=("z", "a"),
    )
    assert payload["frontier_hashes"] == ["a", "z"]
    assert build_tag_command("abc123", 8) == ["git", "tag", "champion/g0008-abc123"]
