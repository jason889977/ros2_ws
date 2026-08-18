# Basler Camera ROS 2 接口

## 节点

默认节点为 `/my_camera/pylon_ros2_camera_node`，由 `camera_id` 修改命名空间。

## 发布 Topic

| 相对名称 | 完整默认名称 | 类型 |
| --- | --- | --- |
| `~/image_raw` | `/my_camera/pylon_ros2_camera_node/image_raw` | `sensor_msgs/msg/Image` |
| `~/camera_info` | `/my_camera/pylon_ros2_camera_node/camera_info` | `sensor_msgs/msg/CameraInfo` |
| `~/current_params` | `/my_camera/pylon_ros2_camera_node/current_params` | `pylon_ros2_camera_interfaces/msg/CurrentParams` |
| `~/status` | `/my_camera/pylon_ros2_camera_node/status` | `pylon_ros2_camera_interfaces/msg/ComponentStatus` |

Blaze 专用话题仅适用于 Blaze 设备，本模块目标设备 `acA2500-14gc` 不发布这些话题。

## 订阅 Topic

相机驱动没有业务输入 Topic。图像抓取由 ROS 2 发布者订阅状态触发。

## Service

驱动提供大量参数控制服务，核心服务包括：

- `~/set_exposure` -> `pylon_ros2_camera_interfaces/srv/SetExposure`
- `~/set_gain` -> `pylon_ros2_camera_interfaces/srv/SetGain`
- `~/set_gamma` -> `pylon_ros2_camera_interfaces/srv/SetGamma`
- `~/set_binning` -> `pylon_ros2_camera_interfaces/srv/SetBinning`
- `~/set_roi` -> `pylon_ros2_camera_interfaces/srv/SetROI`
- `~/set_brightness` -> `pylon_ros2_camera_interfaces/srv/SetBrightness`
- `~/set_white_balance` -> `pylon_ros2_camera_interfaces/srv/SetWhiteBalance`
- `~/get_max_num_buffer` -> `pylon_ros2_camera_interfaces/srv/GetIntegerValue`
- `~/get_statistic_failed_packet_count` -> `pylon_ros2_camera_interfaces/srv/GetIntegerValue`
- `~/get_statistic_missed_frame_count` -> `pylon_ros2_camera_interfaces/srv/GetIntegerValue`

完整服务集合以 `ros2 service list -t` 和 `src/pylon_ros2_camera_component/src/pylon_ros2_camera_node.cpp` 为准。模块不提供 Action。

## TF

相机驱动不主动发布 TF。图像消息使用配置中的 frame：`basler_aca2500_106611_18`。

AprilTag 可选链路由 `apriltag_pose_reader` 发布：

- `/apriltag/pose` -> `geometry_msgs/msg/PoseStamped`
- `/apriltag/transform` -> `geometry_msgs/msg/TransformStamped`
- 输入 `/tf` -> `tf2_msgs/msg/TFMessage`

实际父子坐标系取决于 AprilTag 和 TF 配置，应以 `/apriltag/transform` 的 `header.frame_id` 与 `child_frame_id` 为准。
