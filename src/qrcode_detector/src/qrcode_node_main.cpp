#include <memory>
#include <rclcpp/rclcpp.hpp>

#include "qrcode_detector/qrcode_node.hpp"

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions options;
  auto node = std::make_shared<qrcode_detector::QRCodeNode>(options);
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
