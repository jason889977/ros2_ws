#include "qrcode_detector/qrcode_node.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>

#include <ament_index_cpp/get_package_share_directory.hpp>
#include <cv_bridge/cv_bridge.h>
#include <rclcpp_components/register_node_macro.hpp>
#include <sensor_msgs/image_encodings.hpp>

namespace qrcode_detector
{

namespace
{
std::string formatDouble(double value, int precision = 3)
{
  std::ostringstream ss;
  ss << std::fixed << std::setprecision(precision) << value;
  return ss.str();
}
}  // namespace

QRCodeNode::QRCodeNode(const rclcpp::NodeOptions & options)
: Node("wechat_qr_node", options),
  diagnostic_updater_(this)
{
  RCLCPP_INFO(get_logger(), "Initializing QR detector node (C++ Component)...");

  // Declare parameters
  declare_parameter<std::string>(
    "image_topic", "/my_camera/pylon_ros2_camera_node/image_raw");
  declare_parameter<std::string>("model_dir", "");
  declare_parameter<int>("queue_size", 1);
  declare_parameter<bool>("use_camera_info", false);
  declare_parameter<std::string>(
    "camera_info_topic", "/my_camera/pylon_ros2_camera_node/camera_info");
  declare_parameter<double>("qr_size_m", 0.10);
  declare_parameter<bool>("prefer_wechat_qr", true);
  declare_parameter<double>("deduplicate_window_s", 0.5);
  declare_parameter<double>("min_detect_interval_s", 0.2);
  declare_parameter<bool>("use_compressed", false);

  // Retrieve parameters
  image_topic_ = get_parameter("image_topic").as_string();
  model_dir_ = get_parameter("model_dir").as_string();
  queue_size_ = get_parameter("queue_size").as_int();
  use_camera_info_ = get_parameter("use_camera_info").as_bool();
  camera_info_topic_ = get_parameter("camera_info_topic").as_string();
  qr_size_m_ = get_parameter("qr_size_m").as_double();
  prefer_wechat_qr_ = get_parameter("prefer_wechat_qr").as_bool();
  deduplicate_window_s_ = get_parameter("deduplicate_window_s").as_double();
  min_detect_interval_s_ = get_parameter("min_detect_interval_s").as_double();
  use_compressed_ = get_parameter("use_compressed").as_bool();

  // Validate parameters
  if (!std::isfinite(qr_size_m_) || qr_size_m_ <= 0.0) {
    throw std::invalid_argument("qr_size_m must be a finite value greater than zero");
  }
  if (!std::isfinite(deduplicate_window_s_) || deduplicate_window_s_ < 0.0) {
    throw std::invalid_argument("deduplicate_window_s must be finite and non-negative");
  }
  if (!std::isfinite(min_detect_interval_s_) || min_detect_interval_s_ < 0.0) {
    throw std::invalid_argument("min_detect_interval_s must be finite and non-negative");
  }
  if (queue_size_ < 1) {
    throw std::invalid_argument("queue_size must be a positive integer");
  }

  metrics_started_at_ = now();

  // Resolve model directory
  if (model_dir_.empty()) {
    try {
      std::string pkg_share = ament_index_cpp::get_package_share_directory("qrcode_detector");
      model_dir_ = pkg_share + "/models";
    } catch (const std::exception & e) {
      RCLCPP_WARN(get_logger(), "Could not resolve share directory for models: %s", e.what());
    }
  }

  // Initialize detector
  initDetector(model_dir_, prefer_wechat_qr_);

  // Publishers
  result_pub_ = create_publisher<std_msgs::msg::String>("~/decoded_info", queue_size_);

  if (use_camera_info_) {
    pose_pub_ = create_publisher<geometry_msgs::msg::PoseStamped>("~/qr_pose", 10);
  }

  // QoS profile: BEST_EFFORT, KEEP_LAST(queue_size)
  rclcpp::QoS sensor_qos(queue_size_);
  sensor_qos.best_effort();

  if (use_compressed_) {
    std::string compressed_topic = image_topic_ + "/compressed";
    compressed_image_sub_ = create_subscription<sensor_msgs::msg::CompressedImage>(
      compressed_topic, sensor_qos,
      [this](const sensor_msgs::msg::CompressedImage::ConstSharedPtr msg) {
        compressedImageCallback(msg);
      });
    RCLCPP_INFO(get_logger(), "Subscribed to compressed image: %s", compressed_topic.c_str());
  } else {
    image_sub_ = create_subscription<sensor_msgs::msg::Image>(
      image_topic_, sensor_qos,
      [this](const sensor_msgs::msg::Image::ConstSharedPtr msg) {
        imageCallback(msg);
      });
    RCLCPP_INFO(get_logger(), "Subscribed to raw image: %s", image_topic_.c_str());
  }

  if (use_camera_info_) {
    rclcpp::QoS camera_info_qos(queue_size_);
    camera_info_qos.best_effort();

    camera_info_sub_ = create_subscription<sensor_msgs::msg::CameraInfo>(
      camera_info_topic_, camera_info_qos,
      [this](const sensor_msgs::msg::CameraInfo::ConstSharedPtr msg) {
        cameraInfoCallback(msg);
      });
    RCLCPP_INFO(
      get_logger(),
      "use_camera_info enabled, subscribing to %s, qr_size_m=%.3f",
      camera_info_topic_.c_str(), qr_size_m_);
  }

  // Diagnostics
  diagnostic_updater_.setHardwareID("qrcode_detector");
  diagnostic_updater_.add("QR Detector Status", this, &QRCodeNode::produceDiagnostics);

  RCLCPP_INFO(
    get_logger(),
    "WeChatQR detector node initialized. Target topic: %s, Backend: %s",
    image_topic_.c_str(), detector_kind_.c_str());
}

void QRCodeNode::initDetector(const std::string & model_dir, bool prefer_wechat_qr)
{
  if (!prefer_wechat_qr) {
    RCLCPP_INFO(get_logger(), "prefer_wechat_qr is false, using OpenCV QRCodeDetector.");
    detector_kind_ = "opencv";
    return;
  }

  std::vector<std::string> required_files = {
    "detect.prototxt",
    "detect.caffemodel",
    "sr.prototxt",
    "sr.caffemodel"
  };

  std::vector<std::string> missing;
  for (const auto & f : required_files) {
    std::filesystem::path p = std::filesystem::path(model_dir) / f;
    if (!std::filesystem::is_regular_file(p)) {
      missing.push_back(f);
    }
  }

  if (!missing.empty()) {
    std::string missing_str;
    for (const auto & m : missing) {
      if (!missing_str.empty()) missing_str += ", ";
      missing_str += m;
    }
    RCLCPP_WARN(
      get_logger(),
      "WeChatQR model files missing [%s], fallback to OpenCV QRCodeDetector.",
      missing_str.c_str());
    detector_kind_ = "opencv";
    return;
  }

  try {
    std::string detect_proto = (std::filesystem::path(model_dir) / "detect.prototxt").string();
    std::string detect_model = (std::filesystem::path(model_dir) / "detect.caffemodel").string();
    std::string sr_proto = (std::filesystem::path(model_dir) / "sr.prototxt").string();
    std::string sr_model = (std::filesystem::path(model_dir) / "sr.caffemodel").string();

    RCLCPP_INFO(get_logger(), "Loading WeChatQR models from: %s", model_dir.c_str());
    wechat_detector_ = cv::makePtr<cv::wechat_qrcode::WeChatQRCode>(
      detect_proto, detect_model, sr_proto, sr_model);
    detector_kind_ = "wechat";
  } catch (const std::exception & e) {
    RCLCPP_WARN(
      get_logger(),
      "Failed to instantiate WeChatQRCode: %s, fallback to OpenCV QRCodeDetector.",
      e.what());
    detector_kind_ = "opencv";
  }
}

bool QRCodeNode::shouldPublish(const std::string & info, const rclcpp::Time & current_time)
{
  if (deduplicate_window_s_ <= 0.0) {
    return true;
  }

  auto it = last_published_at_.find(info);
  bool should_pub = false;
  if (it == last_published_at_.end()) {
    should_pub = true;
  } else {
    double elapsed = (current_time - it->second).seconds();
    if (elapsed >= deduplicate_window_s_) {
      should_pub = true;
    }
  }

  if (should_pub) {
    last_published_at_[info] = current_time;
  }

  if (last_published_at_.size() > 100) {
    double cutoff_seconds = deduplicate_window_s_ * 10.0;
    for (auto map_it = last_published_at_.begin(); map_it != last_published_at_.end(); ) {
      if ((current_time - map_it->second).seconds() > cutoff_seconds) {
        map_it = last_published_at_.erase(map_it);
      } else {
        ++map_it;
      }
    }
  }

  return should_pub;
}

DetectionResult QRCodeNode::decodeQR(const cv::Mat & image)
{
  DetectionResult result;
  if (image.empty()) {
    return result;
  }

  if (detector_kind_ == "wechat" && wechat_detector_) {
    std::vector<cv::Mat> points;
    std::vector<std::string> decoded = wechat_detector_->detectAndDecode(image, points);
    for (size_t i = 0; i < decoded.size(); ++i) {
      if (decoded[i].empty()) {
        continue;
      }
      result.decoded_info.push_back(decoded[i]);

      std::vector<cv::Point2f> corners;
      if (i < points.size() && !points[i].empty()) {
        cv::Mat pt = points[i];
        if (pt.total() == 8) {
          cv::Mat flat = pt.reshape(2, 4);
          bool valid = true;
          for (int r = 0; r < 4; ++r) {
            cv::Point2f p = flat.at<cv::Point2f>(r, 0);
            if (!std::isfinite(p.x) || !std::isfinite(p.y)) {
              valid = false;
              break;
            }
            corners.push_back(p);
          }
          if (!valid) {
            corners.clear();
          }
        }
      }
      result.corner_points.push_back(corners);
    }
    return result;
  }

  // OpenCV QRCodeDetector backend
  std::vector<cv::Point2f> pts;
  std::string decoded = opencv_detector_.detectAndDecode(image, pts);
  if (!decoded.empty()) {
    result.decoded_info.push_back(decoded);
    if (pts.size() == 4) {
      bool valid = true;
      for (const auto & p : pts) {
        if (!std::isfinite(p.x) || !std::isfinite(p.y)) {
          valid = false;
          break;
        }
      }
      result.corner_points.push_back(valid ? pts : std::vector<cv::Point2f>{});
    } else {
      result.corner_points.push_back({});
    }
    return result;
  }

  std::vector<std::string> multi_decoded;
  std::vector<cv::Point2f> multi_pts;
  if (opencv_detector_.detectAndDecodeMulti(image, multi_decoded, multi_pts)) {
    for (size_t i = 0; i < multi_decoded.size(); ++i) {
      if (multi_decoded[i].empty()) {
        continue;
      }
      result.decoded_info.push_back(multi_decoded[i]);
      std::vector<cv::Point2f> corners;
      if (multi_pts.size() >= (i + 1) * 4) {
        bool valid = true;
        for (size_t k = 0; k < 4; ++k) {
          cv::Point2f p = multi_pts[i * 4 + k];
          if (!std::isfinite(p.x) || !std::isfinite(p.y)) {
            valid = false;
            break;
          }
          corners.push_back(p);
        }
        if (!valid) {
          corners.clear();
        }
      }
      result.corner_points.push_back(corners);
    }
  }

  return result;
}

bool QRCodeNode::rotationMatrixToQuaternion(
  const cv::Mat & R, double & qx, double & qy, double & qz, double & qw)
{
  if (R.rows != 3 || R.cols != 3) {
    return false;
  }

  double r00 = R.at<double>(0, 0);
  double r01 = R.at<double>(0, 1);
  double r02 = R.at<double>(0, 2);
  double r10 = R.at<double>(1, 0);
  double r11 = R.at<double>(1, 1);
  double r12 = R.at<double>(1, 2);
  double r20 = R.at<double>(2, 0);
  double r21 = R.at<double>(2, 1);
  double r22 = R.at<double>(2, 2);

  double trace = r00 + r11 + r22;
  if (trace > 0.0) {
    double s = 0.5 / std::sqrt(trace + 1.0);
    qw = 0.25 / s;
    qx = (r21 - r12) * s;
    qy = (r02 - r20) * s;
    qz = (r10 - r01) * s;
  } else if (r00 > r11 && r00 > r22) {
    double s = 2.0 * std::sqrt(1.0 + r00 - r11 - r22);
    qw = (r21 - r12) / s;
    qx = 0.25 * s;
    qy = (r01 + r10) / s;
    qz = (r02 + r20) / s;
  } else if (r11 > r22) {
    double s = 2.0 * std::sqrt(1.0 + r11 - r00 - r22);
    qw = (r02 - r20) / s;
    qx = (r01 + r10) / s;
    qy = 0.25 * s;
    qz = (r12 + r21) / s;
  } else {
    double s = 2.0 * std::sqrt(1.0 + r22 - r00 - r11);
    qw = (r10 - r01) / s;
    qx = (r02 + r20) / s;
    qy = (r12 + r21) / s;
    qz = 0.25 * s;
  }
  return true;
}

std::shared_ptr<geometry_msgs::msg::PoseStamped> QRCodeNode::estimatePose(
  const std::vector<cv::Point2f> & corners,
  const std_msgs::msg::Header & header)
{
  if (!has_camera_matrix_ || corners.size() != 4) {
    return nullptr;
  }

  double s = qr_size_m_;
  std::vector<cv::Point3d> object_points = {
    {-s / 2.0,  s / 2.0, 0.0},
    { s / 2.0,  s / 2.0, 0.0},
    { s / 2.0, -s / 2.0, 0.0},
    {-s / 2.0, -s / 2.0, 0.0}
  };

  std::vector<cv::Point2d> image_points;
  for (const auto & pt : corners) {
    image_points.emplace_back(static_cast<double>(pt.x), static_cast<double>(pt.y));
  }

  cv::Mat rvec, tvec;
  bool success = cv::solvePnP(
    object_points, image_points,
    camera_matrix_, dist_coeffs_,
    rvec, tvec, false, cv::SOLVEPNP_ITERATIVE);

  if (!success) {
    RCLCPP_WARN(get_logger(), "solvePnP did not converge for QR code");
    return nullptr;
  }

  cv::Mat R;
  cv::Rodrigues(rvec, R);

  double qx, qy, qz, qw;
  rotationMatrixToQuaternion(R, qx, qy, qz, qw);

  auto pose = std::make_shared<geometry_msgs::msg::PoseStamped>();
  pose->header.stamp = header.stamp;
  pose->header.frame_id = camera_frame_id_.empty() ? header.frame_id : camera_frame_id_;
  pose->pose.position.x = tvec.at<double>(0);
  pose->pose.position.y = tvec.at<double>(1);
  pose->pose.position.z = tvec.at<double>(2);
  pose->pose.orientation.x = qx;
  pose->pose.orientation.y = qy;
  pose->pose.orientation.z = qz;
  pose->pose.orientation.w = qw;

  return pose;
}

void QRCodeNode::cameraInfoCallback(const sensor_msgs::msg::CameraInfo::ConstSharedPtr msg)
{
  if (has_camera_matrix_) {
    return;
  }

  cv::Mat K(3, 3, CV_64F);
  for (int r = 0; r < 3; ++r) {
    for (int c = 0; c < 3; ++c) {
      K.at<double>(r, c) = msg->k[r * 3 + c];
    }
  }

  double fx = K.at<double>(0, 0);
  double fy = K.at<double>(1, 1);
  if (fx <= 1.0 || fy <= 1.0) {
    RCLCPP_ERROR(
      get_logger(),
      "Camera intrinsics appear to be placeholders (fx=%.3f, fy=%.3f), qr_pose disabled.",
      fx, fy);
    return;
  }

  camera_matrix_ = K;
  dist_coeffs_ = cv::Mat(1, static_cast<int>(msg->d.size()), CV_64F);
  for (size_t i = 0; i < msg->d.size(); ++i) {
    dist_coeffs_.at<double>(0, static_cast<int>(i)) = msg->d[i];
  }
  camera_frame_id_ = msg->header.frame_id;
  has_camera_matrix_ = true;

  RCLCPP_INFO(
    get_logger(),
    "Camera intrinsics loaded (frame=%s): fx=%.1f, fy=%.1f, cx=%.1f, cy=%.1f",
    camera_frame_id_.c_str(),
    camera_matrix_.at<double>(0, 0), camera_matrix_.at<double>(1, 1),
    camera_matrix_.at<double>(0, 2), camera_matrix_.at<double>(1, 2));
}

void QRCodeNode::processDecodedResults(
  const DetectionResult & result,
  const std_msgs::msg::Header & header,
  std::chrono::steady_clock::time_point processing_start)
{
  auto now_time = now();

  if (!result.decoded_info.empty()) {
    detections_seen_ += result.decoded_info.size();
    last_detection_time_ = now_time;
    has_detected_qr_ = true;

    for (size_t i = 0; i < result.decoded_info.size(); ++i) {
      const auto & info = result.decoded_info[i];

      // Pose estimation
      if (pose_pub_ && i < result.corner_points.size() && result.corner_points[i].size() == 4) {
        auto pose = estimatePose(result.corner_points[i], header);
        if (pose) {
          pose_pub_->publish(*pose);
          RCLCPP_INFO(
            get_logger(),
            "📐 QR Pose: x=%.3f y=%.3f z=%.3f",
            pose->pose.position.x, pose->pose.position.y, pose->pose.position.z);
        }
      }

      if (!shouldPublish(info, now_time)) {
        continue;
      }

      RCLCPP_INFO(get_logger(), "✅ 识别到二维码: %s", info.c_str());
      std_msgs::msg::String str_msg;
      str_msg.data = info;
      result_pub_->publish(str_msg);
      results_published_++;
    }
  }

  frames_processed_++;

  auto processing_end = std::chrono::steady_clock::now();
  double elapsed_s = std::chrono::duration<double>(processing_end - processing_start).count();
  total_processing_time_s_ += elapsed_s;
  double elapsed_ms = elapsed_s * 1000.0;
  last_processing_ms_ = elapsed_ms;
  max_processing_ms_ = std::max(max_processing_ms_, elapsed_ms);
}

void QRCodeNode::imageCallback(const sensor_msgs::msg::Image::ConstSharedPtr msg)
{
  frames_received_++;
  auto current_time = now();
  last_image_time_ = current_time;
  has_received_image_ = true;

  if (min_detect_interval_s_ > 0.0) {
    if (last_detect_time_.nanoseconds() > 0 &&
        (current_time - last_detect_time_).seconds() < min_detect_interval_s_)
    {
      frames_skipped_++;
      return;
    }
    last_detect_time_ = current_time;
  }

  auto processing_start = std::chrono::steady_clock::now();

  cv::Mat cv_image;
  try {
    // Zero-copy share if passthrough/mono8, or convert to mono8
    cv_bridge::CvImageConstPtr cv_ptr = cv_bridge::toCvShare(msg, msg->encoding);
    cv_image = cv_ptr->image;
    if (cv_image.channels() > 1 && msg->encoding != sensor_msgs::image_encodings::MONO8) {
      // WeChatQR handles BGR or Mono8 directly
      if (msg->encoding == sensor_msgs::image_encodings::RGB8) {
        cv::cvtColor(cv_image, cv_image, cv::COLOR_RGB2BGR);
      }
    }
  } catch (const cv_bridge::Exception & e) {
    processing_errors_++;
    RCLCPP_ERROR(get_logger(), "cv_bridge exception: %s", e.what());
    return;
  }

  DetectionResult result;
  try {
    result = decodeQR(cv_image);
  } catch (const std::exception & e) {
    processing_errors_++;
    RCLCPP_ERROR(get_logger(), "QR decode exception: %s", e.what());
    return;
  }

  processDecodedResults(result, msg->header, processing_start);
}

void QRCodeNode::compressedImageCallback(const sensor_msgs::msg::CompressedImage::ConstSharedPtr msg)
{
  frames_received_++;
  auto current_time = now();
  last_image_time_ = current_time;
  has_received_image_ = true;

  if (min_detect_interval_s_ > 0.0) {
    if (last_detect_time_.nanoseconds() > 0 &&
        (current_time - last_detect_time_).seconds() < min_detect_interval_s_)
    {
      frames_skipped_++;
      return;
    }
    last_detect_time_ = current_time;
  }

  auto processing_start = std::chrono::steady_clock::now();

  cv::Mat cv_image;
  try {
    cv_image = cv::imdecode(cv::Mat(msg->data), cv::IMREAD_GRAYSCALE);
    if (cv_image.empty()) {
      processing_errors_++;
      RCLCPP_ERROR(get_logger(), "Compressed image decode failed");
      return;
    }
  } catch (const std::exception & e) {
    processing_errors_++;
    RCLCPP_ERROR(get_logger(), "Compressed image decode exception: %s", e.what());
    return;
  }

  DetectionResult result;
  try {
    result = decodeQR(cv_image);
  } catch (const std::exception & e) {
    processing_errors_++;
    RCLCPP_ERROR(get_logger(), "QR decode exception: %s", e.what());
    return;
  }

  processDecodedResults(result, msg->header, processing_start);
}

void QRCodeNode::produceDiagnostics(diagnostic_updater::DiagnosticStatusWrapper & stat)
{
  auto current_time = now();

  if (!has_received_image_) {
    stat.summary(diagnostic_msgs::msg::DiagnosticStatus::WARN, "Waiting for image data");
  } else if ((current_time - last_image_time_).seconds() > 5.0) {
    stat.summary(diagnostic_msgs::msg::DiagnosticStatus::ERROR, "No recent image data");
  } else if (processing_errors_ > 0) {
    stat.summary(diagnostic_msgs::msg::DiagnosticStatus::WARN, "Processing errors detected");
  } else {
    stat.summary(diagnostic_msgs::msg::DiagnosticStatus::OK, "Backend: " + detector_kind_);
  }

  stat.add("backend", detector_kind_);
  stat.add("frames_received", std::to_string(frames_received_));
  stat.add("frames_processed", std::to_string(frames_processed_));
  stat.add("detections_seen", std::to_string(detections_seen_));
  stat.add("results_published", std::to_string(results_published_));
  stat.add("processing_errors", std::to_string(processing_errors_));
  stat.add("frames_skipped", std::to_string(frames_skipped_));

  double total_elapsed_s = std::max(0.0, (current_time - metrics_started_at_).seconds());
  double processing_fps = (total_elapsed_s > 0.0) ?
    (static_cast<double>(frames_processed_) / total_elapsed_s) : 0.0;
  double average_processing_ms = (frames_processed_ > 0) ?
    (total_processing_time_s_ * 1000.0 / static_cast<double>(frames_processed_)) : 0.0;

  stat.add("processing_fps", formatDouble(processing_fps));
  stat.add("last_processing_ms", formatDouble(last_processing_ms_));
  stat.add("average_processing_ms", formatDouble(average_processing_ms));
  stat.add("max_processing_ms", formatDouble(max_processing_ms_));

  if (has_detected_qr_) {
    double sec_since = std::max(0.0, (current_time - last_detection_time_).seconds());
    stat.add("seconds_since_detection", formatDouble(sec_since));
  }
}

}  // namespace qrcode_detector

RCLCPP_COMPONENTS_REGISTER_NODE(qrcode_detector::QRCodeNode)
