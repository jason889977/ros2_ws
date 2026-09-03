# pylon_ros2_camera_interfaces

Message and service definitions shared across the vision pipeline.

## Messages

| Message | Used by |
|---------|--------|
| `VisionStatus` | `vision_status_aggregator` → dashboard/event logger (overall level, per-component names/messages, scan metrics) |
| `ComponentStatus` | per-component diagnostic snapshot |
| `CurrentParams` | current camera parameters snapshot |

## Conventions

`VisionStatus.overall_level` uses `OK=0 / WARN=1 / ERROR=2 / STALE=3`;
`component_names`/`component_messages` are parallel arrays (there is no
per-component level field — the dashboard reads levels from
`/diagnostics` instead).
