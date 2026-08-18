# udev 与硬件挂载

本模块使用 Basler GigE 相机，不使用 `/dev/ttyUSB*`、`/dev/video*` 或 USB 设备节点，因此不需要 udev 规则，也不应伪造设备挂载。

宿主机要求：

- 网卡与相机在同一局域网，例如宿主机 `172.31.0.200/24`。
- 目标相机：Serial `22297681`，User ID `106611-18`，IP `172.31.0.88`，MAC `00:30:53:23:0f:51`。
- Docker Compose 使用 `network_mode: host`，使容器能够访问 GigE 相机和 ROS 2 DDS。

如果后续改为 USB 相机，应新增明确的 Basler USB udev 规则和 `/dev/bus/usb` 挂载，不要复用本文件的空规则方案。
