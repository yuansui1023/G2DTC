# G2DTC

General 2D Material Transfer Controller：用于二维材料转移装置的通用桌面控制程序。

G2DTC 把“实验装置中的逻辑自由度”和“实际连接的硬件”分开。Transfer Arm、Stage 和 Microscope 始终保持固定布局，但每个自由度可以随时选择某台电机、设为手动，或保持未分配。

## 当前功能

- Transfer Arm：X、Y、Z
- Stage：X、Y、Z、Rz、温控
- Microscope：X、Y、Z
- 共 10 个运动自由度和 1 个温控自由度
- 设备自由分配，同一物理设备不会被重复占用
- 选择设备后才显示对应控制面板
- “手动”模式不向任何硬件发送命令
- “未分配”模式保持空白占位
- 分配和硬件配置自动保存
- 串口操作在后台线程执行，不阻塞窗口
- `Esc` 或顶部按钮停止所有已连接电机
- 自带演示模式，没有硬件也能检查全部界面

## 已支持硬件

### Newport ESP300

- 三个轴分别作为三个独立电机参与分配
- 三轴共享同一个串口和通信锁
- 相对/绝对移动、点动、停止、使能、坐标归零、Home、软件限位
- 自动读取控制器原生单位和最大速度

### Newport NanoPZ PZC200

- 每个控制器地址作为一台可分配电机
- 相对移动、点动等级、停止、使能、位置计数归零和软件限位
- 位置单位为 `microstep`；名义步长与实际位移需要按执行器和负载标定

### OMEGA CNi8/CNi8D

- iSeries ASCII：9600、7-O-1，支持自动识别回显开关
- Modbus RTU：9600、8-N-1
- 读取温度和设定值、修改设定值
- iSeries 模式支持运行/待机和报警状态
- 临时设定值默认只写 RAM；可选择写入 EEPROM

## 安装

需要 Python 3.10 或更高版本。图形界面使用 Python 自带的 Tk，无需额外 GUI 框架。

```bash
git clone https://github.com/yuansui1023/G2DTC.git
cd G2DTC
python -m venv .venv
```

macOS/Linux：

```bash
source .venv/bin/activate
python -m pip install -e .
```

Windows：

```powershell
.venv\Scripts\activate
python -m pip install -e .
```

## 启动

```bash
python run.py
```

安装为可编辑包后，也可以直接运行：

```bash
g2dtc
```

第一次启动默认进入演示模式，10 个模拟电机和 1 个模拟温控已经分配到全部自由度。可以直接测试移动、点动、设定温度和输出开关。

## 配置真实硬件

1. 打开“设备分配”页。
2. 关闭“演示模式”。
3. 点击“硬件设备…”。
4. 添加 ESP300、PZC200 或 OMEGA CNi8。
5. 输入设备 ID、串口和通信参数。
6. 保存后，在每个自由度右侧下拉框中选择设备或“手动控制”。

常见串口写法：

- Windows：`COM4`
- macOS：`/dev/cu.usbserial-XXXX`
- Linux：`/dev/ttyUSB0`

默认配置保存在：

- Windows：`%APPDATA%\g2dtc\config.json`
- macOS/Linux：`~/.config/g2dtc/config.json`

也可以指定独立配置：

```bash
python run.py --config ./my_lab_config.json
```

[config.example.json](config.example.json) 展示了三个真实驱动同时存在时的完整配置结构。

## CNi8 前面板设置

iSeries ASCII 默认设置：

- `BAUD = 9600`
- `PRTY = ODD`
- `DATA = 7-BIT`
- `STOP = 1-BIT`
- `M.BUS = NO`
- `MODE = CMD`
- `ECHO = YES`（推荐）
- RS-232 使用 `STND = 232C`
- RS-485 使用 `STND = 485` 并设置地址

Modbus RTU：

- `M.BUS = YES`
- 9600、8 数据位、无校验、1 停止位
- 地址 1–199

## 安全说明

- 首次连接真实装置前，请先设置硬件限位和保守的速度/步长。
- “当前位置归零”只修改坐标，不会移动设备。
- CNi8 的“关闭输出”会进入 Standby，同时关闭输出和报警。
- 关闭 G2DTC 只会断开通信，不会自动关闭温控输出。
- 软件不能替代物理急停、限位开关和温度保护。

## 项目结构

```text
g2dtc/
├── app.py                  启动入口
├── config.py               自由度定义和配置持久化
├── registry.py             驱动实例注册与生命周期
├── ui.py                   控制台、分配页和硬件配置窗口
└── drivers/
    ├── esp300.py
    ├── pzc200.py
    ├── omega_cni8.py
    └── simulated.py
```

驱动通过很小的统一接口接入：

- 电机：`connect`、`disconnect`、`position`、`move_relative`、`jog`、`stop`
- 温控：`connect`、`disconnect`、`temperature`、`setpoint`、`set_setpoint`、`output`

以后增加新型号时，只需写新的后端驱动并在 `registry.py` 中注册，不需要改变自由度布局。

## 测试

```bash
python -m unittest discover -s tests -v
python -m compileall -q g2dtc run.py
```

测试不需要连接真实硬件，包含配置、分配、模拟设备、三个硬件协议和共享串口行为。
