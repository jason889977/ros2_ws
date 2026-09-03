"""AprilGrid board specification used by calibration workflows."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AprilGridSpec:
    """AprilTag board geometry: 4x3 tag36h11 tags with 10mm gaps."""

    rows: int = 4
    cols: int = 3
    tag_size_m: float = 0.05
    tag_spacing_m: float = 0.01
    tag_family: str = 'tag36h11'

    @property
    def num_tags(self) -> int:
        return self.rows * self.cols

    @property
    def tag_center_spacing_m(self) -> float:
        return self.tag_size_m + self.tag_spacing_m

    @property
    def tag_ids(self) -> list[int]:
        return list(range(self.num_tags))

    def tag_corner_points(self, tag_id: int) -> np.ndarray:
        """Return tag corners in board coordinates, from top-left clockwise."""
        if tag_id not in self.tag_ids:
            raise ValueError(f'tag_id must be in [0, {self.num_tags - 1}]')
        row = tag_id // self.cols
        col = tag_id % self.cols
        x = col * self.tag_center_spacing_m
        y = row * self.tag_center_spacing_m
        size = self.tag_size_m
        return np.array([
            [x, y, 0.0],
            [x + size, y, 0.0],
            [x + size, y + size, 0.0],
            [x, y + size, 0.0],
        ], dtype=np.float64)

    def tag_corner_points_apriltag_order(self, tag_id: int) -> np.ndarray:
        """Return corners in the detector's lb-rb-rt-lt order."""
        return self.tag_corner_points(tag_id)[[3, 2, 1, 0]]
