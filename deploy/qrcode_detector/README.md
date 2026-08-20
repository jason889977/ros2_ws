# QR Code Detector Module Delivery

## 构建

```bash
docker build -f deploy/qrcode_detector/Dockerfile -t qrcode_detector_20260818_v1.0 .
```

## 运行

```bash
cp deploy/qrcode_detector/.env.example deploy/qrcode_detector/.env
docker compose --env-file deploy/qrcode_detector/.env \
  -f deploy/qrcode_detector/docker-compose.yml up -d
```

## 验收

```bash
docker exec qrcode_detector /opt/ros2_ws/deploy/qrcode_detector/smoke_test.sh
docker inspect --format '{{json .State.Health}}' qrcode_detector
```

## 前置条件

- 宿主机或上游模块已提供图像输入话题。
- 默认依赖 Basler 相机节点输出 `/my_camera/pylon_ros2_camera_node/image_raw`。
- 运行依赖 `python3-opencv` 与 `python3-numpy`。
- `IMAGE_TOPIC`、`MODEL_DIR`、`PREFER_WECHAT_QR` 会作为 `qrcode_detector.launch.py` 的默认参数传入；若图像源来自其他相机，可通过 `.env` 覆盖 `IMAGE_TOPIC`。
- WeChatQR 模型文件在 `share/qrcode_detector/models/` 中，若未提供则自动回退到 OpenCV 内置 QR 检测器。
