"""PySide6 desktop interface for assignment and device control."""

from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QCursor,
    QDesktopServices,
    QMouseEvent,
    QPainter,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from .config import (
    MANUAL_ASSIGNMENT,
    SLOTS,
    SLOT_BY_KEY,
    AppConfig,
    SlotDefinition,
    is_hardware_assignment,
    load_config,
    save_config,
)
from .registry import DeviceRegistry, SUPPORTED_DEVICE_TYPES
from .version import REPOSITORY_URL, current_commit_sha, source_url


APP_STYLESHEET = """
* {
    color: #182230;
    font-family: "Inter", "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 14px;
}
QMainWindow, QDialog, QWidget#appRoot, QWidget#page, QWidget#scrollBody {
    background: #F6F7F9;
}
QWidget#header, QWidget#statusBar {
    background: #FFFFFF;
}
QLabel#appTitle {
    font-size: 34px;
    font-weight: 700;
}
QLabel#appMeta {
    color: #667085;
    font-size: 15px;
}
QLabel#appVersion {
    color: #2864DC;
    font-size: 15px;
}
QLabel#pageTitle {
    font-size: 30px;
    font-weight: 700;
}
QLabel#groupTitle {
    font-size: 19px;
    font-weight: 650;
}
QLabel#cardTitle {
    font-size: 21px;
    font-weight: 700;
}
QLabel#deviceName, QLabel#muted, QLabel#hint, QLabel#statusText {
    color: #667085;
}
QLabel#statusText {
    font-size: 12px;
}
QLabel#kindBadge {
    color: #245BD6;
    background: #EBF2FF;
    border-radius: 9px;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: 700;
}
QLabel#value {
    font-size: 34px;
    font-weight: 700;
}
QLabel#unit {
    color: #667085;
    font-size: 15px;
}
QFrame#card, QFrame#section {
    background: #FFFFFF;
    border: 1px solid #EAECF0;
    border-radius: 18px;
}
QPushButton {
    background: #EEF1F5;
    border: 0;
    border-radius: 10px;
    min-height: 38px;
    padding: 0 15px;
    font-weight: 600;
}
QPushButton:hover {
    background: #E4E8EE;
}
QPushButton:pressed {
    background: #D9DFE7;
}
QPushButton[role="primary"] {
    color: #FFFFFF;
    background: #2864DC;
}
QPushButton[role="primary"]:hover {
    background: #1F56C7;
}
QPushButton[role="soft"] {
    color: #245BD6;
    background: #EBF2FF;
}
QPushButton[role="danger"] {
    color: #B42318;
    background: #FEECEB;
}
QPushButton[role="nav"] {
    color: #667085;
    background: transparent;
    border-radius: 10px;
    min-height: 42px;
    padding: 0 22px;
    font-size: 15px;
}
QPushButton[role="nav"]:hover {
    color: #182230;
    background: #EEF1F5;
}
QPushButton[role="nav"]:checked {
    color: #245BD6;
    background: #E8F0FF;
}
QPushButton:disabled {
    color: #98A2B3;
    background: #F2F4F7;
}
QLineEdit, QComboBox, QDoubleSpinBox {
    background: #F1F3F6;
    border: 1px solid transparent;
    border-radius: 10px;
    min-height: 40px;
    padding: 0 12px;
    selection-background-color: #2864DC;
}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover {
    background: #ECEFF3;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
    background: #FFFFFF;
    border: 1px solid #7AA2F7;
}
QComboBox {
    padding-right: 34px;
}
QComboBox::drop-down {
    border: 0;
    width: 36px;
}
QComboBox::down-arrow {
    image: none;
}
QLabel#comboArrow {
    color: #667085;
    background: transparent;
    font-size: 16px;
    font-weight: 700;
}
QComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #EAECF0;
    border-radius: 10px;
    padding: 6px;
    outline: 0;
    selection-background-color: #E8F0FF;
    selection-color: #182230;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 0;
    border: 0;
}
QCheckBox {
    spacing: 9px;
}
QListWidget {
    background: transparent;
    border: 0;
    outline: 0;
    padding: 0;
}
QListWidget::item {
    border-radius: 10px;
    min-height: 48px;
    padding: 4px 10px;
}
QListWidget::item:hover {
    background: #F1F3F6;
}
QListWidget::item:selected {
    color: #245BD6;
    background: #E8F0FF;
}
QScrollArea {
    border: 0;
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #C7CFDA;
    border-radius: 4px;
    min-height: 36px;
    min-width: 36px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #AEB8C5;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
"""


class ModernComboBox(QComboBox):
    """A flat selector with a clear, lightweight disclosure mark."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.arrow = QLabel("⌄", self)
        self.arrow.setObjectName("comboArrow")
        self.arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.arrow.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.arrow.setStyleSheet(
            "color: #667085; background: transparent; "
            "font-size: 16px; font-weight: 700;"
        )
        self.arrow.resize(24, 24)

    def resizeEvent(self, event: Any) -> None:
        self.arrow.move(
            self.width() - self.arrow.width() - 8,
            max(0, (self.height() - self.arrow.height()) // 2 - 2),
        )
        super().resizeEvent(event)


class ToggleSwitch(QCheckBox):
    """A compact switch that keeps standard checkbox behavior."""

    track_width = 42
    track_height = 24
    text_gap = 10

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(
            self.track_width + self.text_gap + text_width + 4,
            max(30, self.fontMetrics().height() + 6),
        )

    def paintEvent(self, _: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        top = (self.height() - self.track_height) / 2
        track = QRectF(0, top, self.track_width, self.track_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            QColor("#2864DC") if self.isChecked() else QColor("#C7CFDA")
        )
        painter.drawRoundedRect(
            track,
            self.track_height / 2,
            self.track_height / 2,
        )
        diameter = self.track_height - 6
        knob_x = (
            self.track_width - diameter - 3
            if self.isChecked()
            else 3
        )
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(knob_x, top + 3, diameter, diameter))
        painter.setPen(QColor("#182230"))
        text_rect = QRectF(
            self.track_width + self.text_gap,
            0,
            max(0, self.width() - self.track_width - self.text_gap),
            self.height(),
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )


class FlowLayout(QLayout):
    """Wrap fixed-size widgets across the available width."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        margin: int = 0,
        spacing: int = 18,
    ) -> None:
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items: list[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def addWidget(self, widget: QWidget) -> None:
        self.addChildWidget(widget)
        self.addItem(QWidgetItem(widget))

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )

    def _arrange(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(
            margins.left(),
            margins.top(),
            -margins.right(),
            -margins.bottom(),
        )
        x = area.x()
        y = area.y()
        row_height = 0
        gap = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + gap
            if next_x - gap > area.right() and row_height > 0:
                x = area.x()
                y += row_height + gap
                next_x = x + hint.width() + gap
                row_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            row_height = max(row_height, hint.height())
        return y + row_height - rect.y() + margins.bottom()


class ScrollPage(QScrollArea):
    """A page with independently available horizontal and vertical scrolling."""

    def __init__(self, *, minimum_content_width: int = 720) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.body = QWidget()
        self.body.setObjectName("scrollBody")
        self.body.setMinimumWidth(minimum_content_width)
        self.setWidget(self.body)


class ResizableCard(QFrame):
    """A dashboard module resized by dragging its lower-right corner."""

    corner_size = 22

    def __init__(
        self,
        module_key: str,
        resize_callback: Callable[[str, QSize], None],
        initial_size: tuple[int, int],
    ) -> None:
        super().__init__()
        self.module_key = module_key
        self._resize_callback = resize_callback
        self._resizing = False
        self._drag_origin = QPoint()
        self._start_size = QSize()
        self.setObjectName("card")
        self.setMouseTracking(True)
        self.setMinimumSize(340, 330)
        self.setMaximumSize(720, 680)
        self.setFixedSize(*initial_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._drag_origin
            size = QSize(
                max(self.minimumWidth(), self._start_size.width() + delta.x()),
                max(self.minimumHeight(), self._start_size.height() + delta.y()),
            ).boundedTo(self.maximumSize())
            self.setFixedSize(size)
            self._resize_callback(self.module_key, size)
            return
        if self._in_resize_corner(event.position().toPoint()):
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._in_resize_corner(event.position().toPoint())
        ):
            self._resizing = True
            self._drag_origin = event.globalPosition().toPoint()
            self._start_size = self.size()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._resizing:
            self._resizing = False
            self._resize_callback(self.module_key, self.size())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event: Any) -> None:
        if not self._resizing:
            self.unsetCursor()
        super().leaveEvent(event)

    def _in_resize_corner(self, point: QPoint) -> bool:
        return (
            point.x() >= self.width() - self.corner_size
            and point.y() >= self.height() - self.corner_size
        )


class TaskBridge(QObject):
    completed = Signal(object, object, object, str)
    failed = Signal(object, object, str)


class DeviceCard(ResizableCard):
    """Shared dashboard module behavior for one assigned device."""

    def __init__(
        self,
        window: "G2DTCWindow",
        slot: SlotDefinition,
        driver: Any,
    ) -> None:
        initial_size = window.module_sizes.get(slot.key, (390, 440))
        super().__init__(slot.key, window.store_module_size, initial_size)
        self.window = window
        self.slot = slot
        self.driver = driver
        self.alive = True
        self.polling = False
        self._operation_active = False

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 22, 24, 22)
        self.layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel(f"{slot.group_label} · {slot.label}")
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        badge = QLabel(slot.kind.upper())
        badge.setObjectName("kindBadge")
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        self.layout.addLayout(header)

        self.device_name = QLabel(
            f"{driver.display_name}  ·  {window.registry.source(driver.device_id)}"
        )
        self.device_name.setObjectName("deviceName")
        self.device_name.setWordWrap(True)
        self.layout.addWidget(self.device_name)

        connection_row = QHBoxLayout()
        self.connection_status = QLabel("Disconnected")
        self.connection_status.setObjectName("muted")
        connection_row.addWidget(self.connection_status, 1)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setProperty("role", "soft")
        self.connect_button.clicked.connect(self.toggle_connection)
        connection_row.addWidget(self.connect_button)
        self.layout.addLayout(connection_row)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(700)
        self.poll_timer.timeout.connect(self.poll)
        if driver.is_connected:
            self._connection_changed(True)

    def dispose(self) -> None:
        self.alive = False
        self.poll_timer.stop()

    def toggle_connection(self) -> None:
        if self._operation_active:
            return
        if self.driver.is_connected:
            operation = self.driver.disconnect
            message = f"Disconnect {self.driver.display_name}"
        else:
            operation = self.driver.connect
            message = f"Connect {self.driver.display_name}"
        self._operation_active = True
        self.connect_button.setEnabled(False)

        def success(_: Any) -> None:
            self._operation_active = False
            self.connect_button.setEnabled(True)
            self._connection_changed(bool(self.driver.is_connected))

        self.window.submit(
            operation,
            success=success,
            owner=self,
            message=message,
        )

    def run_device_operation(
        self,
        operation: Callable[[], Any],
        *,
        success: Callable[[Any], None] | None = None,
        message: str,
    ) -> None:
        def connected_operation() -> Any:
            if not self.driver.is_connected:
                self.driver.connect()
            return operation()

        def completed(value: Any) -> None:
            self._connection_changed(True)
            if success:
                success(value)
            self.poll()

        self.window.submit(
            connected_operation,
            success=completed,
            owner=self,
            message=message,
        )

    def _connection_changed(self, connected: bool) -> None:
        self.connection_status.setText("Connected" if connected else "Disconnected")
        self.connect_button.setText("Disconnect" if connected else "Connect")
        if connected:
            self.poll_timer.start()
            self.poll()
        else:
            self.poll_timer.stop()
            self.polling = False

    def poll(self) -> None:
        if not self.alive or not self.driver.is_connected or self.polling:
            return
        self.polling = True

        def success(status: Any) -> None:
            self.polling = False
            self.apply_status(status)

        self.window.submit(
            self.read_status,
            success=success,
            owner=self,
        )

    def operation_failed(self, error: BaseException) -> None:
        self.polling = False
        self._operation_active = False
        self.connect_button.setEnabled(True)
        if not self.driver.is_connected:
            self._connection_changed(False)
        self.connection_status.setText("Error")
        self.window.set_status(str(error))

    def read_status(self) -> Any:
        raise NotImplementedError

    def apply_status(self, status: Any) -> None:
        raise NotImplementedError


class MotorCard(DeviceCard):
    def __init__(
        self,
        window: "G2DTCWindow",
        slot: SlotDefinition,
        driver: Any,
    ) -> None:
        super().__init__(window, slot, driver)

        value_row = QHBoxLayout()
        value_row.setSpacing(8)
        self.position_label = QLabel("—")
        self.position_label.setObjectName("value")
        value_row.addWidget(self.position_label)
        self.unit_label = QLabel(str(getattr(driver, "unit", "")))
        self.unit_label.setObjectName("unit")
        value_row.addWidget(
            self.unit_label,
            1,
            Qt.AlignmentFlag.AlignBottom,
        )
        self.layout.addLayout(value_row)

        self.motion_label = QLabel("Idle")
        self.motion_label.setObjectName("muted")
        self.layout.addWidget(self.motion_label)

        step_row = QHBoxLayout()
        step_label = QLabel("Step")
        step_label.setObjectName("muted")
        step_row.addWidget(step_label)
        self.step = QDoubleSpinBox()
        self.step.setDecimals(6)
        self.step.setRange(0.000001, 10_000_000)
        self.step.setValue(float(getattr(driver, "default_step", 0.1)))
        self.step.setSingleStep(max(self.step.value() / 10, 0.000001))
        step_row.addWidget(self.step, 1)
        self.layout.addLayout(step_row)

        move_row = QHBoxLayout()
        minus = QPushButton("Move −")
        plus = QPushButton("Move +")
        minus.clicked.connect(lambda: self.move(-1))
        plus.clicked.connect(lambda: self.move(1))
        move_row.addWidget(minus)
        move_row.addWidget(plus)
        self.layout.addLayout(move_row)

        jog_row = QHBoxLayout()
        jog_label = QLabel("Jog")
        jog_label.setObjectName("muted")
        jog_row.addWidget(jog_label)
        self.jog_speed = QDoubleSpinBox()
        self.jog_speed.setDecimals(6)
        self.jog_speed.setRange(0.000001, 10_000_000)
        self.jog_speed.setValue(float(getattr(driver, "default_jog", 0.5)))
        jog_row.addWidget(self.jog_speed, 1)
        self.layout.addLayout(jog_row)

        jog_buttons = QHBoxLayout()
        jog_minus = QPushButton("Hold −")
        jog_plus = QPushButton("Hold +")
        stop = QPushButton("Stop")
        stop.setProperty("role", "danger")
        jog_minus.pressed.connect(lambda: self.start_jog(-1))
        jog_minus.released.connect(self.stop)
        jog_plus.pressed.connect(lambda: self.start_jog(1))
        jog_plus.released.connect(self.stop)
        stop.clicked.connect(self.stop)
        jog_buttons.addWidget(jog_minus)
        jog_buttons.addWidget(jog_plus)
        jog_buttons.addWidget(stop)
        self.layout.addLayout(jog_buttons)

        utility_row = QHBoxLayout()
        self.enable_button = QPushButton("Disable")
        self.enable_button.clicked.connect(self.toggle_enable)
        zero_button = QPushButton("Set zero")
        zero_button.clicked.connect(self.zero)
        utility_row.addWidget(self.enable_button)
        utility_row.addWidget(zero_button)
        self.layout.addLayout(utility_row)
        self.layout.addStretch(1)

    def read_status(self) -> dict[str, Any]:
        return {
            "position": self.driver.position(),
            "moving": self.driver.is_moving(),
            "enabled": self.driver.motor_enabled(),
            "unit": getattr(self.driver, "unit", ""),
        }

    def apply_status(self, status: dict[str, Any]) -> None:
        self.position_label.setText(f"{status['position']:.6g}")
        self.unit_label.setText(str(status["unit"]))
        self.motion_label.setText("Moving" if status["moving"] else "Idle")
        self.enable_button.setText("Disable" if status["enabled"] else "Enable")

    def move(self, direction: int) -> None:
        distance = direction * self.step.value()
        self.run_device_operation(
            lambda: self.driver.move_relative(distance),
            message=f"Move {self.slot.group_label} {self.slot.label}",
        )

    def start_jog(self, direction: int) -> None:
        self.run_device_operation(
            lambda: self.driver.jog(direction, self.jog_speed.value()),
            message=f"Jog {self.slot.group_label} {self.slot.label}",
        )

    def stop(self) -> None:
        if not self.driver.is_connected:
            return
        self.window.submit(
            self.driver.stop,
            owner=self,
            success=lambda _: self.poll(),
            message=f"Stop {self.slot.group_label} {self.slot.label}",
        )

    def toggle_enable(self) -> None:
        enabled = self.enable_button.text() == "Enable"
        self.run_device_operation(
            lambda: self.driver.enable(enabled),
            message=(
                f"{'Enable' if enabled else 'Disable'} "
                f"{self.slot.group_label} {self.slot.label}"
            ),
        )

    def zero(self) -> None:
        answer = QMessageBox.question(
            self,
            "Set digital zero",
            f"Set the current {self.slot.group_label} "
            f"{self.slot.label} position to zero?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.run_device_operation(
            self.driver.zero,
            message=f"Set zero for {self.slot.group_label} {self.slot.label}",
        )


class TemperatureCard(DeviceCard):
    def __init__(
        self,
        window: "G2DTCWindow",
        slot: SlotDefinition,
        driver: Any,
    ) -> None:
        super().__init__(window, slot, driver)

        value_row = QHBoxLayout()
        self.temperature_label = QLabel("—")
        self.temperature_label.setObjectName("value")
        value_row.addWidget(self.temperature_label)
        self.unit_label = QLabel(str(getattr(driver, "unit", "C")))
        self.unit_label.setObjectName("unit")
        value_row.addWidget(
            self.unit_label,
            1,
            Qt.AlignmentFlag.AlignBottom,
        )
        self.layout.addLayout(value_row)

        setpoint_row = QHBoxLayout()
        setpoint_label = QLabel("Setpoint")
        setpoint_label.setObjectName("muted")
        setpoint_row.addWidget(setpoint_label)
        self.setpoint = QDoubleSpinBox()
        self.setpoint.setDecimals(3)
        self.setpoint.setRange(-1999, 9999)
        self.setpoint.setValue(
            float(getattr(driver, "default_setpoint", 25.0))
        )
        setpoint_row.addWidget(self.setpoint, 1)
        self.layout.addLayout(setpoint_row)

        self.persist = ToggleSwitch("Save setpoint to controller memory")
        self.layout.addWidget(self.persist)
        apply_button = QPushButton("Apply setpoint")
        apply_button.setProperty("role", "primary")
        apply_button.clicked.connect(self.apply_setpoint)
        self.layout.addWidget(apply_button)

        output_row = QHBoxLayout()
        self.output_label = QLabel("Output state unavailable")
        self.output_label.setObjectName("muted")
        output_row.addWidget(self.output_label, 1)
        self.output_button = QPushButton("Enable output")
        self.output_button.clicked.connect(self.toggle_output)
        output_row.addWidget(self.output_button)
        self.layout.addLayout(output_row)
        self.layout.addStretch(1)

    def read_status(self) -> dict[str, Any]:
        return {
            "temperature": self.driver.temperature(),
            "setpoint": self.driver.setpoint(),
            "unit": getattr(self.driver, "unit", "C"),
            "output": getattr(self.driver, "output_enabled", None),
        }

    def apply_status(self, status: dict[str, Any]) -> None:
        self.temperature_label.setText(f"{status['temperature']:.6g}")
        self.unit_label.setText(str(status["unit"]))
        if not self.setpoint.hasFocus():
            self.setpoint.setValue(float(status["setpoint"]))
        output = status["output"]
        if output is None:
            self.output_label.setText("Output state unavailable")
            self.output_button.setText("Enable output")
        else:
            self.output_label.setText("Output enabled" if output else "Output disabled")
            self.output_button.setText(
                "Disable output" if output else "Enable output"
            )

    def apply_setpoint(self) -> None:
        value = self.setpoint.value()
        persist = self.persist.isChecked()
        self.run_device_operation(
            lambda: self.driver.set_setpoint(value, persist=persist),
            message=f"Apply {self.slot.group_label} setpoint",
        )

    def toggle_output(self) -> None:
        enabled = self.output_button.text() == "Enable output"
        self.run_device_operation(
            lambda: self.driver.output(enabled),
            message=f"{'Enable' if enabled else 'Disable'} temperature output",
        )


class DashboardPage(ScrollPage):
    def __init__(self, window: "G2DTCWindow") -> None:
        super().__init__(minimum_content_width=620)
        self.window = window
        self.cards: list[DeviceCard] = []
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(28, 22, 28, 30)
        layout.setSpacing(20)

        self.card_host = QWidget()
        self.card_host.setObjectName("scrollBody")
        self.flow = FlowLayout(self.card_host, spacing=18)
        layout.addWidget(self.card_host, 1)

        for slot in SLOTS:
            device_id = window.config.assignments.get(
                slot.key,
                MANUAL_ASSIGNMENT,
            )
            if not is_hardware_assignment(device_id):
                continue
            driver = window.registry.get(device_id)
            if driver is None:
                continue
            card: DeviceCard
            if slot.kind == "motor":
                card = MotorCard(window, slot, driver)
            else:
                card = TemperatureCard(window, slot, driver)
            self.cards.append(card)
            self.flow.addWidget(card)

        if not self.cards:
            empty = QFrame()
            empty.setObjectName("section")
            empty.setMinimumHeight(180)
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(28, 28, 28, 28)
            empty_label = QLabel("No instruments assigned")
            empty_label.setObjectName("groupTitle")
            empty_hint = QLabel(
                "Choose a device for a degree of freedom in Assignments."
            )
            empty_hint.setObjectName("muted")
            empty_hint.setWordWrap(True)
            empty_layout.addStretch(1)
            empty_layout.addWidget(empty_label)
            empty_layout.addWidget(empty_hint)
            empty_layout.addStretch(1)
            self.flow.addWidget(empty)

    def dispose(self) -> None:
        for card in self.cards:
            card.dispose()


class AssignmentPage(ScrollPage):
    def __init__(self, window: "G2DTCWindow") -> None:
        super().__init__(minimum_content_width=760)
        self.window = window
        self._building = True
        self.combos: dict[str, QComboBox] = {}
        self.display_to_id: dict[str, str] = {"Manual": MANUAL_ASSIGNMENT}
        self.id_to_display: dict[str, str] = {MANUAL_ASSIGNMENT: "Manual"}

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(28, 22, 28, 30)
        layout.setSpacing(18)

        top = QHBoxLayout()
        top.addStretch(1)
        hardware = QPushButton("Hardware")
        hardware.setProperty("role", "soft")
        hardware.clicked.connect(window.open_hardware_dialog)
        top.addWidget(hardware)
        self.simulation = ToggleSwitch("Simulation")
        self.simulation.setChecked(window.config.simulation)
        self.simulation.toggled.connect(window.set_simulation)
        top.addWidget(self.simulation)
        layout.addLayout(top)

        self._build_names()
        groups: list[str] = []
        for slot in SLOTS:
            if slot.group not in groups:
                groups.append(slot.group)

        for group in groups:
            slots = [slot for slot in SLOTS if slot.group == group]
            section = QFrame()
            section.setObjectName("section")
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(22, 20, 22, 22)
            section_layout.setSpacing(12)
            group_title = QLabel(slots[0].group_label)
            group_title.setObjectName("groupTitle")
            section_layout.addWidget(group_title)
            for slot in slots:
                row = QHBoxLayout()
                row.setSpacing(18)
                label = QLabel(slot.label)
                label.setMinimumWidth(130)
                row.addWidget(label)
                kind = QLabel(slot.kind.upper())
                kind.setObjectName("kindBadge")
                row.addWidget(kind)
                combo = ModernComboBox()
                combo.setMinimumWidth(320)
                options = ["Manual"]
                for driver in window.registry.drivers(slot.kind):
                    options.append(self.id_to_display[driver.device_id])
                combo.addItems(options)
                assigned = window.config.assignments.get(
                    slot.key,
                    MANUAL_ASSIGNMENT,
                )
                combo.setCurrentText(
                    self.id_to_display.get(assigned, "Manual")
                )
                combo.currentTextChanged.connect(
                    lambda _text, key=slot.key: self.assignment_changed(key)
                )
                self.combos[slot.key] = combo
                row.addWidget(combo, 1)
                section_layout.addLayout(row)
            layout.addWidget(section)
        layout.addStretch(1)
        self._building = False

    def _build_names(self) -> None:
        used: set[str] = {"Manual"}
        for driver in self.window.registry.drivers():
            base = str(getattr(driver, "display_name", driver.device_id))
            display = base
            if display in used:
                display = f"{base} · {driver.device_id}"
            used.add(display)
            self.display_to_id[display] = driver.device_id
            self.id_to_display[driver.device_id] = display

    def assignment_changed(self, slot_key: str) -> None:
        if self._building:
            return
        combo = self.combos[slot_key]
        device_id = self.display_to_id.get(
            combo.currentText(),
            MANUAL_ASSIGNMENT,
        )
        driver = self.window.registry.get(device_id)
        try:
            cleared = self.window.config.assign(
                slot_key,
                device_id,
                device_kind=getattr(driver, "kind", None),
            )
            self.window.save()
        except Exception as exc:
            QMessageBox.critical(self, "Assignment failed", str(exc))
            self.window.rebuild_views(selected_tab=1)
            return
        if cleared:
            cleared_slot = SLOT_BY_KEY[cleared]
            self.window.set_status(
                f"{device_id} moved to {slot_key}; "
                f"{cleared_slot.group_label} {cleared_slot.label} "
                "was set to Manual"
            )
        else:
            self.window.set_status(f"Saved assignment for {slot_key}")
        self.window.rebuild_views(selected_tab=1)


class HardwareDialog(QDialog):
    TYPE_TO_KEY = {label: key for key, label in SUPPORTED_DEVICE_TYPES.items()}

    def __init__(self, window: "G2DTCWindow") -> None:
        super().__init__(window)
        self.window = window
        self.selected_index: int | None = None
        self.setWindowTitle("Hardware")
        self.resize(1040, 700)
        self.setMinimumSize(640, 480)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage(minimum_content_width=900)
        outer.addWidget(scroll)
        layout = QVBoxLayout(scroll.body)
        layout.setContentsMargins(28, 26, 28, 28)
        layout.setSpacing(18)
        title = QLabel("Hardware")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QFrame()
        left.setObjectName("section")
        left.setMinimumWidth(330)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(12)
        left_header = QHBoxLayout()
        left_title = QLabel("Devices")
        left_title.setObjectName("groupTitle")
        left_header.addWidget(left_title, 1)
        add_button = QPushButton("Add")
        add_button.setProperty("role", "soft")
        add_button.clicked.connect(self.new_device)
        left_header.addWidget(add_button)
        left_layout.addLayout(left_header)
        self.device_list = QListWidget()
        self.device_list.currentRowChanged.connect(self.select_device)
        left_layout.addWidget(self.device_list, 1)
        delete_button = QPushButton("Delete")
        delete_button.setProperty("role", "danger")
        delete_button.clicked.connect(self.delete_device)
        left_layout.addWidget(delete_button)
        columns.addWidget(left, 2)

        right = QFrame()
        right.setObjectName("section")
        right.setMinimumWidth(500)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(22, 20, 22, 22)
        right_layout.setSpacing(14)
        settings_title = QLabel("Settings")
        settings_title.setObjectName("groupTitle")
        right_layout.addWidget(settings_title)

        self.type_combo = ModernComboBox()
        self.type_combo.addItems(self.TYPE_TO_KEY)
        self.type_combo.currentTextChanged.connect(self.type_changed)
        self.id_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.port_edit = QLineEdit()
        self.address_edit = QLineEdit("0")
        self.protocol_combo = ModernComboBox()
        self.protocol_combo.addItems(("iseries", "modbus"))
        self.baudrate_edit = QLineEdit("9600")
        self.timeout_edit = QLineEdit("1.0")
        self.flow_combo = ModernComboBox()
        self.flow_combo.addItems(("both", "xonxoff", "rtscts", "none"))
        self.axes_edit = QLineEdit("1,2,3")

        form = QFormLayout()
        form.setHorizontalSpacing(22)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.addRow("Device type", self.type_combo)
        form.addRow("Device ID", self.id_edit)
        form.addRow("Display name", self.name_edit)
        form.addRow("Serial port", self.port_edit)
        form.addRow("Address", self.address_edit)
        form.addRow("Protocol", self.protocol_combo)
        form.addRow("Baud rate", self.baudrate_edit)
        form.addRow("Timeout (seconds)", self.timeout_edit)
        form.addRow("PZC flow control", self.flow_combo)
        form.addRow("ESP300 axes", self.axes_edit)
        right_layout.addLayout(form)
        self.enabled = ToggleSwitch("Enable this device")
        self.enabled.setChecked(True)
        right_layout.addWidget(self.enabled)
        hint = QLabel(
            "ESP300 axes become independent assignable devices while sharing "
            "one serial port. Leave the CNi8 address blank for RS-232."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)
        save_button = QPushButton("Save device")
        save_button.setProperty("role", "primary")
        save_button.clicked.connect(self.save_device)
        right_layout.addWidget(save_button)
        right_layout.addStretch(1)
        columns.addWidget(right, 3)
        layout.addLayout(columns, 1)
        self.refresh_list()

    def refresh_list(self) -> None:
        self.device_list.clear()
        for item in self.window.config.devices:
            label = SUPPORTED_DEVICE_TYPES.get(item["type"], item["type"])
            name = item.get("name", item["id"])
            list_item = QListWidgetItem(f"{name}\n{label}  ·  {item.get('port', '')}")
            self.device_list.addItem(list_item)

    def select_device(self, index: int) -> None:
        if index < 0 or index >= len(self.window.config.devices):
            return
        self.selected_index = index
        item = self.window.config.devices[index]
        self.type_combo.setCurrentText(
            SUPPORTED_DEVICE_TYPES.get(item["type"], item["type"])
        )
        self.id_edit.setText(str(item.get("id", "")))
        self.name_edit.setText(str(item.get("name", "")))
        self.port_edit.setText(str(item.get("port", "")))
        address = item.get("address")
        self.address_edit.setText("" if address is None else str(address))
        self.protocol_combo.setCurrentText(str(item.get("protocol", "iseries")))
        self.baudrate_edit.setText(str(item.get("baudrate", 9600)))
        self.timeout_edit.setText(str(item.get("timeout", 1.0)))
        self.flow_combo.setCurrentText(str(item.get("flow", "both")))
        self.axes_edit.setText(
            ",".join(str(axis) for axis in item.get("axes", [1, 2, 3]))
        )
        self.enabled.setChecked(bool(item.get("enabled", True)))

    def new_device(self) -> None:
        self.selected_index = None
        self.device_list.clearSelection()
        self.type_combo.setCurrentText(SUPPORTED_DEVICE_TYPES["esp300"])
        self.id_edit.clear()
        self.name_edit.clear()
        self.port_edit.clear()
        self.address_edit.setText("0")
        self.protocol_combo.setCurrentText("iseries")
        self.baudrate_edit.setText("9600")
        self.timeout_edit.setText("1.0")
        self.flow_combo.setCurrentText("both")
        self.axes_edit.setText("1,2,3")
        self.enabled.setChecked(True)

    def type_changed(self, _: str) -> None:
        device_type = self.TYPE_TO_KEY.get(self.type_combo.currentText())
        address = self.address_edit.text().strip()
        if device_type == "omega_cni8" and address == "0":
            self.address_edit.clear()
        elif device_type == "pzc200" and not address:
            self.address_edit.setText("0")

    def save_device(self) -> None:
        try:
            item = self.form_item()
        except (TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Invalid settings", str(exc))
            return
        devices = [dict(device) for device in self.window.config.devices]
        old_id: str | None = None
        old_type: str | None = None
        if self.selected_index is None:
            if any(device["id"] == item["id"] for device in devices):
                QMessageBox.critical(
                    self,
                    "Invalid settings",
                    "Device ID already exists",
                )
                return
            devices.append(item)
        else:
            old_id = devices[self.selected_index]["id"]
            old_type = devices[self.selected_index]["type"]
            if any(
                index != self.selected_index and device["id"] == item["id"]
                for index, device in enumerate(devices)
            ):
                QMessageBox.critical(
                    self,
                    "Invalid settings",
                    "Device ID already exists",
                )
                return
            devices[self.selected_index] = item
        self.window.replace_devices(
            devices,
            renamed_from=old_id,
            renamed_to=item["id"],
            old_type=old_type,
            new_type=item["type"],
        )
        self.accept()

    def form_item(self) -> dict[str, Any]:
        device_type = self.TYPE_TO_KEY.get(self.type_combo.currentText())
        if not device_type:
            raise ValueError("Select a device type")
        device_id = self.id_edit.text().strip()
        port = self.port_edit.text().strip()
        if not device_id or not re_identifier(device_id):
            raise ValueError(
                "Device ID may contain only letters, numbers, periods, "
                "hyphens, and underscores"
            )
        if not port:
            raise ValueError("Serial port is required")
        item: dict[str, Any] = {
            "type": device_type,
            "id": device_id,
            "name": self.name_edit.text().strip() or device_id,
            "port": port,
            "timeout": float(self.timeout_edit.text()),
            "enabled": self.enabled.isChecked(),
        }
        if item["timeout"] <= 0:
            raise ValueError("Timeout must be greater than zero")
        if device_type == "esp300":
            axes = {
                int(part.strip())
                for part in self.axes_edit.text().split(",")
                if part.strip()
            }
            if not axes or not axes.issubset({1, 2, 3}):
                raise ValueError(
                    "ESP300 axes must be 1, 2, or 3; for example, 1,2,3"
                )
            item.update({"axes": sorted(axes), "rtscts": True})
        elif device_type == "pzc200":
            address = int(self.address_edit.text())
            if not 0 <= address <= 255:
                raise ValueError("PZC200 address must be between 0 and 255")
            item.update(
                {
                    "address": address,
                    "flow": self.flow_combo.currentText(),
                }
            )
        else:
            protocol = self.protocol_combo.currentText()
            address_text = self.address_edit.text().strip()
            address = None if address_text == "" else int(address_text)
            if protocol == "modbus" and address is None:
                address = 1
            if protocol == "modbus" and not 1 <= int(address) <= 199:
                raise ValueError(
                    "CNi8 Modbus address must be between 1 and 199"
                )
            if address is not None and not 0 <= address <= 199:
                raise ValueError("CNi8 address must be between 0 and 199")
            item.update(
                {
                    "protocol": protocol,
                    "address": address,
                    "baudrate": int(self.baudrate_edit.text()),
                }
            )
        return item

    def delete_device(self) -> None:
        if self.selected_index is None:
            return
        item = self.window.config.devices[self.selected_index]
        answer = QMessageBox.question(
            self,
            "Delete device",
            f"Delete {item.get('name', item['id'])}?\n"
            "Related degrees of freedom will switch to Manual.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        devices = [dict(device) for device in self.window.config.devices]
        devices.pop(self.selected_index)
        self.window.replace_devices(
            devices,
            removed_id=item["id"],
            old_type=item["type"],
        )
        self.accept()


def re_identifier(value: str) -> bool:
    return bool(value) and all(
        character.isalnum() or character in "._-" for character in value
    )


class Navigation(QWidget):
    changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("header")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 10)
        layout.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, text in enumerate(("Dashboard", "Assignments")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("role", "nav")
            button.clicked.connect(
                lambda _checked=False, page=index: self.changed.emit(page)
            )
            self.group.addButton(button, index)
            layout.addWidget(button)
        layout.addStretch(1)
        first = self.group.button(0)
        if first is not None:
            first.setChecked(True)

    def set_current(self, index: int) -> None:
        button = self.group.button(index)
        if button is not None:
            button.setChecked(True)


class G2DTCWindow(QMainWindow):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.config: AppConfig = load_config(config_path)
        self.executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="g2dtc",
        )
        self._closing = False
        self.commit_sha = current_commit_sha()
        self.module_sizes: dict[str, tuple[int, int]] = {}
        self.registry = DeviceRegistry(
            self.config,
            log_callback=self._device_log,
        )
        self.task_bridge = TaskBridge()
        self.task_bridge.completed.connect(self._task_completed)
        self.task_bridge.failed.connect(self._task_failed)
        self.dashboard: DashboardPage | None = None

        self.setWindowTitle("G2DTC · General 2D Material Transfer Controller")
        self.resize(1440, 900)
        self.setMinimumSize(640, 480)
        self._build_shell()
        self.save()

    def _build_shell(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 18, 28, 10)
        header_layout.setSpacing(14)
        title_area = QVBoxLayout()
        title_area.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(20)
        title = QLabel("G2DTC")
        title.setObjectName("appTitle")
        title_row.addWidget(title)
        version = QLabel(
            f"<a href=\"{source_url(self.commit_sha)}\">"
            f"{self.commit_sha}  ·  {REPOSITORY_URL}</a>"
        )
        version.setObjectName("appVersion")
        version.setTextFormat(Qt.TextFormat.RichText)
        version.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        version.setOpenExternalLinks(True)
        title_row.addWidget(version)
        title_row.addStretch(1)
        title_area.addLayout(title_row)
        metadata = QLabel("General 2D Material Transfer Controller")
        metadata.setObjectName("appMeta")
        title_area.addWidget(metadata)
        header_layout.addLayout(title_area, 1)
        stop_button = QPushButton("Stop all  Esc")
        stop_button.setProperty("role", "danger")
        stop_button.clicked.connect(self.stop_all_motors)
        header_layout.addWidget(stop_button)
        connect_button = QPushButton("Connect assigned")
        connect_button.setProperty("role", "soft")
        connect_button.clicked.connect(self.connect_assigned)
        header_layout.addWidget(connect_button)
        outer.addWidget(header)

        self.navigation = Navigation()
        self.navigation.changed.connect(self.set_current_page)
        outer.addWidget(self.navigation)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        status_bar = QWidget()
        status_bar.setObjectName("statusBar")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(28, 6, 28, 7)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusText")
        status_layout.addWidget(self.status_label)
        outer.addWidget(status_bar)

        self.rebuild_views(selected_tab=0)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.stop_all_motors()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_current_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.navigation.set_current(index)

    def rebuild_views(self, *, selected_tab: int | None = None) -> None:
        if selected_tab is None:
            selected_tab = max(0, self.stack.currentIndex())
        if self.dashboard is not None:
            self.dashboard.dispose()
        while self.stack.count():
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()
        self.dashboard = DashboardPage(self)
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(AssignmentPage(self))
        self.set_current_page(min(selected_tab, 1))

    def store_module_size(self, module_key: str, size: QSize) -> None:
        self.module_sizes[module_key] = (size.width(), size.height())
        if self.dashboard is not None:
            self.dashboard.flow.invalidate()
            self.dashboard.card_host.updateGeometry()

    def submit(
        self,
        operation: Callable[[], Any],
        *,
        success: Callable[[Any], None] | None = None,
        owner: DeviceCard | None = None,
        message: str = "",
    ) -> Future[Any]:
        if message:
            self.set_status(message + "…")
        future = self.executor.submit(operation)

        def completed(task: Future[Any]) -> None:
            try:
                value = task.result()
            except Exception as exc:
                self.task_bridge.failed.emit(exc, owner, message)
                return
            self.task_bridge.completed.emit(value, success, owner, message)

        future.add_done_callback(completed)
        return future

    def _task_completed(
        self,
        value: Any,
        success: Callable[[Any], None] | None,
        owner: DeviceCard | None,
        message: str,
    ) -> None:
        if self._closing or (owner is not None and not owner.alive):
            return
        if success is not None:
            success(value)
        if message:
            self.set_status(message + " complete")

    def _task_failed(
        self,
        error: BaseException,
        owner: DeviceCard | None,
        message: str,
    ) -> None:
        if self._closing or (owner is not None and not owner.alive):
            return
        if owner is not None:
            owner.operation_failed(error)
        if message:
            self.set_status(f"{message} failed: {error}")
            QMessageBox.critical(self, "Device operation failed", str(error))

    def connect_assigned(self) -> None:
        drivers = self.registry.assigned_drivers(
            self.config.assignments.values()
        )

        def operation() -> tuple[int, list[str]]:
            connected = 0
            errors: list[str] = []
            for driver in drivers:
                try:
                    if not driver.is_connected:
                        driver.connect()
                    connected += 1
                except Exception as exc:
                    errors.append(f"{driver.display_name}: {exc}")
            return connected, errors

        def success(result: tuple[int, list[str]]) -> None:
            connected, errors = result
            self.rebuild_views(selected_tab=0)
            if errors:
                QMessageBox.warning(
                    self,
                    "Some devices did not connect",
                    "\n".join(errors),
                )
            self.set_status(f"Connected {connected} assigned devices")

        self.submit(
            operation,
            success=success,
            message="Connect assigned devices",
        )

    def stop_all_motors(self) -> None:
        motors = [
            driver
            for driver in self.registry.drivers("motor")
            if getattr(driver, "is_connected", False)
        ]

        def operation() -> list[str]:
            errors: list[str] = []
            for driver in motors:
                try:
                    driver.stop()
                except Exception as exc:
                    errors.append(f"{driver.display_name}: {exc}")
            return errors

        def success(errors: list[str]) -> None:
            if errors:
                QMessageBox.warning(
                    self,
                    "Some motors did not stop",
                    "\n".join(errors),
                )
            self.set_status(
                "Stop command sent to all connected motors"
                if not errors
                else "Motor stop completed with errors"
            )

        self.submit(
            operation,
            success=success,
            message="Stop all motors",
        )

    def set_simulation(self, enabled: bool) -> None:
        if self.config.simulation == bool(enabled):
            return
        self.config.simulation = bool(enabled)
        if not enabled:
            for key, value in list(self.config.assignments.items()):
                if isinstance(value, str) and value.startswith("sim."):
                    self.config.assignments[key] = MANUAL_ASSIGNMENT
        self.save()
        self._rebuild_registry(selected_tab=1)

    def replace_devices(
        self,
        devices: list[dict[str, Any]],
        *,
        renamed_from: str | None = None,
        renamed_to: str | None = None,
        removed_id: str | None = None,
        old_type: str | None = None,
        new_type: str | None = None,
    ) -> None:
        old_id = removed_id or renamed_from
        if old_id:
            for slot_key, assigned in list(self.config.assignments.items()):
                replacement = MANUAL_ASSIGNMENT
                if renamed_to and old_type == new_type:
                    if old_type == "esp300" and assigned.startswith(
                        old_id + ".axis"
                    ):
                        replacement = renamed_to + assigned[len(old_id) :]
                    elif assigned == old_id:
                        replacement = renamed_to
                if assigned == old_id or (
                    old_type == "esp300"
                    and assigned.startswith(old_id + ".axis")
                ):
                    self.config.assignments[slot_key] = replacement
        self.config.devices = devices
        self.save()
        self._rebuild_registry(selected_tab=1)

    def _rebuild_registry(self, *, selected_tab: int) -> None:
        try:
            new_registry = DeviceRegistry(
                self.config,
                log_callback=self._device_log,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Device configuration error", str(exc))
            self.set_status(f"Device configuration error: {exc}")
            return
        self.registry.shutdown()
        self.registry = new_registry
        self.rebuild_views(selected_tab=selected_tab)
        self.set_status(f"Loaded {len(self.registry)} available devices")

    def reload_from_disk(self) -> None:
        try:
            self.config = load_config(self.config_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Configuration load failed",
                str(exc),
            )
            return
        self._rebuild_registry(selected_tab=1)

    def save(self) -> None:
        try:
            save_config(self.config, self.config_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Configuration save failed",
                str(exc),
            )

    def open_hardware_dialog(self) -> None:
        HardwareDialog(self).exec()

    def open_config_folder(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.config_path.parent))
        )

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _device_log(self, message: str) -> None:
        print(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            event.accept()
            return
        self._closing = True
        if self.dashboard is not None:
            self.dashboard.dispose()
        self.registry.shutdown()
        self.executor.shutdown(wait=False, cancel_futures=True)
        event.accept()


class G2DTCApplication:
    """Compatibility wrapper retaining the original application entry point."""

    def __init__(self, config_path: Path) -> None:
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setApplicationName("G2DTC")
        self.qt_app.setStyle("Fusion")
        self.qt_app.setStyleSheet(APP_STYLESHEET)
        self.window = G2DTCWindow(config_path)

    def mainloop(self) -> int:
        self.window.show()
        return self.qt_app.exec()
