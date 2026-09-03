"""AprilTag pose reader node.

Reads AprilTag pose information from apriltag_ros TF output and republishes
it as standard PoseStamped and TransformStamped messages.

Data flow:
    apriltag_ros detector → /detections (which tags detected)
                          → /tf (tag coordinate transforms)
                                ↓
                    This node subscribes and republishes
                                ↓
                        ~/pose      (PoseStamped for downstream consumers)
                        ~/transform (TransformStamped, preserves raw transform)

Use when you need to provide AprilTag 6D poses (position + orientation) as
standard ROS messages to downstream nodes (e.g., robot control, navigation).
"""

from __future__ import annotations

import threading
import time

import rclpy

from diagnostic_updater import DiagnosticStatusWrapper, Updater
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped, TransformStamped
from vision_core import TagFrameTracker, run_node
from diagnostic_msgs.msg import DiagnosticStatus

from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer, TransformException, TransformListener

try:
    from apriltag_msgs.msg import AprilTagDetectionArray
except (ImportError, OSError):  # pragma: no cover - optional at runtime if package is missing
    AprilTagDetectionArray = None


class AprilTagPoseReader(Node):
    """AprilTag pose reader node.

    On startup the node:
      1. Declares and reads parameters (topic names, tag IDs, etc.)
      2. Creates publishers (output poses) and subscribers (detections and TF)
      3. Optionally starts a timer to actively query TF based on parameters
    """

    def __init__(self, parameter_overrides=None) -> None:
        super().__init__(
            'apriltag_pose_reader', parameter_overrides=parameter_overrides or [],
        )
        self._declare_parameters()
        self._read_parameters()
        self._setup_communication()
        self._setup_timers()

    def _declare_parameters(self) -> None:
        self.declare_parameter('detections_topic', '/detections')
        self.declare_parameter('tf_topic', '/tf')
        self.declare_parameter('tag_frame_id', '')
        self.declare_parameter('publish_all_tags', False)
        self.declare_parameter('tag_timeout_s', 1.0)
        self.declare_parameter('tag_family', '')
        self.declare_parameter('tag_id', -1)
        self.declare_parameter('lookup_parent_frame', '')
        self.declare_parameter('tag_frame_prefix', '')
        self.declare_parameter('lookup_rate_hz', 0.0)
        self.declare_parameter('health_log_interval_s', 10.0)
        self.declare_parameter('output_pose_topic', '~/pose')
        self.declare_parameter('output_transform_topic', '~/transform')
        self.declare_parameter('publish_detection_logs', True)
        self.declare_parameter('subscribe_detections', True)

    def _read_parameters(self) -> None:
        self._detections_topic = self.get_parameter('detections_topic').value
        self._tf_topic = self.get_parameter('tf_topic').value
        self._tag_frame_id = self.get_parameter('tag_frame_id').value
        self._tag_family = TagFrameTracker.normalize_family(self.get_parameter('tag_family').value)
        self._tag_id = int(self.get_parameter('tag_id').value)
        self._lookup_parent_frame = self.get_parameter('lookup_parent_frame').value
        self._tag_frame_prefix = str(self.get_parameter('tag_frame_prefix').value).strip('/')
        self._lookup_rate_hz = float(self.get_parameter('lookup_rate_hz').value)
        self._health_log_interval_s = float(self.get_parameter('health_log_interval_s').value)
        self._publish_detection_logs = bool(self.get_parameter('publish_detection_logs').value)
        self._subscribe_detections = bool(self.get_parameter('subscribe_detections').value)
        self._publish_all_tags = bool(self.get_parameter('publish_all_tags').value)
        self._tag_timeout_s = float(self.get_parameter('tag_timeout_s').value)

    def _setup_communication(self) -> None:
        self._pose_pub = self.create_publisher(
            PoseStamped, self.get_parameter('output_pose_topic').value, 10)
        self._transform_pub = self.create_publisher(
            TransformStamped, self.get_parameter('output_transform_topic').value, 10)

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self, spin_thread=False)

        self._lock = threading.RLock()
        self._tracker = TagFrameTracker(
            tag_frame_id=self._tag_frame_id,
            tag_family=self._tag_family,
            tag_id=self._tag_id,
            tag_frame_prefix=self._tag_frame_prefix,
            publish_all_tags=self._publish_all_tags,
            tag_timeout_s=self._tag_timeout_s,
        )
        self._latest_parent_frame_hint: str | None = None
        self._detections_seen = 0
        self._transforms_published = 0
        self._tf_messages_received = 0
        self._metrics_started_at = time.monotonic()
        self._last_tf_processing_ms = 0.0
        self._last_transform_mono = None
        self._last_no_tag_warn_mono = 0.0

        self._tf_sub = None
        if self._tf_topic != '/tf':
            self._tf_sub = self.create_subscription(
                TFMessage, self._tf_topic, self._on_tf_message, 10)

        self._detections_sub = None
        if self._subscribe_detections and AprilTagDetectionArray is not None:
            self._detections_sub = self.create_subscription(
                AprilTagDetectionArray,
                self._detections_topic,
                self._on_detections,
                10,
            )
        elif self._subscribe_detections:
            self.get_logger().warning(
                'apriltag_msgs is not available in the current environment; '
                'detection-topic subscription is disabled '
                'and TF-only reading will be used.')

        self.get_logger().info(
            'AprilTag pose reader started. '
            f'detections_topic={self._detections_topic}, tf_topic={self._tf_topic}, '
            f'tag_frame_id={self._tag_frame_id or "<auto>"}, '
            f'lookup_parent_frame={self._lookup_parent_frame or "<auto>"}, '
            f'lookup_rate_hz={self._lookup_rate_hz}'
        )

    def _setup_timers(self) -> None:
        if self._tf_topic == '/tf' and self._lookup_rate_hz <= 0.0:
            self._lookup_rate_hz = 10.0
            self.get_logger().info(
                'tf_topic is /tf (passive path disabled); '
                'auto-enabling lookup timer at 10.0 Hz to ensure pose publishing.'
            )
        if self._lookup_rate_hz > 0.0:
            self.create_timer(1.0 / self._lookup_rate_hz, self.lookup_and_publish_latest)

        if self._health_log_interval_s > 0.0:
            self.create_timer(self._health_log_interval_s, self._log_health)

        self._diag_updater = Updater(self)
        self._diag_updater.setHardwareID('apriltag')
        self._diag_updater.add('AprilTag Status', self._diag_status)

    # -- helpers -----------------------------------------------------------

    def _publish_transform(self, transform: TransformStamped) -> None:
        """Publish a transform as both TransformStamped and PoseStamped.

        TransformStamped retains full TF info (parent/child frame relationships).
        PoseStamped is more widely consumed by downstream nodes (e.g., MoveIt, navigation).

        Translation → PoseStamped position
        Rotation → PoseStamped orientation (quaternion)
        """
        pose = PoseStamped()
        pose.header = transform.header
        pose.pose.position.x = transform.transform.translation.x
        pose.pose.position.y = transform.transform.translation.y
        pose.pose.position.z = transform.transform.translation.z
        pose.pose.orientation = transform.transform.rotation

        self._transform_pub.publish(transform)
        self._pose_pub.publish(pose)
        self._latest_parent_frame_hint = transform.header.frame_id
        self._transforms_published += 1
        self._last_transform_mono = time.monotonic()

    # -- callbacks ---------------------------------------------------------

    def _on_detections(self, msg: AprilTagDetectionArray) -> None:
        """Process AprilTag detection messages from apriltag_ros.

        Records detected tag frame names for subsequent TF filtering,
        updates the latest-tag hint for auto inference, and optionally
        logs detection details.
        """
        with self._lock:
            self._detections_seen += len(msg.detections)
            for detection in msg.detections:
                frame_id = self._tracker.frame_from_detection(detection)
                if not frame_id:
                    continue
                self._tracker.remember(frame_id)
                if self._publish_detection_logs:
                    self.get_logger().debug(
                        'AprilTag detection: '
                        f'frame={frame_id}, family={getattr(detection, "family", "")}, '
                        f'id={getattr(detection, "id", -1)}, '
                        f'hamming={getattr(detection, "hamming", -1)}, '
                        f'decision_margin={getattr(detection, "decision_margin", 0.0):.3f}'
                    )

    def _on_tf_message(self, msg: TFMessage) -> None:
        """Process TF messages from the /tf topic (passive mode).

        Filters incoming transforms for target tags and publishes them
        immediately without needing a timer. This is the core of passive
        mode: receive TF → publish pose.
        """
        with self._lock:
            started_at = time.monotonic()
            self._tf_messages_received += 1
            transforms = msg.transforms
            if self._lookup_parent_frame:
                transforms = [
                    transform for transform in transforms
                    if transform.header.frame_id == self._lookup_parent_frame
                ]
            if not self._tag_frame_id:
                for transform in transforms:
                    if self._tracker.is_auto_tag_frame(transform.child_frame_id):
                        self._tracker.remember(transform.child_frame_id)

            for transform in transforms:
                self._tf_buffer.set_transform(transform, 'apriltag_pose_reader')

            self._tracker.expire_stale()
            candidate_frames = self._tracker.candidate_frames()
            if not candidate_frames:
                return

            for transform in transforms:
                if transform.child_frame_id in candidate_frames:
                    self._publish_transform(transform)
            elapsed = max(0.0, time.monotonic() - started_at)
            self._last_tf_processing_ms = elapsed * 1000.0

    def _warn_throttled(self, message: str, interval_s: float = 30.0) -> None:
        """Log a warning at most once per *interval_s* to avoid 10 Hz spam."""
        now = time.monotonic()
        if now - self._last_no_tag_warn_mono >= interval_s:
            self._last_no_tag_warn_mono = now
            self.get_logger().warning(message)

    def lookup_and_publish_latest(self) -> None:
        """Actively query TF and publish the latest pose (timer callback).

        Enabled when lookup_rate_hz > 0. Unlike passive mode (via
        _on_tf_message), this actively queries the TF Buffer at a fixed
        rate instead of waiting for /tf message pushes.

        Use when:
          - A fixed-rate pose output is needed (e.g., controller at 30 Hz)
          - /tf message frequency is unstable

        Query flow:
          1. Determine target tag frames (candidate_frames)
          2. Determine reference frame (parent_frame)
          3. Look up the latest transform from TF Buffer
          4. Publish if found, log warning if not
        """
        with self._lock:
            self._tracker.expire_stale()
            candidate_frames = self._tracker.candidate_frames()
            parent_frame = self._lookup_parent_frame or self._latest_parent_frame_hint

        if not candidate_frames:
            self._warn_throttled(
                'No AprilTag frame is known yet; '
                'waiting for detections or a configured tag_frame_id.')
            return

        if not parent_frame:
            self._warn_throttled(
                'No parent frame available for TF lookup yet. '
                'Set lookup_parent_frame or wait for TF message hints.')
            return

        any_published = False
        for frame_id in candidate_frames:
            try:
                transform = self._tf_buffer.lookup_transform(
                    parent_frame, frame_id, rclpy.time.Time())
            except TransformException:
                continue
            with self._lock:
                self._publish_transform(transform)
            any_published = True
            if not self._publish_all_tags:
                return

        if not any_published:
            self._warn_throttled(
                f'Could not resolve an AprilTag transform from TF buffer yet '
                f'for parent={parent_frame}. Waiting for the apriltag_ros /tf stream.')

    def _log_health(self) -> None:
        """Periodic health log: print node running status.

        Outputs cumulative detections, published transforms, and
        currently tracked tag frames. Useful for quick diagnosis
        of whether the node is working correctly.
        """
        with self._lock:
            self._tracker.expire_stale()
            frames = ','.join(sorted(self._tracker.candidate_frames())) or '<none>'
            detections = self._detections_seen
            published = self._transforms_published
        self.get_logger().info(
            'AprilTag reader health: '
            f'detections_seen={detections}, '
            f'transforms_published={published}, '
            f'candidate_frames={frames}'
        )

    def _diag_status(self, stat: DiagnosticStatusWrapper) -> DiagnosticStatusWrapper:
        """Diagnostic task: report AprilTag detection and transform statistics."""
        with self._lock:
            detections = self._detections_seen
            published = self._transforms_published
            tf_msgs = self._tf_messages_received
            last_ms = self._last_tf_processing_ms
            started = self._metrics_started_at
            last_transform = self._last_transform_mono
            self._tracker.expire_stale()
            frames = ','.join(sorted(self._tracker.candidate_frames())) or '<none>'
        # Judge health from actual output, not just the optional detections
        # subscription: TF-only mode (apriltag_msgs missing or
        # subscribe_detections=false) never increments _detections_seen.
        recent_transform = (
            last_transform is not None
            and time.monotonic() - last_transform <= 2.0 * self._tag_timeout_s
        )
        if recent_transform or detections > 0:
            stat.summary(DiagnosticStatus.OK, 'Tracking tags')
        elif published > 0:
            stat.summary(DiagnosticStatus.WARN, 'No recent tag transforms')
        else:
            stat.summary(DiagnosticStatus.WARN, 'No detections yet')
        stat.add('detections_seen', str(detections))
        stat.add('transforms_published', str(published))
        stat.add('tf_messages_received', str(tf_msgs))
        stat.add('last_tf_processing_ms', f'{last_ms:.3f}')
        elapsed = max(0.0, time.monotonic() - started)
        stat.add('tf_message_rate_hz', f'{tf_msgs / elapsed:.3f}' if elapsed > 0.0 else '0.000')
        stat.add('candidate_frames', frames)
        return stat

    def destroy_node(self) -> None:
        """Clean up TF listener and subscriptions to prevent thread leaks."""
        if self._tf_sub is not None:
            self.destroy_subscription(self._tf_sub)
        if self._detections_sub is not None:
            self.destroy_subscription(self._detections_sub)
        del self._tf_listener
        del self._tf_buffer
        super().destroy_node()


# -- entry point --------------------------------------------------------

def main(args=None) -> None:
    run_node(AprilTagPoseReader, args=args)


if __name__ == '__main__':
    main()
