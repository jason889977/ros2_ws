# Basler 相机构建部署与故障处理 SOP

本文档总结本次 `basler_camera` 容器从 `restarting unhealthy` 到 `running healthy` 的完整处理经验，适用于 ROS 2 Humble、Docker Compose、Basler GigE 相机、AprilTag、二维码识别和 Keyence SR 联合视觉容器。

## 1. 适用范围

- 工作目录：`/home/ubuntu/ros2_ws`
- 容器服务：`basler_camera`
- 镜像标签：`basler_camera_20260819_v2.0`
- Compose 文件：`deploy/basler_camera/docker-compose.yml`
- 环境文件：`deploy/basler_camera/.env`
- 当前 Basler 相机：
  - Model: `acA2500-14gc`
  - Serial: `22297684`
  - User ID: `apriltagCam`
  - IP: `172.31.0.88`
  - MAC: `00:30:53:23:0f:54`

## 2. 最终有效状态

最终验证通过的状态：

```bash
sudo -n docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' basler_camera
# 期望：running healthy

sudo -n docker exec basler_camera sh -lc '. /opt/ros/humble/setup.sh && . /opt/ros2_ws/install/setup.sh && timeout 8s ros2 topic echo /my_camera/pylon_ros2_camera_node/camera_info --once >/tmp/camera_info.txt && echo camera_info_ok'
# 期望：camera_info_ok

sudo -n docker exec basler_camera sh -lc '. /opt/ros/humble/setup.sh && . /opt/ros2_ws/install/setup.sh && timeout 8s ros2 topic echo /my_camera/pylon_ros2_camera_node/image_raw --once >/tmp/image_raw.txt && echo image_raw_ok'
# 期望：image_raw_ok
```

日志中应能看到：

```text
Trying to connect the camera device with the following device user id: apriltagCam
Found camera device! Device Model: acA2500-14gc, Serial Number: 22297684, User Id: apriltagCam, IP: 172.31.0.88
Image publish FPS: 24.00
```

## 3. 一键高效构建与重建容器

在工作目录执行：

```bash
cd /home/ubuntu/ros2_ws

docker build -f deploy/basler_camera/Dockerfile -t basler_camera_20260819_v2.0 . \
  && sudo -n docker compose --env-file deploy/basler_camera/.env -f deploy/basler_camera/docker-compose.yml up -d --force-recreate \
  && sudo -n docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_camera
```

说明：

- 第一次构建仍需下载依赖；后续构建会复用 Docker layer cache 和 BuildKit apt cache。
- 如果只改配置或 Python 包，通常基础依赖层、pylon 安装层会缓存命中。
- 如果改了 C++ 包，`colcon build` 层会重新编译。

## 4. 国内源与依赖缓存策略

本次经验表明，官方 Ubuntu/ROS 源下载慢且不稳定；Dockerfile 已切换为国内源，并增加 apt 缓存。

默认源：

- Ubuntu: `http://mirrors.tuna.tsinghua.edu.cn/ubuntu`
- ROS 2: `http://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu`

Dockerfile 中通过 build args 支持覆盖：

```bash
docker build \
  --build-arg UBUNTU_APT_MIRROR=http://mirrors.aliyun.com/ubuntu \
  --build-arg ROS2_APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu \
  -f deploy/basler_camera/Dockerfile \
  -t basler_camera_20260819_v2.0 .
```

可选国内 Ubuntu 源：

```text
清华：http://mirrors.tuna.tsinghua.edu.cn/ubuntu
中科大：http://mirrors.ustc.edu.cn/ubuntu
阿里云：http://mirrors.aliyun.com/ubuntu
华为云：https://repo.huaweicloud.com/ubuntu
```

注意事项：

- ROS 2 国内镜像可能没有 `deb-src` 的 source 索引，所以 Dockerfile 已强制把 ROS 源 `Types` 改为 `deb`。
- Dockerfile 使用 BuildKit cache mount 缓存：
  - `/var/cache/apt`
  - `/var/lib/apt/lists`
- 不要随意执行 `docker builder prune -f`，它会清掉 BuildKit 构建缓存，下一次又要重新下载依赖。
- 如果磁盘不足必须清理，优先先看占用，再决定清理范围。

查看 Docker 空间占用：

```bash
docker system df
df -h / /var/lib/docker 2>/dev/null || df -h
```

谨慎清理：

```bash
# 只在空间明显不足时使用，会清理构建缓存
docker builder prune -f
```

## 5. pylon SDK 处理原则

当前仓库内实际 SDK 文件：

```text
deploy/basler_camera/pylon-sdk/pylon-8.0.0-linux-x86_64_debs.tar.gz
```

该压缩包内部包含 Debian 包：

```text
pylon_8.0.0.16021-deb0_amd64.deb
codemeter_7.40.4997.501_amd64.deb
```

本次关键修复：

- 不再假设 SDK 文件名是 `pylon-8.0.0-linux-x86_64_setup.tar.gz`。
- Dockerfile 支持 Debian bundle tar.gz。
- pylon SDK 通过 BuildKit bind mount 参与构建，不作为镜像层复制进去，避免导出镜像时把 527MB SDK 压缩包写入最终层。
- 安装 pylon 时排除文档、man、locale，降低镜像和临时层空间占用。

如果出现：

```text
No space left on device
```

优先检查是否把 SDK 压缩包 COPY 进了镜像层，正确方式应是：

```dockerfile
RUN --mount=type=bind,source=deploy/basler_camera/pylon-sdk,target=/tmp/pylon-sdk,readonly ...
```

不要在同一层里 `rm -rf /tmp/pylon-sdk`，因为它是只读 bind mount；只清理临时解包目录即可：

```bash
rm -rf /tmp/pylon-inner
```

## 6. 镜像基础源异常处理

如果 Docker Hub 拉取 `osrf/ros:humble-ros-base-jammy` 失败，可使用华为云镜像：

```bash
docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/ros:humble-ros-base
docker tag swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/ros:humble-ros-base osrf/ros:humble-ros-base-jammy

docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}' | grep -E 'osrf/ros|swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/ros'
```

## 7. 相机 ID 变更处理 SOP

如果日志出现：

```text
Couldn't find the camera that matches the specified camera identity
Failed to connect camera device with device user id: 旧ID
```

先枚举实际相机身份。本次使用 Pylon SDK 编译小工具，不依赖 NetworkManager：

```bash
sudo -n docker exec basler_camera sh -lc 'cat > /tmp/list_pylon_cameras.cpp <<"CPP"
#include <pylon/PylonIncludes.h>
#include <iostream>
int main() {
  Pylon::PylonInitialize();
  try {
    Pylon::CTlFactory& factory = Pylon::CTlFactory::GetInstance();
    Pylon::DeviceInfoList_t devices;
    size_t count = factory.EnumerateDevices(devices);
    std::cout << "count=" << count << std::endl;
    for (size_t i = 0; i < devices.size(); ++i) {
      const auto& d = devices[i];
      std::cout << "index=" << i
                << " model=" << d.GetModelName()
                << " serial=" << d.GetSerialNumber()
                << " user_id=" << d.GetUserDefinedName()
                << " ip=" << d.GetIpAddress()
                << " mac=" << d.GetMacAddress()
                << std::endl;
    }
  } catch (const GenICam::GenericException& e) {
    std::cerr << "exception=" << e.GetDescription() << std::endl;
    Pylon::PylonTerminate();
    return 2;
  }
  Pylon::PylonTerminate();
  return 0;
}
CPP
c++ /tmp/list_pylon_cameras.cpp -o /tmp/list_pylon_cameras $(/opt/pylon/bin/pylon-config --cflags --libs)
LD_LIBRARY_PATH=/opt/pylon/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} /tmp/list_pylon_cameras'
```

本次枚举结果：

```text
count=2
index=0 model=acA2500-14gc serial=22297684 user_id=apriltagCam ip=172.31.0.88 mac=003053230F54
index=1 model=acA2440-20gm serial=22784373 user_id=GigE_acA2440-20 ip=172.31.0.87 mac=0030532A7C75
```

然后同步修改以下文件：

```text
src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.yaml
deploy/basler_camera/config/aca2500_106611_18.yaml
src/pylon_ros2_camera_wrapper/config/aca2500_106611_18.calib.yaml
deploy/basler_camera/udev/README.md
```

应保证运行配置里一致：

```yaml
device_user_id: "apriltagCam"
serial_number: "22297684"
user_id: "apriltagCam"
mac: "00:30:53:23:0f:54"
ip: "172.31.0.88"
model: "acA2500-14gc"
```

标定文件里的 `camera_name` 也应同步为：

```yaml
camera_name: apriltagCam
```

检查旧 ID 是否残留：

```bash
grep -RIn "106611-18\|22297681\|00:30:53:23:0f:51" \
  deploy/basler_camera/config \
  deploy/basler_camera/udev \
  src/pylon_ros2_camera_wrapper/config | cat
```

命令无输出表示旧设备标识已清理。

## 8. 运行时健康检查

运行时容器状态、节点、话题和消息验证统一参阅 [故障排查手册](故障排查手册.md)。本 SOP 只保留 Basler SDK、镜像构建、网络、相机占用和容器构建问题。

## 9. 常见问题与处理

### 9.1 Package `industrial_vision_bringup` not found

表现：

```text
Package 'industrial_vision_bringup' not found
```

原因：运行的是旧镜像，镜像内只安装了部分 pylon 包，没有包含当前源码里的 `industrial_vision_bringup`。

处理：重新构建镜像并强制重建容器：

```bash
docker build -f deploy/basler_camera/Dockerfile -t basler_camera_20260819_v2.0 .
sudo -n docker compose --env-file deploy/basler_camera/.env -f deploy/basler_camera/docker-compose.yml up -d --force-recreate
```

### 9.2 pylon setup tar.gz 找不到

表现：

```text
pylon-8.0.0-linux-x86_64_setup.tar.gz: not found
```

原因：实际准备的是 Debian bundle：

```text
pylon-8.0.0-linux-x86_64_debs.tar.gz
```

处理：Dockerfile 应支持 `pylon-sdk/*.tar.gz` 并自动安装内部 `.deb`。

### 9.3 Docker 导出镜像时磁盘不足

表现：

```text
failed to extract layer ... /tmp/pylon-sdk/pylon-8.0.0-linux-x86_64_debs.tar.gz: no space left on device
```

原因：把 527MB pylon SDK 压缩包 COPY 成独立镜像层，最终导出还要写入本地 Docker 存储。

处理：使用 BuildKit bind mount，不把 SDK 压缩包写入镜像层。

### 9.4 pylon 文档导致空间不足

表现：

```text
cannot copy extracted data for ... /opt/pylon/share/pylon/doc/... No space left on device
```

处理：安装前写入 dpkg path-exclude，排除 pylon 文档、系统文档、man、locale。

### 9.5 ROS2 国内源 404 source/Sources

表现：

```text
Failed to fetch ... /ros2/ubuntu/dists/jammy/main/source/Sources 404 Not Found
```

原因：基础镜像的 `ros2.sources` 包含 `deb-src`，国内 ROS2 镜像可能不提供 source 索引。

处理：Dockerfile 中将 ROS 源 `Types` 改为仅 `deb`。

### 9.6 `PylonGigEConfigurator list` 失败

表现：

```text
Couldn't connect to NetworkManager
```

说明：该工具依赖 NetworkManager 服务，容器内通常没有，不适合作为相机枚举首选方式。

推荐：使用第 7 节 Pylon SDK 小程序枚举相机。

### 9.7 相机被其他程序占用

表现：

```text
The device is controlled by another application
```

处理：

```bash
sudo -n docker rm -f basler_camera
ps aux | grep -iE 'pylon|basler|camera' | grep -v grep
```

确认没有其他 pylon viewer、旧容器或本机 ROS 节点占用相机后，再重启容器。

## 10. 推荐日常操作顺序

1. 确认相机和扫码器网络可达：

```bash
ping -c 2 -W 1 172.31.0.88
ping -c 2 -W 1 172.31.0.91
```

2. 构建镜像：

```bash
docker build -f deploy/basler_camera/Dockerfile -t basler_camera_20260819_v2.0 .
```

3. 重建容器：

```bash
sudo -n docker compose --env-file deploy/basler_camera/.env -f deploy/basler_camera/docker-compose.yml up -d --force-recreate
```

4. 查健康状态：

```bash
sudo -n docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_cameraler_camera /opt/ros2_ws/deploy/basler_camera/healthcheck.sh

# 3. 检查 pylon SDK 是否正确安装
docker exec basler_camera ls /opt/pylon/lib/
```

5. 查日志：

```bash
sudo -n docker logs --tail 120 basler_camera
```

6. 验证图像：

```bash
sudo -n docker exec basler_camera sh -lc '. /opt/ros/humble/setup.sh && . /opt/ros2_ws/install/setup.sh && timeout 8s ros2 topic echo /my_camera/pylon_ros2_camera_node/image_raw --once >/tmp/image_raw.txt && echo image_raw_ok'
```

## 11. 本次关键经验

- `restarting unhealthy` 不要只看 healthcheck，要先看 `docker logs`；本次最初根因是旧镜像缺 `industrial_vision_bringup`。
- pylon SDK 文件名和实际格式必须以仓库内真实文件为准；不要硬编码不存在的 setup tar.gz。
- 大 SDK 文件不要 COPY 成镜像层，用 BuildKit bind mount 更稳。
- 国内 apt 源能显著缩短构建时间，但 ROS2 源要禁用 `deb-src`。
- apt cache mount 能提升后续构建速度，但 `docker builder prune` 会清掉这些缓存。
- 相机 User ID 可能被现场改掉，最稳妥的做法是用 Pylon SDK 枚举当前真实 `serial/user_id/ip/mac`，然后同步配置。
- `running starting` 不一定是故障；健康检查有启动窗口，应结合日志和话题消息判断。
- 最终判断标准不是只看容器启动，而是 `running healthy`、`camera_info_ok`、`image_raw_ok` 三项同时通过。