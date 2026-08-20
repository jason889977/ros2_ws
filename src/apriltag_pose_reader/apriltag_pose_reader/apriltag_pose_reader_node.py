"""
AprilTag 姿态读取节点

功能概述：
    本节点从 apriltag_ros 的 TF（坐标变换）输出中读取 AprilTag 标签的位姿信息，
    并将其转换为标准的 PoseStamped 和 TransformStamped 消息重新发布。

数据流：
    apriltag_ros 检测节点 → /detections（检测到哪些标签）
                          → /tf（标签的坐标变换）
                                ↓
                        本节点订阅并转发
                                ↓
                        ~/pose      （PoseStamped，方便其他节点消费）
                        ~/transform （TransformStamped，保留原始变换信息）

使用场景：
    当你需要把 AprilTag 标签的 6D 位姿（位置 + 姿态）以标准 ROS 消息的形式
    提供给下游节点（如机械臂控制、导航等）时使用。
"""

# ============================================================================
# 导入部分
# ============================================================================

from __future__ import annotations
# 允许在类型注解中使用尚未定义的类（如用引号包裹的前向引用），Python 3.7+ 支持

from typing import Optional, Set

import time
# Optional[X] 等价于 X 或 None
# Set[X] 表示元素类型为 X 的集合

import rclpy
# rclpy 是 ROS 2 的 Python 客户端库，提供节点创建、消息发布/订阅等核心功能

from diagnostic_updater import DiagnosticStatusWrapper, Updater
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
# Node 是 ROS 2 节点的基类，所有自定义节点都需要继承它

from geometry_msgs.msg import PoseStamped, TransformStamped
# PoseStamped:       带时间戳和坐标系的位姿消息（位置 xyz + 四元数姿态 xyzw）
# TransformStamped:  带时间戳的坐标变换消息（父坐标系 → 子坐标系的平移 + 旋转）

from tf2_msgs.msg import TFMessage
# TFMessage: TF 系统的消息类型，包含一组 TransformStamped（通常就是 /tf 话题的消息类型）

from tf2_ros import TransformException
# 当 TF 查找失败时（如坐标系不存在、超时等）抛出的异常

from tf2_ros import Buffer
# TF Buffer: 缓存所有收到的坐标变换，支持按时间查询任意两个坐标系之间的变换

from tf2_ros import TransformListener
# TransformListener: 自动订阅 /tf 话题并将数据填充到 Buffer 中

try:
    from apriltag_msgs.msg import AprilTagDetectionArray
    # AprilTagDetectionArray: apriltag_ros 发布的检测结果消息，包含多个标签的检测信息
    # 每个检测包含：标签 ID、标签族、像素坐标、位姿估计等
except Exception:  # pragma: no cover - optional at runtime if package is missing
    # 如果 apriltag_msgs 包未安装（比如只想用 TF 模式），则优雅降级
    AprilTagDetectionArray = None


class AprilTagPoseReader(Node):
    """
    AprilTag 姿态读取节点类

    继承自 rclpy.node.Node，是 ROS 2 中的一个完整节点。
    节点在启动时会：
      1. 声明并读取参数（话题名、标签 ID 等）
      2. 创建发布器（输出位姿）和订阅器（接收检测结果和 TF）
      3. 根据参数决定是否启动定时主动查询 TF 的定时器
    """

    def __init__(self) -> None:
        # 调用父类初始化，节点名称为 'apriltag_pose_reader'
        # 节点名称在 ROS 2 中必须唯一，用于日志、参数命名空间等
        super().__init__('apriltag_pose_reader')

        # ------------------------------------------------------------------
        # 参数声明（declare_parameter）
        # ------------------------------------------------------------------
        # ROS 2 的参数机制：允许在 launch 文件或命令行中覆盖这些默认值
        # 语法: declare_parameter(参数名, 默认值)

        self.declare_parameter('detections_topic', '/detections')
        # AprilTag 检测结果话题名，apriltag_ros 在此发布检测到的标签列表

        self.declare_parameter('tf_topic', '/tf')
        # TF 坐标变换话题名，apriltag_ros 在此发布标签坐标系的变换

        self.declare_parameter('tag_frame_id', '')
        # 指定要跟踪的标签坐标系名称（如 "tag36h11:0"）
        # 留空表示自动从检测结果中推断

        self.declare_parameter('publish_all_tags', False)
        # 主动查询模式下是否发布所有当前仍有效的标签

        self.declare_parameter('tag_timeout_s', 1.0)
        # 自动发现的标签在多长时间没有检测后失效；显式 tag_frame_id 不受影响

        self.declare_parameter('tag_family', '')
        # 标签族名称（如 "tag36h11"），配合 tag_id 使用
        # 留空表示自动推断

        self.declare_parameter('tag_id', -1)
        # 要跟踪的标签 ID，-1 表示不指定（跟踪所有检测到的标签）

        self.declare_parameter('lookup_parent_frame', '')
        # TF 查询时的父坐标系（如 "camera_link"）
        # 留空则自动使用最近收到的 TF 消息中的父坐标系

        self.declare_parameter('lookup_rate_hz', 0.0)
        # 主动查询 TF 的频率（Hz），0 表示不启用主动查询
        # 启用后会按此频率定时从 TF Buffer 中查找并发布最新位姿

        self.declare_parameter('health_log_interval_s', 10.0)
        # 健康日志打印间隔（秒），定期输出节点运行状态统计
        # 设为 0 可禁用

        self.declare_parameter('output_pose_topic', '~/pose')
        # 输出的 PoseStamped 话题名
        # '~' 是私有命名空间，展开后为 /apriltag_pose_reader/pose

        self.declare_parameter('output_transform_topic', '~/transform')
        # 输出的 TransformStamped 话题名

        self.declare_parameter('publish_detection_logs', True)
        # 是否打印每次检测的详细日志（标签 ID、hamming 距离等）

        self.declare_parameter('subscribe_detections', True)
        # 是否订阅检测结果话题（设为 False 则仅依赖 TF 消息）

        # ------------------------------------------------------------------
        # 读取参数值到成员变量
        # ------------------------------------------------------------------
        # get_parameter() 返回 Parameter 对象，.value 取出实际值
        self._detections_topic = self.get_parameter('detections_topic').value
        self._tf_topic = self.get_parameter('tf_topic').value
        self._tag_frame_id = self.get_parameter('tag_frame_id').value
        # 对标签族做标准化处理（确保以 "tag" 开头）
        self._tag_family = self._normalize_tag_family(self.get_parameter('tag_family').value)
        self._tag_id = int(self.get_parameter('tag_id').value)
        self._lookup_parent_frame = self.get_parameter('lookup_parent_frame').value
        self._lookup_rate_hz = float(self.get_parameter('lookup_rate_hz').value)
        self._health_log_interval_s = float(self.get_parameter('health_log_interval_s').value)
        self._publish_detection_logs = bool(self.get_parameter('publish_detection_logs').value)
        self._subscribe_detections = bool(self.get_parameter('subscribe_detections').value)
        self._publish_all_tags = bool(self.get_parameter('publish_all_tags').value)
        self._tag_timeout_s = float(self.get_parameter('tag_timeout_s').value)

        # ------------------------------------------------------------------
        # 创建发布器（Publisher）
        # ------------------------------------------------------------------
        # create_publisher(消息类型, 话题名, 队列大小)
        # 队列大小 10 表示最多缓存 10 条未发送的消息
        self._pose_pub = self.create_publisher(PoseStamped, self.get_parameter('output_pose_topic').value, 10)
        self._transform_pub = self.create_publisher(TransformStamped, self.get_parameter('output_transform_topic').value, 10)

        # ------------------------------------------------------------------
        # TF2 系统初始化
        # ------------------------------------------------------------------
        # Buffer: 存储所有收到的坐标变换，形成一个变换树
        self._tf_buffer = Buffer()
        # TransformListener: 自动订阅 /tf 话题，将收到的变换存入 Buffer
        # spin_thread=False: TF 回调由 MultiThreadedExecutor 调度，避免双线程竞争共享状态
        self._tf_listener = TransformListener(self._tf_buffer, self, spin_thread=False)

        # ------------------------------------------------------------------
        # 内部状态变量
        # ------------------------------------------------------------------
        self._known_tag_frames: Set[str] = set()
        # 已知的标签坐标系名称集合，如 {"tag36h11:0", "tag36h11:1"}
        # 每当检测到新标签时更新

        self._tag_last_seen: dict[str, float] = {}
        self._candidate_cache: Optional[Set[str]] = None
        self._candidate_cache_dirty = True

        self._latest_frame_hint: Optional[str] = None
        # 最近一次检测到的标签坐标系名称，用于自动推断要跟踪的目标

        self._latest_parent_frame_hint: Optional[str] = None
        # 最近一次 TF 消息中的父坐标系（如 "camera_link"），用于 TF 查询

        self._detections_seen = 0
        # 累计收到的检测数量（用于健康日志统计）

        self._transforms_published = 0
        # 累计发布的变换数量（用于健康日志统计）

        # ------------------------------------------------------------------
        # 创建订阅器（Subscriber）
        # ------------------------------------------------------------------

        # 订阅 /tf 话题：监听坐标变换消息
        # 回调函数 _on_tf_message 会在收到 TF 消息时被调用
        self._tf_sub = self.create_subscription(TFMessage, self._tf_topic, self._on_tf_message, 10)

        # 订阅检测结果话题（可选）
        # 只有在 subscribe_detections=True 且 apriltag_msgs 可用时才创建
        self._detections_sub = None
        if self._subscribe_detections and AprilTagDetectionArray is not None:
            self._detections_sub = self.create_subscription(
                AprilTagDetectionArray,
                self._detections_topic,
                self._on_detections,  # 回调函数：处理检测结果
                10,
            )
        elif self._subscribe_detections:
            # apriltag_msgs 包未安装，降级为仅 TF 模式
            self.get_logger().warn(
                'apriltag_msgs is not available in the current environment; '
                'detection-topic subscription is disabled and TF-only reading will be used.'
            )

        # 启动日志：打印节点配置信息，便于调试
        self.get_logger().info(
            'AprilTag pose reader started. '
            f'detections_topic={self._detections_topic}, tf_topic={self._tf_topic}, '
            f'tag_frame_id={self._tag_frame_id or "<auto>"}, '
            f'lookup_parent_frame={self._lookup_parent_frame or "<auto>"}, '
            f'lookup_rate_hz={self._lookup_rate_hz}'
        )

        # ------------------------------------------------------------------
        # 定时器（Timer）
        # ------------------------------------------------------------------
        # 如果设置了主动查询频率，创建定时器按该频率调用 lookup_and_publish_latest
        if self._lookup_rate_hz > 0.0:
            self.create_timer(1.0 / self._lookup_rate_hz, self.lookup_and_publish_latest)
            # create_timer(间隔秒数, 回调函数)

        # 健康日志定时器：定期打印节点运行状态
        if self._health_log_interval_s > 0.0:
            self.create_timer(self._health_log_interval_s, self._log_health)

        # ---- Diagnostics ----
        self._diag_updater = Updater(self)
        self._diag_updater.setHardwareID('apriltag')
        self._diag_updater.addFunction('AprilTag Status', self._diag_status)

    # ======================================================================
    # 辅助方法
    # ======================================================================

    @staticmethod
    def _normalize_tag_family(family: str) -> str:
        """
        标准化标签族名称。

        AprilTag 的标签族名称格式为 "tag36h11"、"tag25h9" 等。
        但用户可能传入 "36h11" 这样不带 "tag" 前缀的简写。
        此方法确保返回值始终以 "tag" 开头。

        示例:
            "tag36h11" → "tag36h11"  （已有前缀，不变）
            "36h11"    → "tag36h11"  （自动补前缀）
            ""         → ""          （空值不变）
        """
        family = str(family).strip()
        if not family:
            return ''
        if family.startswith('tag'):
            return family
        return f'tag{family}'

    def _frame_from_detection(self, detection) -> str:
        """
        从单个检测结果中提取标签的 TF 坐标系名称。

        apriltag_ros 为每个检测到的标签创建一个 TF 坐标系，
        命名规则为 "{标签族}:{标签ID}"，如 "tag36h11:0"。

        参数:
            detection: AprilTagDetection 消息，包含 family、id 等字段

        返回:
            坐标系名称字符串（如 "tag36h11:0"），无法提取时返回空字符串
        """
        family = self._normalize_tag_family(getattr(detection, 'family', ''))
        detection_id = int(getattr(detection, 'id', -1))
        if family and detection_id >= 0:
            return f'{family}:{detection_id}'
        return ''

    def _candidate_frames(self) -> Set[str]:
        """
        确定当前要跟踪的标签坐标系集合。

        按优先级从高到低依次判断：
          1. 如果用户显式指定了 tag_frame_id → 直接用
          2. 如果用户指定了 tag_family + tag_id → 组合出坐标系名
          3. 如果最近有检测提示 → 用最近检测到的标签
          4. 否则 → 返回所有已知标签坐标系的集合

        返回:
            候选坐标系名称的集合
        """
        if self._tag_frame_id:
            return {self._tag_frame_id}
        if self._tag_family and self._tag_id >= 0:
            return {f'{self._tag_family}:{self._tag_id}'}
        if not self._candidate_cache_dirty and self._candidate_cache is not None:
            return self._candidate_cache
        if self._tag_timeout_s > 0.0:
            now = time.monotonic()
            self._known_tag_frames = {
                frame_id for frame_id in self._known_tag_frames
                if now - self._tag_last_seen.get(frame_id, 0.0) <= self._tag_timeout_s
            }
            # 同步清理 _tag_last_seen 字典，防止无限增长
            self._tag_last_seen = {
                frame_id: ts for frame_id, ts in self._tag_last_seen.items()
                if now - ts <= self._tag_timeout_s
            }
        if self._publish_all_tags:
            self._candidate_cache = set(self._known_tag_frames)
            self._candidate_cache_dirty = False
            return self._candidate_cache
        if self._latest_frame_hint in self._known_tag_frames:
            self._candidate_cache = {self._latest_frame_hint}
            self._candidate_cache_dirty = False
            return self._candidate_cache
        self._latest_frame_hint = None
        self._candidate_cache = set(self._known_tag_frames)
        self._candidate_cache_dirty = False
        return self._candidate_cache

    def _publish_transform(self, transform: TransformStamped) -> None:
        """
        将一个坐标变换同时以 TransformStamped 和 PoseStamped 两种格式发布。

        为什么要发两种？
          - TransformStamped: 保留完整的 TF 变换信息（含父子坐标系关系）
          - PoseStamped: 更通用，大多数下游节点（如 MoveIt、导航）直接消费

        转换方法：
          TransformStamped 中的 translation → PoseStamped 的 position
          TransformStamped 中的 rotation    → PoseStamped 的 orientation（四元数）

        参数:
            transform: 从 TF 系统获取的坐标变换消息
        """
        # 构造 PoseStamped 消息
        pose = PoseStamped()
        pose.header = transform.header          # 复制时间戳和父坐标系
        # 从变换中提取平移分量作为位置
        pose.pose.position.x = transform.transform.translation.x
        pose.pose.position.y = transform.transform.translation.y
        pose.pose.position.z = transform.transform.translation.z
        # 从变换中提取旋转分量作为姿态（四元数 xyzw）
        pose.pose.orientation = transform.transform.rotation

        # 发布两种消息
        self._transform_pub.publish(transform)
        self._pose_pub.publish(pose)
        # 记住父坐标系，供后续 TF 查询使用
        self._latest_parent_frame_hint = transform.header.frame_id
        self._transforms_published += 1

    # ======================================================================
    # 回调函数（Callback）
    # ======================================================================
    # 回调函数在收到订阅消息或定时器触发时由 ROS 2 自动调用

    def _on_detections(self, msg: AprilTagDetectionArray) -> None:
        """
        检测结果回调：处理 apriltag_ros 发布的标签检测消息。

        每当 apriltag_ros 检测到标签时，会发布 AprilTagDetectionArray 消息，
        其中包含所有在当前帧中检测到的标签信息。

        本回调的作用：
          1. 记录检测到的标签坐标系名称（用于后续 TF 过滤）
          2. 更新"最新标签提示"（用于自动推断要跟踪的目标）
          3. 可选：打印检测详情日志

        参数:
            msg: AprilTagDetectionArray 消息，包含 detections 列表
        """
        self._detections_seen += len(msg.detections)
        for detection in msg.detections:
            # 从检测结果中提取坐标系名称（如 "tag36h11:0"）
            frame_id = self._frame_from_detection(detection)
            if not frame_id:
                continue
            # 记录到已知集合中
            self._known_tag_frames.add(frame_id)
            self._tag_last_seen[frame_id] = time.monotonic()
            # 更新最新提示
            self._latest_frame_hint = frame_id
            self._candidate_cache_dirty = True
            if self._publish_detection_logs:
                # 打印检测详情：
                # - family:         标签族（如 tag36h11）
                # - id:             标签编号
                # - hamming:        汉明距离（纠错能力指标，越小越好）
                # - decision_margin: 决策边界（检测置信度，越大越可靠）
                self.get_logger().info(
                    'AprilTag detection: '
                    f'frame={frame_id}, family={getattr(detection, "family", "")}, '
                    f'id={getattr(detection, "id", -1)}, '
                    f'hamming={getattr(detection, "hamming", -1)}, '
                    f'decision_margin={getattr(detection, "decision_margin", 0.0):.3f}'
                )

    def _on_tf_message(self, msg: TFMessage) -> None:
        """
        TF 消息回调：处理 /tf 话题上的坐标变换消息。

        /tf 话题持续发布所有坐标系的变换（相机 → 各标签）。
        本回调从中过滤出目标标签的变换并立即发布。

        这是"被动模式"的核心：收到 TF 就转发，不需要定时器。

        参数:
            msg: TFMessage，包含多个 TransformStamped 的集合
        """
        candidate_frames = self._candidate_frames()
        if not candidate_frames:
            return

        # 遍历本条 TF 消息中的所有变换
        for transform in msg.transforms:
            # 只处理子坐标系在候选集合中的变换（即目标标签的变换）
            if transform.child_frame_id in candidate_frames:
                self._publish_transform(transform)

    def lookup_and_publish_latest(self) -> None:
        """
        主动查询 TF 并发布最新位姿（定时器回调）。

        当 lookup_rate_hz > 0 时启用。与被动模式（_on_tf_message）不同，
        这里主动从 TF Buffer 中查询最新的变换，而不是等 /tf 消息推送。

        适用场景：
          - 需要固定频率输出位姿（如控制器要求 30Hz）
          - /tf 消息频率不稳定时作为补充

        查询流程：
          1. 确定目标标签坐标系（candidate_frames）
          2. 确定参考坐标系（parent_frame）
          3. 从 TF Buffer 中查找两者之间的最新变换
          4. 找到则发布，找不到则打印警告
        """
        candidate_frames = self._candidate_frames()
        if not candidate_frames:
            self.get_logger().warn('No AprilTag frame is known yet; waiting for detections or a configured tag_frame_id.')
            return

        # 确定参考坐标系：优先用用户指定的，否则用最近 TF 消息中的父坐标系
        parent_frame = self._lookup_parent_frame or self._latest_parent_frame_hint
        if not parent_frame:
            self.get_logger().warn(
                'No parent frame available for TF lookup yet. '
                'Set lookup_parent_frame or wait for TF message hints.'
            )
            return

        # 尝试从 TF Buffer 中查找变换
        # rclpy.time.Time() 表示查询"最新"的变换（不指定时间点）
        for frame_id in candidate_frames:
            try:
                transform = self._tf_buffer.lookup_transform(parent_frame, frame_id, rclpy.time.Time())
            except TransformException:
                # 变换可能还没到达，跳过继续尝试下一个候选
                continue
            self._publish_transform(transform)
            if not self._publish_all_tags:
                return  # 单目标模式成功发布一个即可

        # 所有候选都查找失败
        self.get_logger().warn(
            f'Could not resolve an AprilTag transform from TF buffer yet '
            f'for parent={parent_frame}. Waiting for the apriltag_ros /tf stream.'
        )

    def _log_health(self) -> None:
        """
        健康日志回调：定期打印节点运行状态。

        输出信息：
          - detections_seen:      累计收到的检测次数
          - transforms_published: 累计发布的变换次数
          - candidate_frames:     当前跟踪的标签坐标系列表

        用于快速判断节点是否正常工作（如检测数是否增长）。
        """
        frames = ','.join(sorted(self._candidate_frames())) or '<none>'
        self.get_logger().info(
            'AprilTag reader health: '
            f'detections_seen={self._detections_seen}, '
            f'transforms_published={self._transforms_published}, '
            f'candidate_frames={frames}'
        )

    def _diag_status(self, stat: DiagnosticStatusWrapper) -> DiagnosticStatusWrapper:
        """Diagnostic task: report AprilTag detection and transform statistics."""
        if self._detections_seen > 0:
            stat.summary(0, 'Detecting tags')
        else:
            stat.summary(1, 'No detections yet')
        frames = ','.join(sorted(self._candidate_frames())) or '<none>'
        stat.add('detections_seen', str(self._detections_seen))
        stat.add('transforms_published', str(self._transforms_published))
        stat.add('candidate_frames', frames)
        return stat

    def destroy_node(self) -> None:
        """显式清理 TF listener 和订阅，防止后台线程泄漏。"""
        if hasattr(self, '_tf_listener'):
            del self._tf_listener
        if hasattr(self, '_tf_buffer'):
            del self._tf_buffer
        super().destroy_node()


# ============================================================================
# 节点入口函数
# ============================================================================

def main(args=None) -> None:
    rclpy.init(args=args)
    node = AprilTagPoseReader()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


# Python 标准入口点：当直接运行此文件时（而非被 import 时）执行 main()
if __name__ == '__main__':
    main()
