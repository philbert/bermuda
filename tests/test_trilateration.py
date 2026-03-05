"""Tests for trilateration helper module."""

from __future__ import annotations

import math

from custom_components.bermuda.trilateration import (
    AnchorMeasurement,
    anchor_centroid,
    residual_rms_m,
    solve_2d_soft_l1,
)


def test_anchor_centroid():
    """Centroid should be the arithmetic mean of anchor coordinates."""
    anchors = [
        AnchorMeasurement("a", 0.0, 0.0, 1.0),
        AnchorMeasurement("b", 2.0, 0.0, 1.0),
        AnchorMeasurement("c", 0.0, 2.0, 1.0),
    ]
    assert anchor_centroid(anchors) == (2 / 3, 2 / 3)


def test_solve_2d_soft_l1_returns_expected_point():
    """Solver should recover a stable point from consistent anchors."""
    anchors = [
        AnchorMeasurement("a", 0.0, 0.0, 5.0),
        AnchorMeasurement("b", 10.0, 0.0, math.hypot(6.0, 4.0)),
        AnchorMeasurement("c", 0.0, 10.0, math.hypot(4.0, 6.0)),
    ]
    result = solve_2d_soft_l1(anchors, initial_guess=(4.5, 4.5))
    assert result.ok
    assert result.x_m is not None
    assert result.y_m is not None
    assert result.residual_rms_m is not None
    assert abs(result.x_m - 4.0) < 0.2
    assert abs(result.y_m - 3.0) < 0.2
    assert result.residual_rms_m < 0.35


def test_solve_2d_soft_l1_rejects_two_anchor_case():
    """Two anchors are insufficient and must be rejected."""
    anchors = [
        AnchorMeasurement("a", 0.0, 0.0, 3.0),
        AnchorMeasurement("b", 4.0, 0.0, 3.0),
    ]
    result = solve_2d_soft_l1(anchors)
    assert not result.ok
    assert result.reason == "insufficient_anchors"


def test_residual_rms_m():
    """Residual RMS should be near zero for an exact point."""
    anchors = [
        AnchorMeasurement("a", 0.0, 0.0, 5.0),
        AnchorMeasurement("b", 10.0, 0.0, 5.0),
        AnchorMeasurement("c", 5.0, 8.660254, 3.660254),
    ]
    rms = residual_rms_m(5.0, 0.0, anchors)
    assert rms < 1e-3
