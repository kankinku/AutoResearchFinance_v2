"""A public research brief lists usable inputs, never protected datasets."""
from pathlib import Path

from application.research_batch_service import ResearchBatchService
from core.data.contracts import DataZone, MarketDataSet
from core.data.parquet import ParquetDataProvider
from integrations.codex_mcp_core import create_mcp_server
from strategy_ir.normalizer import normalize_source
from tests.orchestration.test_evaluation_runner import _write_inputs


def _catalog_fixture(root: Path) -> None:
    source, data, _ = _write_inputs(root)
    strategies = root / "strategies" / "normalized"
    strategies.mkdir(parents=True)
    strategy = normalize_source(source).strategy
    assert strategy is not None
    (strategies / "example.json").write_text(
        strategy.model_dump_json(by_alias=True), encoding="utf-8"
    )
    (root / "data").mkdir()
    data.rename(root / "data" / data.name)


def test_research_brief_resolves_family_parameter_paths_and_qqq_data(tmp_path: Path) -> None:
    _catalog_fixture(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    discovered = service.describe_inputs()
    assert discovered["ready_for_batch"] is True
    source = discovered["sources"][0]
    assert source["strategy_id"] == "runner-test"
    assert source["family"] == "trend"
    assert "indicators.fast.period" in source["numeric_parameter_paths"]
    assert source["source_path"] == "strategies/normalized/example.json"

    details = discovered["datasets"][0]
    assert details["data_path"] == "data/bars.parquet"
    assert details["symbols"] == ["QQQ"]
    assert details["zone"] == "development"
    assert details["bars"] == 6
    assert details["quality_status"] == "UNVERIFIED"
    assert discovered["data_paths"] == ["data/bars.parquet"]

    brief = create_mcp_server(
        state_dir=tmp_path / "state", project_root=tmp_path
    )._dispatch("get_research_brief", {})
    assert brief["research_inputs"]["sources"][0]["family"] == "trend"
    assert brief["research_inputs"]["datasets"][0]["symbols"] == ["QQQ"]
    assert not (tmp_path / "state").exists()


def test_catalog_excludes_protected_corrupt_and_series_parquet(tmp_path: Path) -> None:
    _catalog_fixture(tmp_path)
    original = ParquetDataProvider.read(tmp_path / "data" / "bars.parquet")
    ParquetDataProvider.write(
        tmp_path / "data" / "private.parquet",
        MarketDataSet(original.version, DataZone.SEALED_OOS, original.bars),
    )
    (tmp_path / "data" / "bad.parquet").write_bytes(b"invalid")
    listed = ResearchBatchService(
        project_root=tmp_path, state_dir=tmp_path / "state"
    ).describe_inputs()
    assert listed["ready_for_batch"] is True
    assert listed["data_paths"] == ["data/bars.parquet"]
    assert len(listed["datasets"]) == 1
    assert "private.parquet" not in str(listed)
    assert "bad.parquet" not in str(listed)


def test_sealed_only_data_is_not_research_ready(tmp_path: Path) -> None:
    _catalog_fixture(tmp_path)
    original = ParquetDataProvider.read(tmp_path / "data" / "bars.parquet")
    ParquetDataProvider.write(
        tmp_path / "data" / "bars.parquet",
        MarketDataSet(original.version, DataZone.SEALED_OOS, original.bars),
    )
    listed = ResearchBatchService(
        project_root=tmp_path, state_dir=tmp_path / "state"
    ).describe_inputs()
    assert listed["sources"]
    assert listed["datasets"] == []
    assert listed["data_paths"] == []
    assert listed["ready_for_batch"] is False


def test_catalog_does_not_read_sealed_rows(tmp_path: Path, monkeypatch) -> None:
    _catalog_fixture(tmp_path)
    private = tmp_path / "data" / "private.parquet"
    original = ParquetDataProvider.read(tmp_path / "data" / "bars.parquet")
    ParquetDataProvider.write(
        private, MarketDataSet(original.version, DataZone.SEALED_OOS, original.bars)
    )
    read = ParquetDataProvider.read

    def safe_read(path: Path):
        assert Path(path).name != "private.parquet", "protected rows were accessed"
        return read(path)

    monkeypatch.setattr(ParquetDataProvider, "read", safe_read)
    report = ResearchBatchService(
        project_root=tmp_path, state_dir=tmp_path / "state"
    ).describe_inputs()
    assert report["data_paths"] == ["data/bars.parquet"]
