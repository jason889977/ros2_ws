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
        """Return the 4 corner points of a tag in its local coordinate frame.

        The local tag frame is centered at the tag center and the axes are aligned
        with the board plane. The returned points are ordered clockwise starting at
        the top-left corner in the x-y plane.
        """
        half = self.tag_size_m / 2.0
        return np.array(
            [
                [-half, -half, 0.0],
                [half, -half, 0.0],
                [half, half, 0.0],
                [-half, half, 0.0],
            ],
            dtype=np.float64,
        )

    def board_points_in_tag_frame(self) -> np.ndarray:
        """Return all board landmark points in the board coordinate frame."""
        points = []
        for row in range(self.rows):
            for col in range(self.cols):
                tag_index = row * self.cols + col
                local = self.tag_corner_points(tag_index)
                cx = (col * self.tag_center_spacing_m) + (self.tag_size_m / 2.0)
                cy = (row * self.tag_center_spacing_m) + (self.tag_size_m / 2.0)
                tag_center = np.array([cx, cy, 0.0], dtype=np.float64)
                # The board frame origin is defined at the top-left tag corner in the
                # first tag, so translate each tag's local frame to the board plane.
                translated = local + np.array([
                    col * self.tag_center_spacing_m,
                    row * self.tag_center_spacing_m,
                    0.0,
                ], dtype=np.float64)
                points.append(translated)
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
