# XLeRobot-Bessie

这是 Bessie 机器人的本地控制项目，只保存针对 Bessie 新增和修改的代码：双臂、头部和车轮网页控制，手柄与键盘控制，安全限位，关机姿态，末端联动和训练数据采集。

## 与 XLeRobot 的关系

本项目建立在 [XLeRobot](https://github.com/Vector-Wangel/XLeRobot) 和 [LeRobot](https://github.com/huggingface/lerobot) 之上。原始 XLeRobot 源码、机械结构、硬件模型、仿真环境和通用文档不在本仓库中，请从上游项目获取。本仓库只记录 Bessie 的增量代码和实机参数。

开始前请先按照 XLeRobot 上游文档完成硬件装配，并安装兼容的 LeRobot 环境。代码使用 Apache-2.0 许可；上游项目仍归各自作者所有。

## 包含内容

- `xlerobot_web.py`：Bessie 网页控制服务与运行时安全监控。
- `arm_gamepad.*`、`gamepad_mapping.js`：手柄关节、头部和车轮控制。
- `cartesian_control.*`、`so101_kinematics.py`：双臂平面末端增量控制。
- `data_collection/`：相机、动作和状态采集，以及 LeRobot v2 数据导出。
- `calibration/`：Bessie 的电机校准、安全限位和安全关闭姿态。
- `calibrate_*.py`、`record_*.py`、`finalize_safety_limits.py`：Bessie 校准和限位工具。
- `safe_shutdown.py`：受限速控制的安全关闭流程。
- `tests/`：控制规划、浏览器输入和数据采集测试。

## 安装

建议使用 Python 3.12。先按照 XLeRobot 上游说明安装其兼容版本的 LeRobot，然后安装本项目额外依赖：

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

如果使用头部重新校准脚本，LeRobot 环境还需要包含 XLeRobot 的 `xlerobot_mount` 模块。该模块来自上游 XLeRobot，本仓库没有复制。

## 本机设备配置

```bash
cp robot_ports.env.example robot_ports.env
ls -l /dev/serial/by-id/
v4l2-ctl --list-devices
```

把 `robot_ports.env` 中的串口和相机路径替换成当前机器检测到的路径。该文件被 Git 忽略，不会上传设备序列号。

仓库包含 Bessie 的校准和安全参数。这些参数只适用于 Bessie。换到其他机器人时必须重新校准，并重新测量所有软件安全限位。

## 启动

接好两个控制总线和相机，确认双臂周围没有障碍物。首次测试车轮时必须架空机器人：

```bash
./start_web_controller.sh
```

浏览器访问 `http://127.0.0.1:8765/`。控制器启动时读取实际关节位置，不会自动归零。页面显示 `Safety monitor active — motion permitted` 后才能开始操作。

主要保护包括：

- 所有位置指令受 Bessie 实测软件限位约束。
- 目标或实际位置越界时，车轮停车，双臂和头部保持位置，并锁存急停。
- 车轮命令有短时超时保护；手柄或页面断联后自动停车。
- 末端控制限制每次位移、关节跳变和目标跟随误差。
- `/tmp/xlerobot-controller.lock` 防止两个控制程序同时占用串口。

软件保护不能代替实体电源开关。调试时应始终保证可以立即切断 12V 电源。

## 测试

```bash
PYTHONPATH=. ./.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

浏览器输入测试位于 `tests/*.html`，需要支持 Gamepad API 的浏览器环境。
