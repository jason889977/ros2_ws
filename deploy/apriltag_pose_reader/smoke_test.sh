#!/usr/bin/env bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /opt/ros2_ws/install/setup.bash

fail() { echo "SMOKE TEST FAILED: $*" >&2; exit 1; }

ros2 node list | grep -Fxq "/apriltag" || fail "apriltag node is not running"
ros2 node list | grep -Fxq "/apriltag_pose_reader" || fail "apriltag_pose_reader node is not running"

ros2 topic list | grep -Fxq "/detections" || fail "detections topic is not available"
ros2 topic list | grep -Fxq "/apriltag/pose" || fail "/apriltag/pose topic is not available"
ros2 topic list | grep -Fxq "/apriltag/transform" || fail "/apriltag/transform topic is not available"

ros2 topic type "/apriltag/pose" | grep -Fxq 'geometry_msgs/msg/PoseStamped' || fail "pose topic type is wrong"
ros2 topic type "/apriltag/transform" | grep -Fxq 'geometry_msgs/msg/TransformStamped' || fail "transform topic type is wrong"

echo "SMOKE TEST PASSED: AprilTag detection and pose publication are active"
