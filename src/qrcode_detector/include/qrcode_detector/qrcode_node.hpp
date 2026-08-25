#pragma once

#include <chrono>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include <diagnostic_updater/diagnostic_updater.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <opencv2/opencv.hpp>
#include <opencv2/wechat_qrcode.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/compressed_image.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/string.hpp>

#include "qrcode_detector/visibility_control.hpp"

namespace qrcode_detector
{

struct DetectionResult
{
  std::vector<std::string> decoded_info;
  std::vector<std::vector<cv::Point2f>> corner_points;
};

class QRCODE_DETECTOR_PUBLIC QRCodeNode : public rclcpp::Node
{
public:
  explicit QRCodeNode(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());
  virtual ~QRCodeNode() = default;

  // Pure logic helpers made public/accessible for unit testing
  static bool rotationMatrixToQuaternion(
    const cv::Mat & R, double & qx, double & qy, double & qz, double & qw);
  bool shouldPublish(const std::string & info, const rclcpp::Time & now);
  DetectionResult decodeQR(const cv::Mat & image);
  std::shared_ptr<geometry_msgs::msg::PoseStamped> estimatePose(
    const std::vector<cv::Point2f> & corners,
    const std_msgs::msg::Header & header);

  void produceDiagnostics(diagnostic_updater::DiagnosticStatusWrapper & stat);

  const std::string & getDetectorKind() const { return detector_kind_; }

private:
  void imageCallback(const sensor_msgs::msg::Image::ConstSharedPtr msg);
  void compressedImageCallback(const sensor_msgs::msg::CompressedImage::ConstSharedPtr msg);
  void cameraInfoCallback(const sensor_msgs::msg::CameraInfo::ConstSharedPtr msg);

  void processDecodedResults(
    const DetectionResult & result,
    const std_msgs::msg::Header & header,
    std::chrono::steady_clock::time_point processing_start);

  void initDetector(const std::string & model_dir, bool prefer_wechat_qr);

  // Parameters
  std::string image_topic_;
  std::string model_dir_;
  std::string camera_info_topic_;
  int queue_size_{1};
  bool use_camera_info_{false};
  double qr_size_m_{0.10};
  bool prefer_wechat_qr_{true};
  double deduplicate_window_s_{0.5};
  double min_detect_interval_s_{0.2};
  bool use_compressed_{false};

  // State
  std::string detector_kind_{"opencv"};
  cv::Ptr<cv::wechat_qrcode::WeChatQRCode> wechat_detector_;
  cv::QRCodeDetector opencv_detector_;

  bool has_camera_matrix_{false};
  cv::Mat camera_matrix_;
  cv::Mat dist_coeffs_;
  std::string camera_frame_id_;

  std::unordered_map<std::string, rclcpp::Time> last_published_at_;
  rclcpp::Time last_detect_time_{0, 0, RCL_ROS_TIME};

  // Metrics
  uint64_t frames_received_{0};
  uint64_t frames_processed_{0};
  uint64_t detections_seen_{0};
  uint64_t results_published_{0};
  uint64_t processing_errors_{0};
  uint64_t frames_skipped_{0};

  rclcpp::Time metrics_started_at_;
  double total_processing_time_s_{0.0};
  double last_processing_ms_{0.0};
  double max_processing_ms_{0.0};

  bool has_received_image_{false};
  rclcpp::Time last_image_time_{0, 0, RCL_ROS_TIME};
  bool has_detected_qr_{false};
  rclcpp::Time last_detection_time_{0, 0, RCL_ROS_TIME};

  // ROS interfaces
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr result_pub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_pub_;

  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_;
  rclcpp::Subscription<sensor_msgs::msg::CompressedImage>::SharedPtr compressed_image_sub_;
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr camera_info_sub_;

  diagnostic_updater::Updater diagnostic_updater_;
};

}  // namespace qrcode_detector
