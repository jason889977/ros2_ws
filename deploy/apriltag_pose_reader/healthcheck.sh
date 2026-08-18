#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

node="/apriltag_pose_reader"
pose_topic="/apriltag/pose"
transform_topic="/apriltag/transform"

test -n "$(ros2 node list | grep -Fx "$node" || true)" || exit 1
ros2 topic list | grep -Fxq "$pose_topic" || exit 1
ros2 topic list | grep -Fxq "$transform_topic" || exit 1

ros2 topic type "$pose_topic" | grep -Fxq 'geometry_msgs/msg/PoseStamped' || exit 1
ros2 topic type "$transform_topic" | grep -Fxq 'geometry_msgs/msg/TransformStamped' || exit 1

exit 0
