# AprilTag Pose Reader ROS 2 Interface

## 节点

- `/apriltag`
- `/apriltag_pose_reader`

## 发布 Topic

| 相对名称 | 完整默认名称 | 类型 |
| --- | --- | --- |
| `/apriltag/pose` | `/apriltag/pose` | `geometry_msgs/msg/PoseStamped` |
| `/apriltag/transform` | `/apriltag/transform` | `geometry_msgs/msg/TransformStamped` |

## 订阅 Topic

| 相对名称 | 完整默认名称 | 类型 |
| --- | --- | --- |
| `/detections` | `/detections` | `apriltag_msgs/msg/AprilTagDetectionArray` |
| `/tf` | `/tf` | `tf2_msgs/msg/TFMessage` |
| 图像输入 | `/my_camera/pylon_ros2_camera_node/image_raw` | `sensor_msgs/msg/Image` |
| 相机内参 | `/my_camera/pylon_ros2_camera_node/camera_info` | `sensor_msgs/msg/CameraInfo` |

## Services

- 该链路不提供业务 Service 入口
- 主要依赖图像流、检测结果和 TF 变换进行位姿解析

## Actions

- 无 Action 定义

## TF

- 主要依赖 `apriltag_ros` 生成的 `/tf` 变换
- 出口数据会以两种形式发布：
  - `/apriltag/pose`：`geometry_msgs/PoseStamped`
  - `/apriltag/transform`：`geometry_msgs/TransformStamped`

典型坐标关系：

- `camera_frame -> tag36h11:<id>`
- 通过 `/apriltag/transform` 可得到父子坐标系关系

实际父子 frame 由 TF 中的 `header.frame_id` 和 `child_frame_id` 确定。
