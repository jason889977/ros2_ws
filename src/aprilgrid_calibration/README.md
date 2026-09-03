# aprilgrid_calibration

Camera intrinsics calibration from AprilGrid targets.

## Components

- `calibrator.py` — AprilGrid detection (via `python3-apriltag`),
  subpixel refinement, and intrinsics solving; validates finite values and
  `image_size=(height, width)` ordering before solving.
- ROS service wrapper for interactive capture sessions.

## Conventions

- The grid config (rows/cols, tag size, spacing) is passed as parameters;
  detection results are cached per capture session.
- Output follows OpenCV `calibrateCamera` conventions (K, D, RMS).

## Testing

`pytest test/` — synthetic reprojection checks and parameter validation.
