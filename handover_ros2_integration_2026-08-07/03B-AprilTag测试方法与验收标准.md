# AprilTag 测试方法与验收标准

## 1. 测试目标

验证相机与 AprilTag 链路满足可发布运行条件:
- 检测结果可达
- 6D 位姿可达
- TF2 变换可达
- 短时稳定

## 2. 测试环境记录模板

- 日期:
- 执行人:
- 主机:
- 相机型号与 DeviceUserID:
- 配置文件:
- 标签信息（family/id）:
- 场景说明:

自动验收入口（推荐）:

```bash
cd /home/ubuntu/ros2_ws
./scripts/acceptance_camera_apriltag.sh --window 30 --enable-rviz true
```

说明:
- 脚本将执行 A-F 六项验收并输出 Markdown/JSON 报告。
- 报告默认路径: /home/ubuntu/ros2_ws/log/acceptance/
- `tag_family` 既可用 `36h11` 也可用 `tag36h11`，系统会自动规范化。

## 3. 测试项 A: ROS 图谱连通

命令:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 node list
ros2 topic info -v /my_camera/pylon_ros2_camera_node/image_raw
```

通过判据:
- 存在节点 /my_camera/pylon_ros2_camera_node
- 存在节点 /apriltag
- 存在节点 /apriltag_pose_reader
- image_raw: Publisher count >= 1

不通过判据:
- 相机或 AprilTag 节点缺失

## 4. 测试项 B: 检测结果可达

命令:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 topic echo /detections --once
```

通过判据:
- 在标签进入视野后，detections 返回有效结果
- 可观察到 family/id/hamming/decision_margin 字段

不通过判据:
- 长时间无输出，或 topic 未发布

## 5. 测试项 C: 6D 位姿可达

命令:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 topic echo /apriltag/pose --once
ros2 topic echo /apriltag/transform --once
```

通过判据:
- /apriltag/pose 返回 PoseStamped
- /apriltag/transform 返回 TransformStamped
- transform 中 child_frame_id 非空

不通过判据:
- 任一话题长时间无输出

## 6. 测试项 D: TF2 变换连通

步骤:
1. 从 /apriltag/transform --once 输出中读取 header.frame_id 和 child_frame_id。
2. 使用以下命令验证连续变换:

```bash
ros2 run tf2_ros tf2_echo <header.frame_id> <child_frame_id>
```

通过判据:
- tf2_echo 可持续输出平移与旋转

不通过判据:
- 报错 frame 不存在或无持续输出

## 7. 测试项 E: RViz2 可视化

命令:

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
rviz2
```

建议配置:
- Fixed Frame 设为 map，或 /apriltag/transform 里的父坐标系
- Add -> TF
- Add -> Pose，Topic 选择 /apriltag/pose

通过判据:
- 可见标签对应 TF 与 Pose 变化

不通过判据:
- 仅有图像无位姿，或 TF 不更新

## 8. 测试项 F: 关键错误码守门

命令:

```bash
latest=$(ls -1t /home/ubuntu/.ros/log/pylon_ros2_camera_wrapper_*.log | head -n 1)
grep -E "3774873620|incompletely grabbed|Grab was not successful" -i "$latest" || true
```

通过判据:
- 无重复爆发式关键错误

不通过判据:
- 出现持续或重复关键错误，需触发回滚或网络排障

## 9. 最小验收结论模板

- 图谱连通: 通过/不通过
- 检测可达: 通过/不通过
- 6D 位姿可达: 通过/不通过
- TF2 连通: 通过/不通过
- RViz2 可视化: 通过/不通过
- 错误码守门: 通过/不通过
- 综合结论: 可交付/需整改
- 备注:
