# Keyence SR Wrapper Module Delivery

## 构建

```bash
docker build -f deploy/keyence_sr_wrapper/Dockerfile -t keyence_sr_wrapper_20260818_v1.0 .
```

## 运行

```bash
cp deploy/keyence_sr_wrapper/.env.example deploy/keyence_sr_wrapper/.env
docker compose --env-file deploy/keyence_sr_wrapper/.env \
  -f deploy/keyence_sr_wrapper/docker-compose.yml up -d
```

## 验收

```bash
docker exec keyence_sr_wrapper /opt/ros2_ws/deploy/keyence_sr_wrapper/smoke_test.sh
docker inspect --format '{{json .State.Health}}' keyence_sr_wrapper
```

## 前置条件

- 目标扫码器 IP 与端口必须可达。
- 默认 IP：`172.31.0.91`
- 默认端口：`9004`
- 该模块通过 TCP 连接与扫码器通信，不依赖串口设备。
