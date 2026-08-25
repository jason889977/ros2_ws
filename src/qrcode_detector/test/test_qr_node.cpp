#include <gtest/gtest.h>
#include <cmath>
#include <opencv2/opencv.hpp>
#include <rclcpp/rclcpp.hpp>

#include "qrcode_detector/qrcode_node.hpp"

class QRNodeTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite()
  {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }

  static void TearDownTestSuite()
  {
    if (rclcpp::ok()) {
      rclcpp::shutdown();
    }
  }
};

TEST_F(QRNodeTest, RotationMatrixToQuaternionIdentity)
{
  cv::Mat R = cv::Mat::eye(3, 3, CV_64F);
  double qx = 0, qy = 0, qz = 0, qw = 0;
  bool ok = qrcode_detector::QRCodeNode::rotationMatrixToQuaternion(R, qx, qy, qz, qw);
  EXPECT_TRUE(ok);
  EXPECT_NEAR(qw, 1.0, 1e-6);
  EXPECT_NEAR(qx, 0.0, 1e-6);
  EXPECT_NEAR(qy, 0.0, 1e-6);
  EXPECT_NEAR(qz, 0.0, 1e-6);
}

TEST_F(QRNodeTest, RotationMatrixToQuaternion90DegZ)
{
  cv::Mat R = (cv::Mat_<double>(3, 3) <<
    0, -1, 0,
    1,  0, 0,
    0,  0, 1);
  double qx = 0, qy = 0, qz = 0, qw = 0;
  bool ok = qrcode_detector::QRCodeNode::rotationMatrixToQuaternion(R, qx, qy, qz, qw);
  EXPECT_TRUE(ok);
  EXPECT_NEAR(qw, std::cos(M_PI / 4.0), 1e-5);
  EXPECT_NEAR(qz, std::sin(M_PI / 4.0), 1e-5);
  EXPECT_NEAR(qx, 0.0, 1e-5);
  EXPECT_NEAR(qy, 0.0, 1e-5);
}

TEST_F(QRNodeTest, DeduplicationLogic)
{
  rclcpp::NodeOptions options;
  options.append_parameter_override("deduplicate_window_s", 0.5);
  options.append_parameter_override("min_detect_interval_s", 0.0);
  options.append_parameter_override("prefer_wechat_qr", false);

  auto node = std::make_shared<qrcode_detector::QRCodeNode>(options);

  rclcpp::Time t0(100, 0, RCL_ROS_TIME);
  EXPECT_TRUE(node->shouldPublish("ABC123", t0));
  // Same string within 0.5s -> false
  rclcpp::Time t1(100, 200000000, RCL_ROS_TIME); // +0.2s
  EXPECT_FALSE(node->shouldPublish("ABC123", t1));
  // Different string -> true
  EXPECT_TRUE(node->shouldPublish("XYZ789", t1));
  // After 0.5s -> true
  rclcpp::Time t2(100, 600000000, RCL_ROS_TIME); // +0.6s
  EXPECT_TRUE(node->shouldPublish("ABC123", t2));
}

TEST_F(QRNodeTest, ZeroDeduplicationWindowAlwaysPublishes)
{
  rclcpp::NodeOptions options;
  options.append_parameter_override("deduplicate_window_s", 0.0);
  options.append_parameter_override("prefer_wechat_qr", false);

  auto node = std::make_shared<qrcode_detector::QRCodeNode>(options);
  rclcpp::Time t0(100, 0, RCL_ROS_TIME);
  EXPECT_TRUE(node->shouldPublish("ABC123", t0));
  EXPECT_TRUE(node->shouldPublish("ABC123", t0));
}

TEST_F(QRNodeTest, ParameterValidationRejectsInvalidValues)
{
  {
    rclcpp::NodeOptions options;
    options.append_parameter_override("qr_size_m", -0.05);
    EXPECT_THROW(std::make_shared<qrcode_detector::QRCodeNode>(options), std::invalid_argument);
  }
  {
    rclcpp::NodeOptions options;
    options.append_parameter_override("deduplicate_window_s", -1.0);
    EXPECT_THROW(std::make_shared<qrcode_detector::QRCodeNode>(options), std::invalid_argument);
  }
  {
    rclcpp::NodeOptions options;
    options.append_parameter_override("min_detect_interval_s", -0.1);
    EXPECT_THROW(std::make_shared<qrcode_detector::QRCodeNode>(options), std::invalid_argument);
  }
  {
    rclcpp::NodeOptions options;
    options.append_parameter_override("queue_size", 0);
    EXPECT_THROW(std::make_shared<qrcode_detector::QRCodeNode>(options), std::invalid_argument);
  }
}
