from __future__ import annotations

from orchestration.plateau import PlateauDetector


def test_plateau_detector_requires_patience_and_min_delta() -> None:
    detector = PlateauDetector(patience=2, min_delta=0.01)

    assert detector.observe(0.50) is False
    assert detector.observe(0.505) is False
    assert detector.observe(0.506) is True
    assert detector.observe(0.53) is False
