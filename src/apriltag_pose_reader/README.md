# apriltag_pose_reader

Publishes AprilTag poses and TF transforms from an upstream `apriltag_ros`
detector, independent of the detector's process boundaries.

## Node: `apriltag_pose_reader`

- **Inputs**: `detections_topic` (AprilTagDetectionArray) and `/tf`
  (passive TF path; a 10 Hz lookup timer is auto-enabled when needed).
- **Outputs**: `output_pose_topic`, `output_transform_topic`.
- **Key parameters**: `lookup_parent_frame`, `tag_frame_prefix`,
  `tag_timeout_s`, `publish_all_tags`, `subscribe_detections`.
- **Diagnostics**: `apriltag_pose_reader: AprilTag Status` — OK when tag
  transforms were published recently (works in TF-only mode), WARN when
  stale or never seen. Warnings are throttled (30 s).

## Testing

`pytest test/` — frame tracker logic, diagnostic level transitions, and
log throttling.
