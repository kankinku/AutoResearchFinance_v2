"""Import an existing non-PIT development snapshot into the isolated MCP fork.

No vendor download, no original research writes, no sealed OOS, no orders.
The source manifest is an integrity claim only, not PIT attestation.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from core.data.quality import market_data_quality


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def import_pinned_development_data(
    fork_root: Path, source_path: Path, manifest_path: Path,
) -> dict[str, Any]:
    """Copy only a hash-pinned QQQ development snapshot, never overwrite data."""
    root = fork_root.resolve(strict=True)
    source = source_path.absolute()
    manifest_file = manifest_path.absolute()
    if source.is_symlink() or manifest_file.is_symlink():
        raise ValueError('untrusted source symlink')
    if source.suffix != '.parquet' or not source.name.startswith('QQQ_'):
        raise ValueError('expected immutable QQQ development Parquet')
    if not source.is_file() or not manifest_file.is_file():
        raise ValueError('source Parquet and manifest must exist')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if (
        manifest.get('classification') != 'NON_PIT_DEVELOPMENT_ONLY'
        or manifest.get('orders_enabled') is not False
    ):
        raise ValueError('only non-PIT development data with orders disabled are allowed')
    expected_hash = manifest.get('parquet_sha256')
    actual_hash = _sha(source)
    if not isinstance(expected_hash, str) or actual_hash != expected_hash:
        raise ValueError('source parquet sha256 differs from pinned manifest')
    dataset = ParquetDataProvider.read(source)
    if dataset.zone is not DataZone.DEVELOPMENT or dataset.timeframe != '1d':
        raise ValueError('sealed/validation or non-daily data cannot enter this cohort')
    if not dataset.bars or {bar.symbol for bar in dataset.bars} != {'QQQ'}:
        raise ValueError('dataset is not a nonempty single-symbol QQQ cohort')
    if (dataset.dataset_hash != manifest.get('dataset_hash')
        or len(dataset.bars) != manifest.get('bars')
        or dataset.bars[0].timestamp.date().isoformat() != manifest.get('start')
        or dataset.bars[-1].timestamp.date().isoformat() != manifest.get('end')):
        raise ValueError('canonical dataset identity/count/range differs from source manifest')

    relative = Path('state/python-mcp/development-qqq') / source.name
    destination = root / relative
    # Reject every destination ancestor symlink before creating any directory.
    dest_dir = destination.parent
    for ancestor in (
        root / 'state', root / 'state/python-mcp', dest_dir,
    ):
        if ancestor.is_symlink():
            raise ValueError('destination research path cannot follow a symlink')
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not dest_dir.resolve().is_relative_to(root):
        raise ValueError('destination research path escaped the isolated fork')
    if destination.is_symlink():
        raise ValueError('destination symlinks forbidden')
    if destination.exists():
        if _sha(destination) != expected_hash:
            raise ValueError('existing development copy differs; refusing overwrite')
    else:
        fd, tmp_name = tempfile.mkstemp(prefix='.qqq-copy-', dir=dest_dir)
        try:
            with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
                for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                    out.write(chunk)
            if _sha(Path(tmp_name)) != expected_hash:
                raise ValueError('copied development data failed sha256 check')
            os.chmod(tmp_name, 0o444)
            # Atomic no-overwrite publication; existing immutable copies stay intact.
            try:
                os.link(tmp_name, destination)
            except FileExistsError:
                if destination.is_symlink() or _sha(destination) != expected_hash:
                    raise ValueError('concurrent destination change; refusing overwrite') from None
        finally:
            Path(tmp_name).unlink(missing_ok=True)
    if _sha(destination) != expected_hash:
        raise ValueError('destination integrity check failed')
    quality = market_data_quality(dataset)
    return {
        'status': 'VERIFIED_EXISTING_DEVELOPMENT_COPY',
        'data_path': relative.as_posix(),
        'classification': 'NON_PIT_DEVELOPMENT_ONLY',
        'source_sha256': actual_hash,
        'dataset_hash': dataset.dataset_hash,
        'bars': len(dataset.bars),
        'first_date': manifest['start'],
        'last_date': manifest['end'],
        'quality_issues': list(quality.issues),
        'point_in_time_verified': False,
        'independent_oos_approved': False,
        'orders_enabled': False,
        'model_invocation_verified': False,
        'generations_completed': 0,
    }
