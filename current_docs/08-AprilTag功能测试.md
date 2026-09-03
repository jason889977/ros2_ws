# AprilTag 功能测试与验证

本文给出 AprilTag 从启动、图像输入、检测、TF 到位姿输出的逐步验证方法。除特别说明外，命令均在工作区根目录 `/home/ubuntu/ros2_ws` 执行，示例使用 `camera_id=my_camera`。

## 1. 验收范围与通过条件

数据链路如下：

```text
image_rect + camera_info
        -> apriltag_ros
        -> /my_camera/detections + /tf
        -> apriltag_pose_reader
        -> /my_camera/apriltag/pose
        -> /my_camera/apriltag/transform
```

完整功能通过必须同时满足：

1. 校正图像和相机内参持续发布；
2. AprilTag 检测器和位姿读取节点均已运行；
3. 标签入镜时能收到非空检测数组；
4. 相机 frame 到标签 frame 的 TF 可查询；
5. Pose 和 Transform 话题均能收到数值有限的位姿；
6. AprilTag 诊断为 `OK / Tracking tags`。

仅看到话题名称不代表功能正常，必须检查发布者数量并实际收到消息。

## 2. 测试准备

### 步骤 1：加载环境

**指令：**

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

**通过结果：** 命令无报错，并能找到主要包：

```bash
ros2 pkg prefix industrial_vision_bringup
ros2 pkg prefix apriltag_ros
ros2 pkg prefix vision_nodes
```

三个命令都应输出安装路径。

**说明：** 若提示 `Package not found`，先构建再重新加载环境：

```bash
colcon build --symlink-install --packages-up-to industrial_vision_bringup
source install/setup.bash
```

### 步骤 2：确认测试标签参数

本项目默认参数如下：

| 项目 | 默认值 |
| --- | --- |
| 标签族 | `tag36h11` |
| 标签 ID | `0` 至 `11` |
| 标签黑色外框边长 | `0.05 m` |
| 相机 frame | `basler_aca2500_106611_18` |
| 标签 frame 格式 | `my_camera/tag36h11:<ID>` |

真实标签必须属于 `tag36h11`，实际边长必须与 `apriltag_size` 一致。尺寸配置错误通常不会阻止检测，但会使平移距离按比例出错。

## 3. 真实相机测试

### 步骤 3：启动真实相机流水线

执行：

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch industrial_vision_bringup vision_pipeline.launch.py \
  camera_id:=my_camera \
  camera_config:="$PWD/deploy/basler_camera/config/aca2500_106611_18.yaml" \
  enable_apriltag:=true \
  enable_keyence:=false \
  apriltag_ids:=0 \
  apriltag_size:=0.05
```

**通过结果：** 相机组件容器、`/my_camera/apriltag` 和 `/my_camera/apriltag_pose_reader` 启动，无配置文件、相机占用或组件加载错误。

**说明：** 示例只检测 ID `0`，可减少不必要的 TF。测试其他标签时同步修改 `apriltag_ids`；`apriltag_size` 使用实测黑色标签外框边长，单位为米。

### 步骤 4：确认相机内参与校正图像

**指令：**

```bash
timeout 10 ros2 topic echo \
  /my_camera/pylon_ros2_camera_node/camera_info --once
ros2 topic info \
  /my_camera/pylon_ros2_camera_node/image_rect --verbose
timeout 10 ros2 topic hz \
  /my_camera/pylon_ros2_camera_node/image_rect
```

**通过结果：**

- `camera_info` 的宽高与当前图像一致；
- `k[0]` 和 `k[4]`（焦距）明显大于零，`k[2]`、`k[5]` 为合理主点；
- `image_rect` 有发布者，且能统计到稳定频率。

**说明：** 生产链路中的 AprilTag 订阅 `image_rect`。Basler 只有成功加载有效 `camera_info_url` 后才发布校正图像；只有 `image_raw` 而没有 `image_rect` 时，AprilTag 链路不会工作。

### 步骤 5：确认检测器连接完整

**指令：**

```bash
ros2 node list | grep -E '/my_camera/(apriltag|apriltag_pose_reader)'
ros2 topic info /my_camera/detections --verbose
```

**通过结果：**

- 两个节点均存在；
- `/my_camera/detections` 类型为 `apriltag_msgs/msg/AprilTagDetectionArray`；
- `Publisher count` 至少为 `1`，`Subscription count` 至少为 `1`。

**失败含义：** `Publisher count: 0` 表示只有位姿读取节点在订阅，检测器组件没有运行或未成功加载。此时话题虽然出现在列表中，功能仍未通过。

### 步骤 6：摆放标签并验证检测

将平整的 `tag36h11:0` 标签正对相机，先放在视野中央，避免过曝、反光、运动模糊和严重倾斜。标签至少应占图像数十个像素。

**指令：**

```bash
timeout 15 ros2 topic echo /my_camera/detections --once
```

**通过结果：** 15 秒内收到消息，`detections` 非空，其中存在：

```yaml
family: 36h11
id: 0
hamming: 0
```

**说明：** 收到 `detections: []` 仅证明检测节点在发布，尚未识别到标签。持续为空时依次检查标签族/ID、对焦、曝光、标签像素尺寸、打印边框和 `image_rect` 画面。

### 步骤 7：验证 TF

**指令：**

```bash
timeout 15 ros2 run tf2_ros tf2_echo \
  basler_aca2500_106611_18 my_camera/tag36h11:0
```

**通过结果：** 持续输出从相机 frame 到标签 frame 的 Translation 和 Rotation。

**说明：** Translation 单位为米。标签约在相机正前方时，深度方向应为正且量级符合实际距离；若距离按固定比例偏大或偏小，重点核对 `apriltag_size`。

### 步骤 8：验证 Transform 和 Pose

**指令：**

```bash
timeout 15 ros2 topic echo /my_camera/apriltag/transform --once
timeout 15 ros2 topic echo /my_camera/apriltag/pose --once
```

**通过结果：**

- Transform 的父 frame 为 `basler_aca2500_106611_18`；
- 子 frame 为 `my_camera/tag36h11:0`；
- Pose 的位置和姿态与 Transform 对应；
- 标签移动后平移数值随之变化，静止后数值基本稳定。

可用以下命令观察输出频率：

```bash
timeout 10 ros2 topic hz /my_camera/apriltag/transform
timeout 10 ros2 topic hz /my_camera/apriltag/pose
```

标签离开视野后无新位姿输出属于正常行为。

### 步骤 9：验证诊断状态

**指令：**

```bash
timeout 10 ros2 topic echo /my_camera/diagnostics --once | \
  grep -A 12 'AprilTag Status'
```

**通过结果：** 标签可见时应包含类似结果：

```text
message: Tracking tags
values:
- key: detections_seen
  value: '<大于 0>'
- key: transforms_published
  value: '<大于 0>'
- key: candidate_frames
  value: my_camera/tag36h11:0
```

诊断解释：

| 状态消息 | 含义 |
| --- | --- |
| `Tracking tags` | 已检测标签或最近发布了变换，功能正常 |
| `No recent tag transforms` | 以前发布过，但最近标签已离开视野或 TF 中断 |
| `No detections yet` | 启动后尚无检测，需检查输入和标签 |

## 4. 当前工作区实测记录

实测时间：`2026-09-02`。相机内参已通过 Web 四步向导完成标定并应用，当前已运行实例得到：

```text
/my_camera/pylon_ros2_camera_node              已加载，SN=22297681, Model=acA2500-14gc
/my_camera/pylon_ros2_camera_node/camera_info  持续发布，2590×1942，distortion_model=plumb_bob
/my_camera/pylon_ros2_camera_node/image_raw    持续发布，~7-10 FPS（Mono8，GigE 偶有 buffer underrun）
/my_camera/apriltag                            已加载（组件容器内）
/my_camera/apriltag_pose_reader                存在
/my_camera/detections                          类型正确，Publisher count=1
/my_camera/detections Subscription count       5（含容器内 intra-process 端点）
/my_camera/apriltag/transform Publisher        1
```

**内参验证：通过。** `camera_info` 的 `k[0]=3613.15`、`k[4]=3612.19` 为实际标定焦距（非占位值 1.0），畸变模型为 `plumb_bob`，5 个畸变系数均为有效数值。相机启动日志确认 `Camera is calibrated (at startup)`。

**AprilTag 检测链路：部分通过。** 检测器组件已成功加载并向 `/my_camera/detections` 发布（Publisher count=1，此前为 0），位姿读取节点正常订阅。诊断状态为 `No detections yet`，系现场无标签入镜所致，属正常待检测状态。待放置实体 `tag36h11:0` 标签后即可完成步骤 6 至步骤 9 的完整验收。

**已知环境限制（非功能缺陷）：**

- `event_logger` 因 `/var/log/vision` 目录权限不足而崩溃，Docker 环境下不会出现；
- `web_dashboard` 端口 8080 若被前次进程占用会报 `address already in use`，清理残留进程即可。

## 5. 快速故障定位表

| 现象 | 最可能原因 | 优先检查 |
| --- | --- | --- |
| `image_raw` 有数据，`image_rect` 不存在 | 内参文件无效或未加载 | `camera_info_url`、相机启动日志 |
| `detections` 话题存在但发布者为 0 | AprilTag 组件未加载 | 组件容器日志、`enable_apriltag` |
| 检测数组持续为空 | 标签或成像条件不匹配 | 标签族/ID、曝光、对焦、画面 |
| 检测非空但 TF 查不到 | frame 配置或 TF 发布异常 | `camera_frame`、标签 frame 名称、`/tf` |
| TF 正常但 Pose/Transform 无输出 | 位姿读取节点或参数异常 | 节点、诊断、`detections_topic` |
| 平移距离比例错误 | 标签边长配置错误 | `apriltag_size` 的单位和测量方式 |
| 位姿跳动明显 | 模糊、反光、标签像素过少或内参不准 | 曝光、固定方式、标定质量 |

## 6. 验收记录模板

```text
日期：
测试人员：
相机型号/序列号：
camera_id：
camera_frame：
标签族/ID/实测边长：
相机内参文件：

[ ] 节点启动正常
[ ] camera_info 有效
[ ] image_rect 稳定发布，频率：_____ Hz
[ ] detections 发布者/订阅者均存在
[ ] 标签检测 family、ID、hamming 正确
[ ] TF 可查询
[ ] Transform 可接收，频率：_____ Hz
[ ] Pose 可接收，频率：_____ Hz
[ ] 诊断为 Tracking tags
[ ] 移动标签后位姿变化方向与量级合理

最终结论：通过 / 不通过
异常与日志摘要：
```
