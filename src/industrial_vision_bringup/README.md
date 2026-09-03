# industrial_vision_bringup

Launch files, factory helpers, and defaults that assemble the full vision
pipeline for one or more cameras.

## Launch files

| File | Purpose |
|------|---------|
| `vision_pipeline.launch.py` | Real hardware pipeline (Pylon camera + AprilTag + Keyence + observability) |
| `apriltag_pose_reader.launch.py` | Standalone AprilTag reader + detector pair |

## Wiring conventions (see `bringup_utils.py` / `pipeline_nodes.py` / `composable_nodes.py`)

- Topics are namespaced per camera: `/<camera_id>/...`
  (e.g. `/<camera_id>/vision/status`, `/<camera_id>/diagnostics`).
- `expected_components` names are **prefixed** diagnostic names (e.g.
  `apriltag_pose_reader: AprilTag Status`); the aggregator also
  suffix-matches unprefixed entries.
- The AprilTag detector uses
  `image_rect`/`camera_info` remap keys.

## Configuration

`config/pipeline_defaults.yaml` — default parameters; deploy overlays in
`deploy/basler_camera/`.

## Testing

`pytest test/` — launch argument validation and topic wiring tests.
