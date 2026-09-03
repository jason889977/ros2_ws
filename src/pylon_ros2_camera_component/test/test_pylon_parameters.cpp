// Unit tests for PylonROS2CameraParameter::validateParameterSet and
// shutterModeString — pure logic that needs no camera hardware.

#include <gtest/gtest.h>

#include <cmath>
#include <string>

#include <rclcpp/rclcpp.hpp>

#include "pylon_ros2_camera_parameter.hpp"

using pylon_ros2_camera::PylonROS2CameraParameter;
using pylon_ros2_camera::SHUTTER_MODE;
using pylon_ros2_camera::SM_ROLLING;
using pylon_ros2_camera::SM_GLOBAL;
using pylon_ros2_camera::SM_GLOBAL_RESET_RELEASE;

// The parameter fields are protected; a thin subclass exposes them to tests.
class TestableParams : public PylonROS2CameraParameter
{
public:
  void validate(rclcpp::Node & nh) {validateParameterSet(nh);}

  void setFrameRate(double v) {frame_rate_ = v;}
  double frameRate() const {return frame_rate_;}
  void setExposure(double v, bool given) {exposure_ = v; exposure_given_ = given;}
  bool exposureGiven() const {return exposure_given_;}
  void setGain(double v, bool given) {gain_ = v; gain_given_ = given;}
  bool gainGiven() const {return gain_given_;}
  void setBrightness(int v, bool given) {brightness_ = v; brightness_given_ = given;}
  bool brightnessGiven() const {return brightness_given_;}
  void setShutterMode(SHUTTER_MODE m) {shutter_mode_ = m;}
};

class PylonParameterTest : public ::testing::Test
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

  PylonParameterTest()
  : nh_(std::make_shared<rclcpp::Node>("pylon_parameter_test_node"))
  {
  }

  rclcpp::Node::SharedPtr nh_;
};

TEST_F(PylonParameterTest, InvalidFrameRateIsResetToDefault)
{
  TestableParams p;
  p.setFrameRate(0.0);
  p.validate(*nh_);
  EXPECT_DOUBLE_EQ(p.frameRate(), 5.0);

  TestableParams p2;
  p2.setFrameRate(-3.0);
  p2.validate(*nh_);
  EXPECT_DOUBLE_EQ(p2.frameRate(), 5.0);

  TestableParams p3;
  p3.setFrameRate(std::nan(""));
  p3.validate(*nh_);
  EXPECT_DOUBLE_EQ(p3.frameRate(), 5.0);
}

TEST_F(PylonParameterTest, ValidFrameRatesAreKept)
{
  TestableParams p;
  p.setFrameRate(30.0);
  p.validate(*nh_);
  EXPECT_DOUBLE_EQ(p.frameRate(), 30.0);

  TestableParams p2;
  p2.setFrameRate(-1.0);  // -1 means "auto / device default"
  p2.validate(*nh_);
  EXPECT_DOUBLE_EQ(p2.frameRate(), -1.0);
}

TEST_F(PylonParameterTest, OutOfRangeExposureDropsGivenFlag)
{
  TestableParams p;
  p.setExposure(0.0, true);
  p.validate(*nh_);
  EXPECT_FALSE(p.exposureGiven());

  TestableParams p2;
  p2.setExposure(2e7, true);
  p2.validate(*nh_);
  EXPECT_FALSE(p2.exposureGiven());
}

TEST_F(PylonParameterTest, ValidExposureKeepsGivenFlag)
{
  TestableParams p;
  p.setExposure(5000.0, true);
  p.validate(*nh_);
  EXPECT_TRUE(p.exposureGiven());
}

TEST_F(PylonParameterTest, OutOfRangeGainDropsGivenFlag)
{
  TestableParams p;
  p.setGain(1.5, true);
  p.validate(*nh_);
  EXPECT_FALSE(p.gainGiven());

  TestableParams p2;
  p2.setGain(-0.1, true);
  p2.validate(*nh_);
  EXPECT_FALSE(p2.gainGiven());
}

TEST_F(PylonParameterTest, OutOfRangeBrightnessDropsGivenFlag)
{
  TestableParams p;
  p.setBrightness(300, true);
  p.validate(*nh_);
  EXPECT_FALSE(p.brightnessGiven());

  TestableParams p2;
  p2.setBrightness(-1, true);
  p2.validate(*nh_);
  EXPECT_FALSE(p2.brightnessGiven());
}

TEST_F(PylonParameterTest, ShutterModeStringMapping)
{
  TestableParams p;
  p.setShutterMode(SM_ROLLING);
  EXPECT_EQ(p.shutterModeString(), "rolling");
  p.setShutterMode(SM_GLOBAL);
  EXPECT_EQ(p.shutterModeString(), "global");
  p.setShutterMode(SM_GLOBAL_RESET_RELEASE);
  EXPECT_EQ(p.shutterModeString(), "global_reset");
  p.setShutterMode(static_cast<SHUTTER_MODE>(99));
  EXPECT_EQ(p.shutterModeString(), "default_shutter_mode");
}
