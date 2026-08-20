FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /opt/ros2_ws

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    ros-humble-tf2-ros \
    ros-humble-tf2-msgs \
    ros-humble-cv-bridge \
    ros-humble-image-transport \
    ros-humble-sensor-msgs \
    ros-humble-geometry-msgs \
    ros-humble-apriltag-ros \
    ros-humble-apriltag-msgs \
    && rm -rf /var/lib/apt/lists/*

COPY src/apriltag_pose_reader/ src/apriltag_pose_reader/

RUN /bin/bash -lc 'source /opt/ros/humble/setup.bash && colcon build --packages-select apriltag_pose_reader --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release'

CMD ["/bin/bash", "-lc", "source /opt/ros/humble/setup.bash && source /opt/ros2_ws/install/setup.bash && ros2 launch apriltag_pose_reader apriltag_pose_reader.launch.py"]
