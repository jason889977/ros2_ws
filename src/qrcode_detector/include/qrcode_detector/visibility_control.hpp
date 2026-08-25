#pragma once

#if defined _WIN32 || defined __CYGWIN__
  #ifdef __GNUC__
    #define QRCODE_DETECTOR_EXPORT __attribute__ ((dllexport))
    #define QRCODE_DETECTOR_IMPORT __attribute__ ((dllimport))
  #else
    #define QRCODE_DETECTOR_EXPORT __declspec(dllexport)
    #define QRCODE_DETECTOR_IMPORT __declspec(dllimport)
  #endif
  #ifdef QRCODE_DETECTOR_BUILDING_LIBRARY
    #define QRCODE_DETECTOR_PUBLIC QRCODE_DETECTOR_EXPORT
  #else
    #define QRCODE_DETECTOR_PUBLIC QRCODE_DETECTOR_IMPORT
  #endif
  #define QRCODE_DETECTOR_PUBLIC_TYPE QRCODE_DETECTOR_PUBLIC
  #define QRCODE_DETECTOR_LOCAL
#else
  #define QRCODE_DETECTOR_EXPORT __attribute__ ((visibility("default")))
  #define QRCODE_DETECTOR_IMPORT
  #if __GNUC__ >= 4
    #define QRCODE_DETECTOR_PUBLIC __attribute__ ((visibility("default")))
    #define QRCODE_DETECTOR_LOCAL  __attribute__ ((visibility("hidden")))
  #else
    #define QRCODE_DETECTOR_PUBLIC
    #define QRCODE_DETECTOR_LOCAL
  #endif
  #define QRCODE_DETECTOR_PUBLIC_TYPE
#endif
