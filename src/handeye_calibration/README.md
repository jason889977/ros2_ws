# handeye_calibration

Hand-eye calibration (eye-in-hand) via the Web Dashboard, plus an offline
solver CLI and a static TF broadcaster for the results.

## Components

| Entry | Purpose |
|-------|---------|
| Web Dashboard (`vision_dashboard/handeye_routes.py`) | Production entry point: four-step wizard for manual-pose capture, solving, and result application |
| `handeye_static_tf_broadcaster` | Publishes the calibrated gripper→camera transform (or manual parameters) as a static TF |
| `handeye_calibrate` (CLI) | Offline calibration from recorded pose CSV sets; writes OpenCV FileStorage YAML |

## Key services

- Service: `ReloadCalibration` (`apriltag_pose_reader_interfaces`) to
  re-publish transforms after recalibration.

## Testing

`pytest test/` — AX=XB math is verified against synthetic ground truth
(known X with noise-free samples).
