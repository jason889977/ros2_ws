# AprilTag Pose Reader Module Delivery

## 构建

```bash
docker build -f deploy/apriltag_pose_reader/Dockerfile -t apriltag_pose_reader_20260818_v1.0 .
```

## 运行

```bash
cp deploy/apriltag_pose_reader/.env.example deploy/apriltag_pose_reader/.env
docker compose --env-file deploy/apriltag_pose_reader/.env \
  -f deploy/apriltag_pose_reader/docker-compose.yml up -d
```

## 验收

```bash
docker exec apriltag_pose_reader /opt/ros2_ws/deploy/apriltag_pose_reader/smoke_test.sh
docker inspect --format '{{json .State.Health}}' apriltag_pose_reader
```

## 前置条件

- 需要上游相机节点提供图像和 camera_info。
- 默认依赖 Basler 相机：`/my_camera/pylon_ros2_camera_node/image_raw` 与 `/my_camera/pylon_ros2_camera_node/camera_info`。
- Compose 会将 `IMAGE_TOPIC`、`CAMERA_INFO_TOPIC`、`START_DETECTOR`、`TAG_FAMILY`、`TAG_ID`、`LOOKUP_PARENT_FRAME`、`LOOKUP_RATE_HZ` 作为 `apriltag_pose_reader.launch.py` 的默认参数传入。
- 默认启动 `apriltag_ros` 检测节点，输出 `/detections` 与 `/tf`。
