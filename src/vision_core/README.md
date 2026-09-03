# vision_core

Shared Python utilities for the industrial vision pipeline. No ROS nodes
live here — only library code reused by `vision_nodes`, `vision_dashboard`,
and the calibration packages.

## Modules

| Module | Purpose |
|--------|---------|
| `rotation` helpers (`rotation_from_rpy`, `rotation_matrix_to_quaternion`) | SE(3) math shared by calibration and TF publishers |
| `run_node` | Standard node bootstrap (init → spin → clean shutdown) |
| `diagnostics.DiagnosticsSubscriber` | Namespaced `/diagnostics` subscription with freshness tracking |
| `event_logging` | Append-only JSONL event log with size-based rotation |

## Conventions

- All consumers import via `from vision_core import ...`.
- Diagnostic name matching is suffix-based (`': <name>'`) to tolerate node
  name prefixes added by `diagnostic_updater`.
