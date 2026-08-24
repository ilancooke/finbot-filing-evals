from pathlib import Path

import pytest

from finbot_filing_evals.golden_dataset.config import GoldenDatasetConfig


def test_config_derives_documented_layout(tmp_path: Path) -> None:
    config = GoldenDatasetConfig.from_data_root(tmp_path)

    assert config.data_root == tmp_path.resolve()
    assert config.source_root == (
        tmp_path / "raw" / "financial_statement_screenshots_golden_dataset"
    )
    assert config.annotations_root == (
        tmp_path / "intermediate" / "golden_dataset_annotations"
    )
    assert config.consensus_root == (
        tmp_path / "intermediate" / "golden_dataset_consensus"
    )
    assert config.processed_root == (
        tmp_path / "processed" / "financial_statement_visual_gold"
    )
    assert not config.intermediate_root.exists()


def test_config_supports_environment_overrides(tmp_path: Path) -> None:
    source = tmp_path / "custom-source"
    config = GoldenDatasetConfig.from_env(
        {
            "FINBOT_DATA_ROOT": str(tmp_path / "data"),
            "FINBOT_GOLDEN_DATASET_SOURCE_ROOT": str(source),
        }
    )

    assert config.source_root == source.resolve()
    assert config.intermediate_root == (tmp_path / "data" / "intermediate").resolve()


def test_config_requires_data_root() -> None:
    with pytest.raises(ValueError, match="FINBOT_DATA_ROOT is required"):
        GoldenDatasetConfig.from_env({})

