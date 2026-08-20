# 工控机 ROS2 集成与调用超详细指南（小白版）

适用对象：
- 需要把本项目集成到工控机，并与机器人等其他 ROS2 包同时运行的同事。
- 对 ROS2、Docker 不熟悉，按步骤执行即可。

适用版本：
- 日期基线：2026-08-20
- 工作区：`/home/ubuntu/ros2_ws`
- ROS2：Humble

---

## 1. 你们最终要达到的目标

在同一台工控机上：
- 运行机器人相关 ROS2 包（运动控制、规划、任务调度等）。
- 同时运行本视觉项目（Basler 相机 + QR + AprilTag + Keyence）。
- 让机器人程序通过 ROS2 话题/服务，直接拿到视觉结果并触发扫码。

最核心原则只有 3 条：
1. 所有需要互通的程序，`ROS_DOMAIN_ID` 必须一致。
2. 所有程序尽量使用同一种 DDS（本项目默认 `rmw_fastrtps_cpp`）。
3. 统一话题命名，不要随意改名称；如果改了，要同步改调用方。

---

## 2. 本项目当前“标准运行模式”

### 2.1 推荐模式（现场默认）

只启动一个容器：`basler_camera`，它会在容器里统一拉起以下节点：
- Basler 相机：`/my_camera/pylon_ros2_camera_node`
- AprilTag 检测：`/apriltag`
- AprilTag 位姿读取：`/apriltag_pose_reader`
- 二维码识别：`/wechat_qr_node`
- Keyence 扫码：`/keyence_sr_node`

对应统一入口 launch：
- `industrial_vision_bringup/vision_pipeline.launch.py`

优点：
- 新手最不容易配错。
- 一条命令重启全链路，问题定位简单。

### 2.2 可选模式（模块分开）

也可以单独启动 4 个容器：
- `deploy/basler_camera`
- `deploy/qrcode_detector`
- `deploy/apriltag_pose_reader`
- `deploy/keyence_sr_wrapper`

仅在你们确实需要“独立扩缩容/独立发布版本”时使用。

---

## 3. 对外接口总表（给机器人程序同事看）

### 3.1 视觉结果输出（你们最常用）

1) 二维码文本：
- Topic：`/wechat_qr_node/decoded_info`
- 类型：`std_msgs/msg/String`
- 语义：二维码内容字符串

2) AprilTag 位姿：
- Topic：`/apriltag/pose`
- 类型：`geometry_msgs/msg/PoseStamped`
- 语义：目标 Tag 在某坐标系下的位置姿态（常用于引导机器人）

3) AprilTag 变换：
- Topic：`/apriltag/transform`
- 类型：`geometry_msgs/msg/TransformStamped`
- 语义：父子坐标系之间变换，可直接接 TF 逻辑

4) 原始图像：
- Topic：`/my_camera/pylon_ros2_camera_node/image_raw`
- 类型：`sensor_msgs/msg/Image`

5) 相机内参：
- Topic：`/my_camera/pylon_ros2_camera_node/camera_info`
- 类型：`sensor_msgs/msg/CameraInfo`

### 3.2 设备触发输入（机器人可调用）

1) Keyence 触发扫码服务：
- Service：`/scanner/trigger`
- 类型：`std_srvs/srv/Trigger`
- 作用：机器人动作到位后主动触发一次扫码

2) Keyence 扫码结果输出：
- Topic：`/scanner/barcode`
- 类型：`std_msgs/msg/String`

### 3.3 触发模式说明（非常重要，避免误用）

1) QR 二维码链路：持续读取模式
- 节点持续订阅图像话题，来一帧处理一帧。
- 默认不是“调用一次就拍一张”的服务模式。
- 结果持续发布到 `/wechat_qr_node/decoded_info`（相同结果会做短时间去重抑制）。

2) AprilTag 链路：持续读取模式
- `apriltag_ros` 持续处理图像并输出 `/detections`、`/tf`。
- `apriltag_pose_reader` 持续消费这些数据并发布 `/apriltag/pose`、`/apriltag/transform`。
- 默认不是单次触发拍照模式。

3) Keyence 扫码链路：单次触发模式
- 通过调用 `/scanner/trigger` 触发一次扫码。
- 然后从 `/scanner/barcode` 读取本次结果。
- 这是本项目里典型的“请求-应答/触发”链路。

---

## 4. 部署前统一约定（避免 80% 集成问题）

在你们团队内先固定：
1. `ROS_DOMAIN_ID`：例如统一为 `0`（或现场定义值）。
2. `RMW_IMPLEMENTATION`：统一 `rmw_fastrtps_cpp`。
3. 统一网段：
- Basler 相机网段必须与工控机网卡互通。
- Keyence IP/端口必须可达（默认 `172.31.0.91:9004`）。
4. 容器命名固定：`basler_camera`（避免运维脚本失效）。
5. 统一从本指南给出的命令执行，不要混用旧脚本。

---

## 5. 工控机首次部署（一步一步做）

## 5.1 准备目录

```bash
cd /home/ubuntu/ros2_ws
```

## 5.2 准备环境文件

```bash
cp deploy/basler_camera/.env.example deploy/basler_camera/.env
```

## 5.3 编辑 `.env`（按现场改）

至少确认以下参数：
- `ROS_DOMAIN_ID=0`（改成你们统一值）
- `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`
- `CAMERA_ID=my_camera`（建议保持默认）
- `SCANNER_IP=172.31.0.91`（按现场）
- `SCANNER_PORT=9004`

## 5.4 启动统一容器

```bash
docker compose --env-file deploy/basler_camera/.env \
  -f deploy/basler_camera/docker-compose.yml up -d
```

## 5.5 检查状态

```bash
docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_camera
```

期望输出：
- `running healthy`

如果是 `starting`，等待 20~40 秒再看一次。

---

## 6. 日常启动/停止（交给值班同事）

### 6.1 启动（或重启）

```bash
sudo -n docker restart basler_camera
sudo -n docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_camera
```

### 6.2 停止

```bash
sudo -n docker stop basler_camera
```

### 6.3 查看日志

```bash
docker logs -f --tail=200 basler_camera
```

---

## 7. 5 分钟联调检查单（机器人同事必做）

执行环境（宿主机）：

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
```

### 7.1 看节点是否都在

```bash
ros2 node list | grep -E 'pylon_ros2_camera_node|wechat_qr_node|apriltag_pose_reader|keyence_sr_node|apriltag'
```

### 7.2 看关键话题是否存在

```bash
ros2 topic list | grep -E '/wechat_qr_node/decoded_info|/apriltag/pose|/apriltag/transform|/scanner/barcode|image_raw|camera_info'
```

### 7.3 验证二维码输出

```bash
ros2 topic echo /wechat_qr_node/decoded_info --once
```

### 7.4 验证 AprilTag 输出

```bash
ros2 topic echo /apriltag/pose --once
```

### 7.5 验证 Keyence 触发调用

```bash
ros2 service call /scanner/trigger std_srvs/srv/Trigger {}
```

并在另一个终端看：

```bash
ros2 topic echo /scanner/barcode
```

---

## 8. 机器人程序如何“调用”本项目（最重要）

下面给你们 3 种最常见对接方式。

## 8.1 方式 A：机器人只订阅视觉结果（最简单）

场景：
- 机器人只需要二维码字符串或 AprilTag 位姿，不需要改视觉程序。

机器人侧做法：
1. 订阅 `/wechat_qr_node/decoded_info` 拿字符串。
2. 订阅 `/apriltag/pose` 拿位姿。
3. 收到数据后做动作规划。

优点：耦合低、上线快。

## 8.2 方式 B：机器人主动触发扫码

场景：
- 机器人到位后才扫码，避免误识别。
- 说明：这里是 Keyence 的单次触发逻辑，不是 QR/AprilTag 的处理方式。

机器人侧做法：
1. 先调用 `/scanner/trigger`。
2. 等待 `/scanner/barcode` 返回一条结果。
3. 结果超时则重试或报警。

建议超时：
- 1~3 秒无结果，判定本次失败并重试。

## 8.3 方式 C：基于 TF/位姿抓取

场景：
- 机器人根据 AprilTag 估计位姿进行抓取。

机器人侧做法：
1. 订阅 `/apriltag/transform` 或 `/apriltag/pose`。
2. 把姿态转换到机器人基坐标系（若需要）。
3. 做安全过滤（位姿跳变、超出工作空间直接丢弃）。

建议：
- 对位姿加简单滤波（中值/滑窗）再用于运动控制。

---

## 9. 代码示例（可直接抄给同事）

## 9.1 Python：订阅二维码结果

```python
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class QrListener(Node):
    def __init__(self):
        super().__init__('qr_listener')
        self.sub = self.create_subscription(
            String,
            '/wechat_qr_node/decoded_info',
            self.cb,
            10,
        )

    def cb(self, msg: String):
        self.get_logger().info(f'QR = {msg.data}')


def main():
    rclpy.init()
    node = QrListener()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

## 9.2 Python：调用 Keyence 触发服务

```python
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

class ScannerTrigger(Node):
    def __init__(self):
        super().__init__('scanner_trigger_client')
        self.cli = self.create_client(Trigger, '/scanner/trigger')

    def run(self):
        if not self.cli.wait_for_service(timeout_sec=3.0):
            self.get_logger().error('service /scanner/trigger not available')
            return
        req = Trigger.Request()
        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if future.result() is None:
            self.get_logger().error('trigger call failed or timed out')
            return
        res = future.result()
        self.get_logger().info(f'success={res.success}, message={res.message}')


def main():
    rclpy.init()
    node = ScannerTrigger()
    node.run()
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

## 9.3 C++：订阅 AprilTag 位姿

```cpp
#include <memory>
#include "rclcpp/rclcpp.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"

class TagPoseListener : public rclcpp::Node {
public:
  TagPoseListener() : Node("tag_pose_listener") {
    sub_ = this->create_subscription<geometry_msgs::msg::PoseStamped>(
      "/apriltag/pose", 10,
      [this](const geometry_msgs::msg::PoseStamped::SharedPtr msg) {
        RCLCPP_INFO(this->get_logger(),
                    "Tag Pose: frame=%s, x=%.3f y=%.3f z=%.3f",
                    msg->header.frame_id.c_str(),
                    msg->pose.position.x,
                    msg->pose.position.y,
                    msg->pose.position.z);
      });
  }

private:
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr sub_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<TagPoseListener>());
  rclcpp::shutdown();
  return 0;
}
```

---

## 10. 多 ROS2 包共存时的集成建议（非常关键）

1. 统一环境变量（宿主机 + 容器）：
- `ROS_DOMAIN_ID` 一致
- `RMW_IMPLEMENTATION` 一致

2. 机器人包不要重复发布同名话题：
- 特别是 `/tf`、`/camera_info`、`/image_raw`。

3. 尽量不要修改本项目默认话题：
- 如果必须改，记录变更并同步所有调用方。

4. 先“看见数据”，再“做业务逻辑”：
- 先通过 `ros2 topic echo` 验证有数据，再写状态机。

5. 把视觉与机器人做成松耦合：
- 用 topic/service 协议对接，不要互相直接 import 代码。

---

## 11. 常见故障与处理（新手高频）

## 11.1 容器不 healthy

排查顺序：
1. `docker logs --tail=200 basler_camera`
2. 检查网线、相机供电、扫码器供电
3. 检查 `ROS_DOMAIN_ID` 是否改错
4. 执行容器内健康检查：

```bash
docker exec basler_camera /opt/ros2_ws/deploy/basler_camera/healthcheck.sh
```

## 11.2 看不到 `/wechat_qr_node/decoded_info`

1. 先确认有图像输入：

```bash
ros2 topic hz /my_camera/pylon_ros2_camera_node/image_raw
```

2. 确认二维码节点是否在：

```bash
ros2 node list | grep wechat_qr_node
```

3. 现场二维码是否清晰、尺寸是否太小。

## 11.3 看不到 `/apriltag/pose`

1. 检查标签 family 与 ID 是否匹配（当前验证：`36h11`, `id=3`）。
2. 先看 `/detections` 是否有数据。
3. 再看 `/tf` 是否有对应 tag 变换。

## 11.4 调用 `/scanner/trigger` 失败

1. 检查扫码器 IP/端口是否能 ping/连通。
2. 检查 `SCANNER_IP`、`SCANNER_PORT`。
3. 看 `/keyence_sr_node` 日志是否反复重连。

---

## 12. 交接给同事时，建议直接发这 5 条命令

```bash
cd /home/ubuntu/ros2_ws
cp deploy/basler_camera/.env.example deploy/basler_camera/.env
docker compose --env-file deploy/basler_camera/.env -f deploy/basler_camera/docker-compose.yml up -d
docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' basler_camera
ros2 topic list | grep -E '/wechat_qr_node/decoded_info|/apriltag/pose|/scanner/barcode'
```

如果第 4 条是 `running healthy` 且第 5 条能看到三个关键话题，基本就表示集成成功。

---

## 13. 与机器人包对接的推荐流程（团队协作）

1. 视觉同事先独立启动并验收（本指南第 7 章）。
2. 机器人同事只写“订阅/调用”最小逻辑。
3. 联调时固定只测一个流程：
- 例如“触发扫码 -> 收条码 -> 执行抓取”。
4. 跑通后再加异常分支（超时、空码、位姿丢失）。
5. 最后再做参数调优。

---

## 14. 版本与变更管理建议（防止越改越乱）

1. 任何话题名改动必须写到变更记录。
2. 每次发布前固定做一遍 5 分钟联调检查单。
3. 镜像 tag 用日期+版本号，不要覆盖旧 tag。
4. 生产环境只允许使用已验证过的 `.env`。

---

## 15. 你们可以直接复用的“接口契约”

建议在机器人项目里定义统一约定：
- 输入：
  - `/apriltag/pose`
  - `/wechat_qr_node/decoded_info`
  - `/scanner/barcode`
- 输出调用：
  - `/scanner/trigger`

这样后续即使视觉算法升级，只要接口不变，机器人侧代码基本不用改。

---

## 16. 相关文档入口

- 项目总说明：`README.md`
- 日常启动说明：`项目启动运行指南/项目启动运行说明.md`
- 交接总览：`handover_ros2_integration_2026-08-07/00-交接总览.md`
- 公共 SOP：`handover_ros2_integration_2026-08-07/02-启动与运行SOP.md`
- Basler 接口：`deploy/basler_camera/ROS2-INTERFACE.md`
- QR 接口：`deploy/qrcode_detector/ROS2-INTERFACE.md`
- AprilTag 接口：`deploy/apriltag_pose_reader/ROS2-INTERFACE.md`
- Keyence 接口：`deploy/keyence_sr_wrapper/ROS2-INTERFACE.md`

---

## 17. 背景信息与参考资料：持续读取持续反馈是否为业界通行做法

是，整体上可以说是通行做法，尤其在机器人和机器视觉里非常常见，但会按场景做变体。

为什么常用持续读取持续反馈：
1. 实时性更好：目标进入视野就能马上输出结果，不用先发一次触发命令再等拍照处理。
2. 系统更简单：上游持续发流，下游持续订阅，模块解耦更好。
3. 更稳健：即使某几帧丢失，后续帧还能继续补上结果。
4. 更利于融合：定位、抓取、避障等通常都需要连续更新而不是一次性值。

但业界通常会加“节流和门控”，不是无脑全量处理：
1. 去重：相同识别结果短时间不重复上报。
2. 降频：比如只发布 10Hz 的有效结果，而不是相机 60FPS 全发。
3. 置信度过滤：低置信结果不发布。
4. 业务触发门控：机器人到位后才“采信”持续流中的结果。

所以最佳实践通常是：
1. 感知层持续运行（QR、AprilTag 持续读取）。
2. 执行层按任务节拍使用结果（到位、窗口期、超时重试）。
3. 对某些设备保留触发式（如扫码枪服务触发）作为补充。

一句话总结：持续读取持续反馈是主流常规做法，触发式更多用于特定设备或特定工艺步骤。

---

如果你们希望，我还可以在下一版给你们补两份模板：
1. 机器人端“状态机示例节点”（触发扫码 + 等待二维码 + 超时重试）。
2. 一份“联调值班检查表”（可打印，按勾执行）。

## 18.0 “机器人 + 机器视觉”里最通用、最实用、跨项目基本都适用的 ROS2 部署知识清单
一、先定架构，不要先写功能

把系统拆成三层：感知层、决策层、执行层。
感知层只负责“稳定出结果”，不要耦合业务状态机。
决策层负责时序和策略，比如到位触发、超时重试、降级策略。
执行层只关心“动作安全与可达”，不要直接依赖相机细节。
各层只通过话题、服务、动作通信，避免跨包直接调用内部函数。

二、话题和接口设计要先“签合同”

每个接口都明确四件事：字段含义、坐标系、时间语义、有效期。
先冻结接口名，再迭代算法。接口频繁改名会让联调成本爆炸。
输出结果要带置信度或质量指标，方便下游过滤。
触发式与流式要写清楚，不要混在一个接口语义里。
发布“接口契约文档”比口头约定靠谱得多。

三、QoS 是 ROS2 成败关键，不是高级可选项

视觉图像常用 best effort，降低丢包重传带来的延迟。
控制与关键状态常用 reliable，保证消息不丢。
历史深度要按消费能力配，不是越大越好。
发布订阅双方 QoS 要匹配，否则会出现“看得见节点、收不到消息”。
现场先统一一套默认 QoS 策略，后续按链路微调。

四、时间同步与时钟策略必须统一

机器人和视觉需要统一时钟来源，否则时序判断会错。
跨设备部署时优先做 NTP 或 PTP，同步误差要可测。
录包、回放、仿真时要明确是否启用仿真时钟。
下游逻辑不要只看“是否收到”，要看消息时间戳是否新鲜。
过期数据要丢弃，避免机器人执行旧感知结果。

五、坐标系管理是视觉上机第一大坑

所有结果必须说明 frame_id，不能只给数值。
约定统一世界系、基座系、相机系命名，团队内禁止多套叫法。
视觉输出位姿前，先验证 TF 树闭环是否完整。
有外参就版本化管理，变更必须记录并可回滚。
任何抓取动作前，先做坐标与单位自检。

六、参数管理要“可复现、可追溯”

配置文件按场景分层：通用参数、设备参数、产线参数。
参数变更要可审计，谁改的、为什么改要留下记录。
运行时支持最小必要参数热更新，避免频繁重启。
默认值必须安全保守，避免一启动就高风险动作。
每次上线都保存参数快照，故障时能快速回到稳定版本。

七、容器化部署的实战要点

统一基础镜像和依赖版本，避免“我机器上能跑”。
一机多容器时，明确资源预算：CPU、内存、带宽。
视觉链路通常对延迟敏感，先保证实时性再追求吞吐。
容器健康检查要覆盖“节点活着 + 关键话题可用”，不是只看进程。
日志、配置、模型目录要规范挂载，便于运维和回滚。

八、可靠性设计要默认“会失败”

每条关键链路都要有超时机制。
每个节点都要有重连、重试、退避策略。
感知结果要有有效期，过期立刻失效。
外设断连时系统要可降级，不要全系统卡死。
失败要可观测，错误码和告警信息要让现场人员看得懂。

九、调试与验收要标准化

先定义最小闭环验收用例，再做功能扩展。
每次发布前固定执行同一套冒烟测试。
录制标准数据包，回归测试用同一数据对比结果漂移。
关键指标要量化：延迟、丢帧率、识别成功率、误检率。
问题复盘用“现象-根因-修复-预防”四段式沉淀。

十、安全与现场工程化

机器人执行必须有最终安全门，不可直接信任单帧视觉。
对异常值做边界检查，防止错误位姿直接驱动机械动作。
网络隔离和访问控制要做，避免误操作和广播风暴。
紧急停止和人工接管流程要有文档和演练。
上线策略建议灰度：先单机、再小批量、再全量。

十一、常见反模式，尽量避开

把业务逻辑写在感知节点里，后期很难维护。
只看“有消息”不看“消息是否新鲜”。
只在开发机验证，不做工控机压力测试。
不做版本固定，现场更新后行为漂移。
出问题只重启不定位，导致隐患长期积累。

十二、一套通用落地流程（建议你们长期沿用）

冻结接口契约。
跑通最小闭环。
建立自动化冒烟测试。
增加超时、重试、降级。
增加监控和日志。
小范围灰度。
全量上线并持续复盘。