"""Utilities for the AprilGrid calibration board used by this project."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AprilGridSpec:
    """AprilTag calibration board specification.

    The board uses a 4x3 grid of tag36h11 tags, each tag is 50mm wide,
    and the gap between adjacent tag borders is 10mm. In the board plane,
    the center-to-center spacing is therefore 60mm.
    """

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
        return np.array(
            [
                [x, y, 0.0],
                [x + size, y, 0.0],
                [x + size, y + size, 0.0],
                [x, y + size, 0.0],
            ],
            dtype=np.float64,
        )

    def board_points_in_tag_frame(self) -> np.ndarray:
        """Return all board landmark points in the board coordinate frame."""
        points = []
        for tag_index in self.tag_ids:
            points.append(self.tag_corner_points(tag_index))
        return np.vstack(points)

    def board_origin_world(self) -> np.ndarray:
        """Return the board origin in the board plane: upper-left corner of the grid."""
        return np.array([0.0, 0.0, 0.0], dtype=np.float64)

    def tag_pose_in_board(self, tag_id: int) -> np.ndarray:
        """Return the tag center position in the board frame for a given tag id."""
        row = tag_id // self.cols
        col = tag_id % self.cols
        x = col * self.tag_center_spacing_m + self.tag_size_m / 2.0
        y = row * self.tag_center_spacing_m + self.tag_size_m / 2.0
        return np.array([x, y, 0.0], dtype=np.float64)

    @classmethod
    def from_yaml_dict(cls, config: dict) -> 'AprilGridSpec':
        rows = int(config.get('rows', 4))
        cols = int(config.get('cols', 3))
        tag_size_m = float(config.get('tag_size_m', 0.05))
        tag_spacing_m = float(config.get('tag_spacing_m', 0.01))
        tag_family = str(config.get('tag_family', 'tag36h11'))
        return cls(
            rows=rows,
            cols=cols,
            tag_size_m=tag_size_m,
            tag_spacing_m=tag_spacing_m,
            tag_family=tag_family,
        )
