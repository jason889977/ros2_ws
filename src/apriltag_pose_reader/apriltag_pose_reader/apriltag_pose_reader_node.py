"""Read AprilTag pose information from apriltag_ros TF output and republish it as standard pose messages."""

from __future__ import annotations

from typing import Optional, Set

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped, TransformStamped
from tf2_msgs.msg import TFMessage
from tf2_ros import TransformException
from tf2_ros import Buffer
from tf2_ros import TransformListener

try:
    from apriltag_msgs.msg import AprilTagDetectionArray
except Exception:  # pragma: no cover - optional at runtime if package is missing
    AprilTagDetectionArray = None


class AprilTagPoseReader(Node):
    def __init__(self) -> None:
        super().__init__('apriltag_pose_reader')

        self.declare_parameter('detections_topic', '/detections')
        self.declare_parameter('tf_topic', '/tf')
        self.declare_parameter('tag_frame_id', '')
        self.declare_parameter('tag_family', '')
        self.declare_parameter('tag_id', -1)
        self.declare_parameter('lookup_parent_frame', '')
        self.declare_parameter('lookup_rate_hz', 0.0)
        self.declare_parameter('health_log_interval_s', 10.0)
        self.declare_parameter('output_pose_topic', '~/pose')
        self.declare_parameter('output_transform_topic', '~/transform')
        self.declare_parameter('publish_detection_logs', True)
        self.declare_parameter('subscribe_detections', True)

        self._detections_topic = self.get_parameter('detections_topic').value
        self._tf_topic = self.get_parameter('tf_topic').value
        self._tag_frame_id = self.get_parameter('tag_frame_id').value
        self._tag_family = self._normalize_tag_family(self.get_parameter('tag_family').value)
        self._tag_id = int(self.get_parameter('tag_id').value)
        self._lookup_parent_frame = self.get_parameter('lookup_parent_frame').value
        self._lookup_rate_hz = float(self.get_parameter('lookup_rate_hz').value)
        self._health_log_interval_s = float(self.get_parameter('health_log_interval_s').value)
        self._publish_detection_logs = bool(self.get_parameter('publish_detection_logs').value)
        self._subscribe_detections = bool(self.get_parameter('subscribe_detections').value)

        self._pose_pub = self.create_publisher(PoseStamped, self.get_parameter('output_pose_topic').value, 10)
        self._transform_pub = self.create_publisher(TransformStamped, self.get_parameter('output_transform_topic').value, 10)

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self, spin_thread=True)

        self._known_tag_frames: Set[str] = set()
        self._latest_frame_hint: Optional[str] = None
        self._latest_parent_frame_hint: Optional[str] = None
        self._detections_seen = 0
        self._transforms_published = 0

        self._tf_sub = self.create_subscription(TFMessage, self._tf_topic, self._on_tf_message, 10)

        self._detections_sub = None
        if self._subscribe_detections and AprilTagDetectionArray is not None:
            self._detections_sub = self.create_subscription(
                AprilTagDetectionArray,
                self._detections_topic,
                self._on_detections,
                10,
            )
        elif self._subscribe_detections:
            self.get_logger().warn(
                'apriltag_msgs is not available in the current environment; ' \
                'detection-topic subscription is disabled and TF-only reading will be used.'
            )

        self.get_logger().info(
            'AprilTag pose reader started. '
            f'detections_topic={self._detections_topic}, tf_topic={self._tf_topic}, '
            f'tag_frame_id={self._tag_frame_id or "<auto>"}, '
            f'lookup_parent_frame={self._lookup_parent_frame or "<auto>"}, '
            f'lookup_rate_hz={self._lookup_rate_hz}'
        )

        if self._lookup_rate_hz > 0.0:
            self.create_timer(1.0 / self._lookup_rate_hz, self.lookup_and_publish_latest)

        if self._health_log_interval_s > 0.0:
            self.create_timer(self._health_log_interval_s, self._log_health)

    @staticmethod
    def _normalize_tag_family(family: str) -> str:
        family = str(family).strip()
        if not family:
            return ''
        if family.startswith('tag'):
            return family
        return f'tag{family}'

    def _frame_from_detection(self, detection) -> str:
        family = self._normalize_tag_family(getattr(detection, 'family', ''))
        detection_id = int(getattr(detection, 'id', -1))
        if family and detection_id >= 0:
            return f'{family}:{detection_id}'
        return ''

    def _candidate_frames(self) -> Set[str]:
        if self._tag_frame_id:
            return {self._tag_frame_id}
        if self._tag_family and self._tag_id >= 0:
            return {f'{self._tag_family}:{self._tag_id}'}
        if self._latest_frame_hint:
            return {self._latest_frame_hint}
        return set(self._known_tag_frames)

    def _publish_transform(self, transform: TransformStamped) -> None:
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

    def _on_detections(self, msg: AprilTagDetectionArray) -> None:
        self._detections_seen += len(msg.detections)
        for detection in msg.detections:
            frame_id = self._frame_from_detection(detection)
            if not frame_id:
                continue
            self._known_tag_frames.add(frame_id)
            self._latest_frame_hint = frame_id
            if self._publish_detection_logs:
                self.get_logger().info(
                    'AprilTag detection: '
                    f'frame={frame_id}, family={getattr(detection, "family", "")}, '
                    f'id={getattr(detection, "id", -1)}, '
                    f'hamming={getattr(detection, "hamming", -1)}, '
                    f'decision_margin={getattr(detection, "decision_margin", 0.0):.3f}'
                )

    def _on_tf_message(self, msg: TFMessage) -> None:
        candidate_frames = self._candidate_frames()
        if not candidate_frames:
            return

        for transform in msg.transforms:
            if transform.child_frame_id in candidate_frames:
                self._publish_transform(transform)

    def lookup_and_publish_latest(self) -> None:
        candidate_frames = self._candidate_frames()
        if not candidate_frames:
            self.get_logger().warn('No AprilTag frame is known yet; waiting for detections or a configured tag_frame_id.')
            return

        parent_frame = self._lookup_parent_frame or self._latest_parent_frame_hint
        if not parent_frame:
            self.get_logger().warn(
                'No parent frame available for TF lookup yet. '
                'Set lookup_parent_frame or wait for TF message hints.'
            )
            return

        for frame_id in candidate_frames:
            try:
                transform = self._tf_buffer.lookup_transform(parent_frame, frame_id, rclpy.time.Time())
            except TransformException:
                continue
            self._publish_transform(transform)
            return

        self.get_logger().warn(
            f'Could not resolve an AprilTag transform from TF buffer yet '
            f'for parent={parent_frame}. Waiting for the apriltag_ros /tf stream.'
        )

    def _log_health(self) -> None:
        frames = ','.join(sorted(self._candidate_frames())) or '<none>'
        self.get_logger().info(
            'AprilTag reader health: '
            f'detections_seen={self._detections_seen}, '
            f'transforms_published={self._transforms_published}, '
            f'candidate_frames={frames}'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AprilTagPoseReader()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
