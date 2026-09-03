# vision_nodes

Python node collection for one camera pipeline (observability, aggregation,
and the ROS side of the web dashboard).

## Nodes

| Executable | Responsibility | Key diagnostics |
|------------|----------------|-----------------|
| `vision_status_aggregator` | Aggregates `/diagnostics` into `VisionStatus` on `<ns>/vision/status`; suffix-matches expected component names | — |
| `event_logger` | Persists scan/error events to rotating JSONL logs | — |
| `web_dashboard_node` | Bridges ROS topics (status, images, scans) to the FastAPI dashboard; JPEG-encodes frames on demand | `web_dashboard: Image Conversion` |
| `apriltag_pose_reader` | Publishes AprilTag poses/TF from detections + TF buffer | `apriltag_pose_reader: AprilTag Status` |

## Testing

`pytest test/` — includes aggregator suffix-matching regression tests and
the AprilTag diagnostic-level tests.
