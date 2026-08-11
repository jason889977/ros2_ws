# ROS2 Basler Camera System Documentation Suite

Version: v1.1.0
Last Updated: 2026-08-06
Target Audience: R&D and Test Engineers

This documentation suite covers dependencies, architecture, deployment SOP, module details, algorithm flow, testing strategy, and troubleshooting for this workspace.

## Documents

1. [01-Dependencies-And-Versions](01-Dependencies-And-Versions.md)
2. [02-Architecture-And-Modules](02-Architecture-And-Modules.md)
3. [03-Core-Flow-And-Algorithm](03-Core-Flow-And-Algorithm.md)
4. [04-Deployment-SOP](04-Deployment-SOP.md)
5. [05-Scripts-And-Automation](05-Scripts-And-Automation.md)
6. [06-Testing-And-Acceptance](06-Testing-And-Acceptance.md)
7. [07-Operations-And-Troubleshooting](07-Operations-And-Troubleshooting.md)
8. [08-ChangeLog](08-ChangeLog.md)
9. [09-Release-Gate-Checklist](09-Release-Gate-Checklist.md)
10. [10-Network-Tuning-Playbook](10-Network-Tuning-Playbook.md)
11. [11-V3-Freeze-Runbook](11-V3-Freeze-Runbook.md)

## Scope

- Basler pylon SDK integration with ROS 2 Humble
- Camera driver runtime via pylon_ros2_camera_wrapper
- QR recognition pipeline via qrcode_detector
- Deployment and test practices validated in this repository

## Out of Scope

- Third-party source code redesign in upstream Basler repository
- Non-Linux deployment targets
