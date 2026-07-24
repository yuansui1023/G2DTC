# G2DTC

General 2D Material Transfer Controller is a desktop application for operating a
two-dimensional material transfer system.

G2DTC separates the logical degrees of freedom in the experiment from the
connected hardware. Transfer Arm, Stage, and Microscope always keep the same
layout, while every degree of freedom can be assigned to hardware or set to
manual control.

## Features

- Transfer Arm: X, Y, and Z
- Stage: X, Y, Z, Rz, and temperature
- Microscope: X, Y, and Z
- 10 motion degrees of freedom and 1 temperature-control channel
- Flexible device assignment without duplicate use of a physical device
- A compact dashboard module appears only when hardware is assigned
- Manual mode never sends hardware commands or creates a dashboard module
- Borderless instrument modules with individual drag resizing and automatic
  reflow
- Large module typography with the device type and controlled degree of freedom
  shown on every module
- Modern flat tabs, grouped assignment panels, and hardware settings
- Freely resizable main and hardware windows with horizontal and vertical
  scrollbars
- Product name, runtime Git SHA, and GitHub source link in the title area
- Assignments and hardware settings are saved automatically
- Serial operations run in worker threads and do not block the window
- `Esc` or the header button stops all connected motors
- A complete simulation mode for testing the interface without hardware

## Supported Hardware

### Newport ESP300

- Each of the three axes is exposed as an independently assignable motor
- All axes share one serial port and one communication lock
- Relative and absolute movement, jogging, stop, enable, coordinate zeroing,
  homing, and software limits
- Automatic detection of native controller units and maximum velocity

### Newport NanoPZ PZC200

- Each controller address is exposed as one assignable motor
- Relative movement, jog levels, stop, enable, position-count zeroing, and
  software limits
- Position is reported in `microstep`; actual travel must be calibrated for the
  actuator and load

### OMEGA CNi8/CNi8D

- iSeries ASCII at 9600 baud, 7-O-1, with automatic echo detection
- Modbus RTU at 9600 baud, 8-N-1
- Temperature and setpoint reads, plus setpoint updates
- Run/standby control and alarm status in iSeries mode
- Temporary setpoint changes write to RAM by default, with optional EEPROM
  persistence

## Installation

Python 3.10 or newer is required. The desktop interface is built with PySide6;
installing the package also installs the required Qt runtime.

```bash
git clone https://github.com/yuansui1023/G2DTC.git
cd G2DTC
python -m venv .venv
```

On macOS or Linux:

```bash
source .venv/bin/activate
python -m pip install -e .
```

On Windows:

```powershell
.venv\Scripts\activate
python -m pip install -e .
```

## Running the Application

```bash
python run.py
```

After installing the editable package, the command-line entry point is also
available:

```bash
g2dtc
```

The first launch uses simulation mode so simulated devices are immediately
available in the **Assignments** tab. All degrees of freedom start in
**Manual** mode, and the Dashboard remains empty until hardware is selected.

## Configuring Real Hardware

1. Open the **Assignments** tab.
2. Clear **Simulation**.
3. Select **Hardware**.
4. Add an ESP300, PZC200, or OMEGA CNi8 controller.
5. Enter the device ID, serial port, and communication settings.
6. Save the device, then assign it or choose **Manual** for each degree of
   freedom.

Common serial-port formats:

- Windows: `COM4`
- macOS: `/dev/cu.usbserial-XXXX`
- Linux: `/dev/ttyUSB0`

The default configuration location is:

- Windows: `%APPDATA%\g2dtc\config.json`
- macOS/Linux: `~/.config/g2dtc/config.json`

An independent configuration file can also be selected:

```bash
python run.py --config ./my_lab_config.json
```

[config.example.json](config.example.json) shows a complete configuration with
all three real hardware drivers.

## CNi8 Front-Panel Settings

Recommended iSeries ASCII settings:

- `BAUD = 9600`
- `PRTY = ODD`
- `DATA = 7-BIT`
- `STOP = 1-BIT`
- `M.BUS = NO`
- `MODE = CMD`
- `ECHO = YES`
- For RS-232, use `STND = 232C`
- For RS-485, use `STND = 485` and configure the controller address

Modbus RTU settings:

- `M.BUS = YES`
- 9600 baud, 8 data bits, no parity, 1 stop bit
- Address 1-199

## Safety

- Before connecting real hardware, configure hardware limits and conservative
  speeds and step sizes.
- **Zero position** changes only the coordinate value; it does not move the
  device.
- Disabling the CNi8 output enters standby and disables both output and alarms.
- Closing G2DTC disconnects communication but does not automatically disable the
  temperature-control output.
- Software cannot replace a physical emergency stop, limit switches, or
  over-temperature protection.

## Project Structure

```text
g2dtc/
|-- app.py                  Application entry point
|-- config.py               Slot definitions and configuration persistence
|-- registry.py             Driver registration and lifecycle management
|-- ui.py                   Dashboard, assignments, and hardware settings
`-- drivers/
    |-- esp300.py
    |-- pzc200.py
    |-- omega_cni8.py
    `-- simulated.py
```

Drivers use small shared interfaces:

- Motor: `connect`, `disconnect`, `position`, `move_relative`, `jog`, and `stop`
- Temperature: `connect`, `disconnect`, `temperature`, `setpoint`,
  `set_setpoint`, and `output`

To support another device model, add a backend driver and register it in
`registry.py`. The logical degree-of-freedom layout does not need to change.

## Testing

```bash
python -m unittest discover -s tests -v
python -m compileall -q g2dtc run.py
```

Tests do not require physical hardware. They cover configuration, assignment,
simulated devices, all three hardware protocols, shared serial-port behavior,
and the English-only repository policy.
