FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /opt/ros2_ws

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    ros-humble-rclpy \
    ros-humble-std-msgs \
    ros-humble-std-srvs \
    && rm -rf /var/lib/apt/lists/*

COPY . /opt/ros2_ws

RUN /bin/bash -lc 'source /opt/ros/humble/setup.bash && colcon build --packages-select keyence_sr_wrapper --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release'

CMD ["/bin/bash", "-lc", "source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && ros2 launch keyence_sr_wrapper keyence_sr_node.launch.py"]
