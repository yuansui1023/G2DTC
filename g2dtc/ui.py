"""Tkinter desktop UI for assignment and device control."""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

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


COLORS = {
    "background": "#F7F9FC",
    "surface": "#FFFFFF",
    "surface_alt": "#F0F4F8",
    "border": "#DCE3EC",
    "text": "#1D2939",
    "muted": "#667085",
    "accent": "#2563EB",
    "accent_dark": "#1D4ED8",
    "accent_soft": "#EAF2FF",
    "success": "#16835A",
    "warning": "#B7791F",
    "danger": "#B42318",
    "danger_soft": "#FEF3F2",
    "header": "#FFFFFF",
}


class ScrollFrame(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(
            self,
            background=COLORS["background"],
            highlightthickness=0,
        )
        self.inner = ttk.Frame(self.canvas, style="Page.TFrame")
        self.window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(
                self.window, width=event.width
            ),
        )
        self.canvas.bind_all("<MouseWheel>", self._mousewheel, add="+")

    def _mousewheel(self, event: tk.Event[Any]) -> None:
        if self.winfo_containing(event.x_root, event.y_root) is not None:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")


class SlotCard(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        app: "G2DTCApplication",
        slot: SlotDefinition,
        *,
        style: str = "Card.TFrame",
    ) -> None:
        width, height = app.module_sizes.get(slot.key, (340, 340))
        super().__init__(
            master,
            style=style,
            width=width,
            height=height,
            padding=(20, 18),
        )
        self.app = app
        self.slot = slot
        self._alive = True
        self._resize_callback: Callable[[], None] | None = None
        self._resize_origin = (0, 0, width, height)
        self.grid_propagate(False)

    def destroy(self) -> None:
        self._alive = False
        super().destroy()

    def submit(
        self,
        operation: Callable[[], Any],
        *,
        success: Callable[[Any], None] | None = None,
        message: str = "",
    ) -> Future[Any]:
        return self.app.submit(
            operation,
            success=success,
            owner=self,
            message=message,
        )

    def enable_resize(self, callback: Callable[[], None]) -> None:
        self._resize_callback = callback
        handle = ttk.Label(
            self,
            text="⋰",
            style="ResizeHandle.TLabel",
        )
        try:
            handle.configure(cursor="bottom_right_corner")
        except tk.TclError:
            pass
        handle.place(relx=1.0, rely=1.0, anchor="se", x=-3, y=-2)
        handle.bind("<ButtonPress-1>", self._start_resize)
        handle.bind("<B1-Motion>", self._drag_resize)
        handle.lift()

    def _start_resize(self, event: tk.Event[Any]) -> None:
        self._resize_origin = (
            event.x_root,
            event.y_root,
            int(self.cget("width")),
            int(self.cget("height")),
        )

    def _drag_resize(self, event: tk.Event[Any]) -> None:
        start_x, start_y, start_width, start_height = self._resize_origin
        width = min(720, max(340, start_width + event.x_root - start_x))
        height = min(720, max(340, start_height + event.y_root - start_y))
        self.configure(width=width, height=height)
        self.app.module_sizes[self.slot.key] = (width, height)
        if self._resize_callback is not None:
            self._resize_callback()


class DeviceSlotCard(SlotCard):
    poll_interval_ms = 900

    def __init__(
        self,
        master: tk.Misc,
        app: "G2DTCApplication",
        slot: SlotDefinition,
        driver: Any,
    ) -> None:
        super().__init__(master, app, slot)
        self.driver = driver
        self._polling = False
        self.connection_var = tk.StringVar(value="Disconnected")
        self.error_var = tk.StringVar(value="")

        header = ttk.Frame(self, style="Card.TFrame")
        header.pack(fill="x")
        ttk.Label(
            header,
            text=f"{slot.group_label} · {slot.label}",
            style="CardTitle.TLabel",
        ).pack(side="left")
        self.connect_button = ttk.Button(
            header,
            text="Connect",
            width=10,
            style="Small.TButton",
            command=self.toggle_connection,
        )
        self.connect_button.pack(side="right")
        kind_label = "Motor" if slot.kind == "motor" else "Temperature"
        ttk.Label(
            self,
            text=(
                f"{kind_label.upper()}  ·  "
                f"{app.registry.source(driver.device_id).upper()}"
            ),
            style="ModuleMeta.TLabel",
        ).pack(anchor="w", pady=(7, 0))
        details = ttk.Frame(self, style="Card.TFrame")
        details.pack(fill="x", pady=(5, 0))
        ttk.Label(
            details,
            text=str(getattr(driver, "display_name", driver.device_id)),
            style="DeviceName.TLabel",
        ).pack(side="left")
        ttk.Label(
            details,
            textvariable=self.connection_var,
            style="Status.TLabel",
        ).pack(side="right")

    def start_polling(self) -> None:
        self.after(120, self._poll)

    def toggle_connection(self) -> None:
        if getattr(self.driver, "is_connected", False):
            self.submit(
                self.driver.disconnect,
                success=lambda _value: self._connection_changed(False),
                message=f"Disconnect {self.driver.display_name}",
            )
        else:
            self.connection_var.set("Connecting...")
            self.submit(
                self.driver.connect,
                success=lambda _value: self._connection_changed(True),
                message=f"Connect {self.driver.display_name}",
            )

    def ensure_connected(self, operation: Callable[[], Any]) -> Any:
        if not getattr(self.driver, "is_connected", False):
            self.driver.connect()
        return operation()

    def show_error(self, error: BaseException) -> None:
        self.error_var.set(str(error))
        self.connection_var.set("Communication error")

    def _connection_changed(self, connected: bool) -> None:
        if not self._alive:
            return
        self.connection_var.set("Connected" if connected else "Disconnected")
        self.connect_button.configure(
            text="Disconnect" if connected else "Connect"
        )
        self.error_var.set("")
        self._poll()

    def _poll(self) -> None:
        if not self._alive:
            return
        if getattr(self.driver, "is_connected", False) and not self._polling:
            self._polling = True
            self.submit(
                self.read_status,
                success=self._poll_success,
            )
        self.after(self.poll_interval_ms, self._poll)

    def _poll_success(self, status: Any) -> None:
        self._polling = False
        if not self._alive:
            return
        self.connection_var.set("Connected")
        self.connect_button.configure(text="Disconnect")
        self.error_var.set("")
        self.apply_status(status)

    def read_status(self) -> Any:
        raise NotImplementedError

    def apply_status(self, status: Any) -> None:
        raise NotImplementedError


class MotorSlotCard(DeviceSlotCard):
    poll_interval_ms = 650

    def __init__(
        self,
        master: tk.Misc,
        app: "G2DTCApplication",
        slot: SlotDefinition,
        driver: Any,
    ) -> None:
        super().__init__(master, app, slot, driver)
        self.position_var = tk.StringVar(value="—")
        self.motion_var = tk.StringVar(value="Idle")
        self.step_var = tk.StringVar(
            value=f"{float(getattr(driver, 'default_step', 1.0)):g}"
        )
        self.jog_var = tk.StringVar(
            value=f"{float(getattr(driver, 'default_jog', 1.0)):g}"
        )
        self._enabled = False

        value_row = ttk.Frame(self, style="Card.TFrame")
        value_row.pack(fill="x", pady=(8, 6))
        ttk.Label(
            value_row, textvariable=self.position_var, style="Value.TLabel"
        ).pack(side="left")
        self.unit_label = ttk.Label(
            value_row,
            text=str(getattr(driver, "unit", "")),
            style="Unit.TLabel",
        )
        self.unit_label.pack(side="left", padx=(6, 0), pady=(7, 0))
        ttk.Label(
            value_row, textvariable=self.motion_var, style="RightStatus.TLabel"
        ).pack(side="right", pady=(7, 0))

        step_row = ttk.Frame(self, style="Card.TFrame")
        step_row.pack(fill="x", pady=(2, 5))
        ttk.Label(step_row, text="Step", style="Field.TLabel").pack(side="left")
        ttk.Entry(step_row, textvariable=self.step_var, width=10).pack(
            side="right"
        )
        move_row = ttk.Frame(self, style="Card.TFrame")
        move_row.pack(fill="x", pady=(0, 7))
        ttk.Button(
            move_row,
            text="Move −",
            command=lambda: self.move(-1),
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(
            move_row,
            text="Move +",
            command=lambda: self.move(1),
            style="Accent.TButton",
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

        jog_row = ttk.Frame(self, style="Card.TFrame")
        jog_row.pack(fill="x")
        left = ttk.Button(jog_row, text="◀ Jog", style="Small.TButton")
        left.pack(side="left")
        left.bind("<ButtonPress-1>", lambda _event: self.start_jog(-1))
        left.bind("<ButtonRelease-1>", lambda _event: self.stop())
        ttk.Entry(jog_row, textvariable=self.jog_var, width=7).pack(
            side="left", padx=5
        )
        right = ttk.Button(jog_row, text="Jog ▶", style="Small.TButton")
        right.pack(side="left")
        right.bind("<ButtonPress-1>", lambda _event: self.start_jog(1))
        right.bind("<ButtonRelease-1>", lambda _event: self.stop())
        ttk.Button(
            jog_row,
            text="Stop",
            style="Danger.TButton",
            command=self.stop,
        ).pack(side="right")

        utility = ttk.Frame(self, style="Card.TFrame")
        utility.pack(fill="x", pady=(8, 0))
        self.enable_button = ttk.Button(
            utility,
            text="Enable motor",
            style="Small.TButton",
            command=self.toggle_enable,
        )
        self.enable_button.pack(side="left")
        ttk.Button(
            utility,
            text="Zero position",
            style="Small.TButton",
            command=self.zero,
        ).pack(side="right")
        ttk.Label(
            self,
            textvariable=self.error_var,
            style="Error.TLabel",
            wraplength=290,
        ).pack(anchor="w", pady=(5, 0))
        self.start_polling()

    def read_status(self) -> dict[str, Any]:
        return {
            "position": self.driver.position(),
            "moving": bool(self.driver.is_moving()),
            "enabled": bool(self.driver.motor_enabled()),
            "unit": str(getattr(self.driver, "unit", "")),
        }

    def apply_status(self, status: dict[str, Any]) -> None:
        self.position_var.set(f"{float(status['position']):.6g}")
        self.motion_var.set("Moving" if status["moving"] else "Idle")
        self._enabled = bool(status["enabled"])
        self.enable_button.configure(
            text="Disable motor" if self._enabled else "Enable motor"
        )
        self.unit_label.configure(text=status["unit"])

    def move(self, direction: int) -> None:
        try:
            distance = abs(float(self.step_var.get())) * int(direction)
        except ValueError:
            messagebox.showerror(
                "Invalid input", "Step must be a number", parent=self
            )
            return

        def operation() -> None:
            def move_now() -> None:
                if hasattr(self.driver, "motor_enabled"):
                    if not self.driver.motor_enabled():
                        self.driver.enable(True)
                self.driver.move_relative(distance)

            return self.ensure_connected(move_now)

        self.submit(
            operation,
            success=lambda _value: self._poll(),
            message=f"Move {self.slot.key}",
        )

    def start_jog(self, direction: int) -> None:
        try:
            velocity = abs(float(self.jog_var.get()))
        except ValueError:
            messagebox.showerror(
                "Invalid input", "Jog speed must be a number", parent=self
            )
            return

        def operation() -> None:
            return self.ensure_connected(
                lambda: self.driver.jog(direction, velocity)
            )

        self.submit(operation, message=f"Jog {self.slot.key}")

    def stop(self) -> None:
        if not getattr(self.driver, "is_connected", False):
            return
        self.submit(
            self.driver.stop,
            success=lambda _value: self._poll(),
            message=f"Stop {self.slot.key}",
        )

    def toggle_enable(self) -> None:
        desired = not self._enabled
        self.submit(
            lambda: self.ensure_connected(lambda: self.driver.enable(desired)),
            success=lambda _value: self._poll(),
            message=("Enable" if desired else "Disable") + f" {self.slot.key}",
        )

    def zero(self) -> None:
        if not messagebox.askyesno(
            "Confirm zero",
            f"Set the current {self.slot.group_label} {self.slot.label} "
            "position to zero?\nThe device will not move.",
            parent=self,
        ):
            return
        self.submit(
            lambda: self.ensure_connected(self.driver.zero),
            success=lambda _value: self._poll(),
            message=f"Zero {self.slot.key}",
        )


class TemperatureSlotCard(DeviceSlotCard):
    poll_interval_ms = 1000

    def __init__(
        self,
        master: tk.Misc,
        app: "G2DTCApplication",
        slot: SlotDefinition,
        driver: Any,
    ) -> None:
        super().__init__(master, app, slot, driver)
        self.temperature_var = tk.StringVar(value="—")
        self.unit_var = tk.StringVar(value="")
        self.setpoint_var = tk.StringVar(
            value=f"{float(getattr(driver, 'default_setpoint', 25.0)):g}"
        )
        self.persist_var = tk.BooleanVar(value=False)
        self.output_var = tk.StringVar(value="Enable output")
        self._output_enabled = False
        self._setpoint_touched = False

        value_row = ttk.Frame(self, style="Card.TFrame")
        value_row.pack(fill="x", pady=(10, 8))
        ttk.Label(
            value_row,
            textvariable=self.temperature_var,
            style="TemperatureValue.TLabel",
        ).pack(side="left")
        ttk.Label(
            value_row,
            textvariable=self.unit_var,
            style="Unit.TLabel",
        ).pack(side="left", padx=(5, 0), pady=(9, 0))

        setpoint_row = ttk.Frame(self, style="Card.TFrame")
        setpoint_row.pack(fill="x", pady=(2, 6))
        ttk.Label(
            setpoint_row, text="Setpoint", style="Field.TLabel"
        ).pack(side="left")
        setpoint_entry = ttk.Entry(
            setpoint_row, textvariable=self.setpoint_var, width=10
        )
        setpoint_entry.pack(side="right")
        setpoint_entry.bind(
            "<FocusIn>", lambda _event: setattr(self, "_setpoint_touched", True)
        )

        ttk.Button(
            self,
            text="Apply setpoint",
            style="Accent.TButton",
            command=self.apply_setpoint,
        ).pack(fill="x", pady=(0, 5))
        ttk.Checkbutton(
            self,
            text="Persist to EEPROM",
            variable=self.persist_var,
            style="Card.TCheckbutton",
        ).pack(anchor="w")
        ttk.Button(
            self,
            textvariable=self.output_var,
            command=self.toggle_output,
        ).pack(fill="x", pady=(8, 0))
        ttk.Label(
            self,
            text="Disabling output puts the CNi8 in standby and disables alarms",
            style="Hint.TLabel",
            wraplength=290,
        ).pack(anchor="w", pady=(5, 0))
        ttk.Label(
            self,
            textvariable=self.error_var,
            style="Error.TLabel",
            wraplength=290,
        ).pack(anchor="w", pady=(4, 0))
        self.start_polling()

    def read_status(self) -> dict[str, Any]:
        return {
            "temperature": self.driver.temperature(),
            "setpoint": self.driver.setpoint(),
            "unit": str(getattr(self.driver, "unit", "")),
            "output": getattr(self.driver, "output_enabled", None),
        }

    def apply_status(self, status: dict[str, Any]) -> None:
        self.temperature_var.set(f"{float(status['temperature']):.4g}")
        self.unit_var.set(f"°{status['unit']}")
        if not self._setpoint_touched:
            self.setpoint_var.set(f"{float(status['setpoint']):g}")
        if status["output"] is not None:
            self._output_enabled = bool(status["output"])
            self.output_var.set(
                "Enter standby / Disable output"
                if self._output_enabled
                else "Leave standby / Enable output"
            )

    def apply_setpoint(self) -> None:
        try:
            value = float(self.setpoint_var.get())
        except ValueError:
            messagebox.showerror(
                "Invalid input", "Setpoint must be a number", parent=self
            )
            return
        persist = self.persist_var.get()

        def operation() -> float:
            return self.ensure_connected(
                lambda: self.driver.set_setpoint(value, persist=persist)
            )

        def success(accepted: float) -> None:
            self._setpoint_touched = False
            self.setpoint_var.set(f"{accepted:g}")
            self._poll()

        self.submit(
            operation,
            success=success,
            message=f"Set {self.slot.key} = {value:g}",
        )

    def toggle_output(self) -> None:
        desired = not self._output_enabled
        self.submit(
            lambda: self.ensure_connected(
                lambda: self.driver.output(desired)
            ),
            success=lambda _value: self._output_changed(desired),
            message=("Enable" if desired else "Disable")
            + " temperature output",
        )

    def _output_changed(self, enabled: bool) -> None:
        self._output_enabled = enabled
        self.output_var.set(
            "Enter standby / Disable output"
            if enabled
            else "Leave standby / Enable output"
        )
        self._poll()


class Dashboard(ttk.Frame):
    card_gap = 16

    def __init__(self, master: tk.Misc, app: "G2DTCApplication") -> None:
        super().__init__(master, style="Page.TFrame")
        self.app = app
        self.cards: list[SlotCard] = []
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True)
        self.canvas = scroll.canvas
        self.content = scroll.inner
        self._build()
        self.canvas.bind("<Configure>", self._relayout, add="+")

    def _build(self) -> None:
        heading = ttk.Frame(self.content, style="Page.TFrame")
        heading.pack(fill="x", padx=24, pady=(22, 10))
        ttk.Label(
            heading,
            text="Instrument Dashboard",
            style="PageTitle.TLabel",
        ).pack(anchor="w")

        self.card_grid = ttk.Frame(self.content, style="Page.TFrame")
        self.card_grid.pack(fill="x", padx=18, pady=(0, 24))
        self.card_grid.pack_propagate(False)
        self.cards = [
            card
            for slot in SLOTS
            if (card := self._make_card(self.card_grid, slot)) is not None
        ]

        if self.cards:
            self.after_idle(self._relayout)
            return

        empty = ttk.Frame(
            self.card_grid,
            style="EmptyState.TFrame",
            padding=(36, 54),
        )
        empty.pack(fill="x", padx=6, pady=6)
        ttk.Label(
            empty,
            text="No instruments assigned",
            style="EmptyStateTitle.TLabel",
        ).pack()
        self.card_grid.configure(height=150)

    def _relayout(self, event: tk.Event[Any] | None = None) -> None:
        if not self.cards:
            return
        width = event.width if event is not None else self.canvas.winfo_width()
        available = max(300, width - 36)
        x = 0
        y = 0
        row_height = 0
        for card in self.cards:
            card_width = int(card.cget("width"))
            card_height = int(card.cget("height"))
            if x and x + card_width > available:
                x = 0
                y += row_height + self.card_gap
                row_height = 0
            card.place(
                x=x,
                y=y,
                width=card_width,
                height=card_height,
            )
            x += card_width + self.card_gap
            row_height = max(row_height, card_height)
        self.card_grid.configure(height=max(1, y + row_height))

    def _make_card(
        self,
        master: tk.Misc,
        slot: SlotDefinition,
    ) -> SlotCard | None:
        assigned = self.app.config.assignments.get(slot.key)
        if not is_hardware_assignment(assigned):
            return None
        assert assigned is not None
        driver = self.app.registry.get(assigned)
        if driver is None:
            return None
        if slot.kind == "motor":
            card: SlotCard = MotorSlotCard(master, self.app, slot, driver)
        else:
            card = TemperatureSlotCard(master, self.app, slot, driver)
        card.enable_resize(self._relayout)
        return card


class AssignmentPage(ttk.Frame):
    MANUAL = "Manual"

    def __init__(self, master: tk.Misc, app: "G2DTCApplication") -> None:
        super().__init__(master, style="Page.TFrame")
        self.app = app
        self.variables: dict[str, tk.StringVar] = {}
        self.combos: dict[str, ttk.Combobox] = {}
        self.display_to_id: dict[str, str] = {
            self.MANUAL: MANUAL_ASSIGNMENT,
        }
        self.id_to_display: dict[str, str] = {
            MANUAL_ASSIGNMENT: self.MANUAL,
        }
        self._build_device_names()
        scroll = ScrollFrame(self)
        scroll.pack(fill="both", expand=True)
        self.content = scroll.inner
        self._build()

    def _build_device_names(self) -> None:
        for summary in self.app.registry.summaries():
            display = f"{summary.display_name}  [{summary.device_id}]"
            self.display_to_id[display] = summary.device_id
            self.id_to_display[summary.device_id] = display

    def _build(self) -> None:
        top = ttk.Frame(self.content, style="Page.TFrame")
        top.pack(fill="x", padx=28, pady=(24, 18))
        ttk.Label(
            top,
            text="Assignments",
            style="PageTitle.TLabel",
        ).pack(side="left")
        ttk.Button(
            top,
            text="Hardware",
            command=lambda: HardwareDialog(self.app),
        ).pack(side="right")
        demo_var = tk.BooleanVar(value=self.app.config.simulation)
        ttk.Checkbutton(
            top,
            text="Simulation mode",
            variable=demo_var,
            style="Page.TCheckbutton",
            command=lambda: self.app.set_simulation(demo_var.get()),
        ).pack(side="right", padx=12)

        groups: list[tuple[str, str]] = []
        for slot in SLOTS:
            group = (slot.group, slot.group_label)
            if group not in groups:
                groups.append(group)

        for group_key, group_label in groups:
            section = ttk.Frame(self.content, style="Page.TFrame")
            section.pack(fill="x", padx=28, pady=(0, 24))
            ttk.Label(
                section,
                text=group_label,
                style="SectionTitle.TLabel",
            ).pack(anchor="w", pady=(0, 8))

            for slot in (item for item in SLOTS if item.group == group_key):
                row = ttk.Frame(section, style="Page.TFrame")
                row.pack(fill="x", pady=5)
                row.columnconfigure(1, weight=1)
                label_area = ttk.Frame(row, style="Page.TFrame")
                label_area.grid(row=0, column=0, sticky="w", padx=(0, 22))
                ttk.Label(
                    label_area,
                    text=slot.label,
                    style="AssignmentName.TLabel",
                    width=12,
                ).pack(anchor="w")
                ttk.Label(
                    label_area,
                    text="Motor" if slot.kind == "motor" else "Temperature",
                    style="AssignmentKind.TLabel",
                ).pack(anchor="w")

                options = [self.MANUAL]
                options.extend(
                    self.id_to_display[driver.device_id]
                    for driver in self.app.registry.drivers(slot.kind)
                )
                assigned = self.app.config.assignments.get(
                    slot.key,
                    MANUAL_ASSIGNMENT,
                )
                selected = self.id_to_display.get(
                    assigned,
                    f"Missing device [{assigned}]",
                )
                variable = tk.StringVar(value=selected)
                combo = ttk.Combobox(
                    row,
                    textvariable=variable,
                    values=options,
                    state="readonly",
                )
                combo.grid(row=0, column=1, sticky="ew")
                combo.bind(
                    "<<ComboboxSelected>>",
                    lambda _event, key=slot.key: self._changed(key),
                )
                self.variables[slot.key] = variable
                self.combos[slot.key] = combo

        footer = ttk.Frame(self.content, style="Page.TFrame")
        footer.pack(fill="x", padx=28, pady=(0, 28))
        ttk.Button(
            footer,
            text="Open config",
            style="Small.TButton",
            command=self.app.open_config_folder,
        ).pack(side="right")
        ttk.Button(
            footer,
            text="Reload",
            style="Small.TButton",
            command=self.app.reload_from_disk,
        ).pack(side="right", padx=(0, 8))

    def _changed(self, slot_key: str) -> None:
        display = self.variables[slot_key].get()
        device_id = self.display_to_id.get(display)
        driver = self.app.registry.get(device_id) if device_id else None
        try:
            cleared = self.app.config.assign(
                slot_key,
                device_id,
                device_kind=getattr(driver, "kind", None),
            )
            self.app.save()
        except Exception as exc:
            messagebox.showerror("Assignment failed", str(exc), parent=self)
            self.app.rebuild_views(selected_tab=1)
            return
        if cleared:
            cleared_slot = SLOT_BY_KEY[cleared]
            self.app.set_status(
                f"{device_id} moved to {slot_key}; "
                f"{cleared_slot.group_label} {cleared_slot.label} "
                "was set to Manual"
            )
        else:
            self.app.set_status(f"Saved assignment for {slot_key}")
        self.app.rebuild_views(selected_tab=1)


class HardwareDialog(tk.Toplevel):
    TYPE_TO_KEY = {label: key for key, label in SUPPORTED_DEVICE_TYPES.items()}

    def __init__(self, app: "G2DTCApplication") -> None:
        super().__init__(app)
        self.app = app
        self.title("Hardware Devices")
        self.geometry("940x570")
        self.minsize(760, 500)
        self.resizable(True, True)
        self.transient(app)
        self.grab_set()
        self.selected_index: int | None = None
        self.variables = {
            "type": tk.StringVar(value=SUPPORTED_DEVICE_TYPES["esp300"]),
            "id": tk.StringVar(),
            "name": tk.StringVar(),
            "port": tk.StringVar(),
            "address": tk.StringVar(value="0"),
            "protocol": tk.StringVar(value="iseries"),
            "timeout": tk.StringVar(value="1.0"),
            "flow": tk.StringVar(value="both"),
            "baudrate": tk.StringVar(value="9600"),
            "axes": tk.StringVar(value="1,2,3"),
            "enabled": tk.BooleanVar(value=True),
        }
        self._build()
        self._refresh_tree()

    def _build(self) -> None:
        outer = ttk.Frame(self, style="Page.TFrame", padding=16)
        outer.pack(fill="both", expand=True)
        left = ttk.Frame(outer, style="Card.TFrame", padding=10)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ttk.Frame(outer, style="Card.TFrame", padding=14)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.tree = ttk.Treeview(
            left,
            columns=("type", "name", "port"),
            show="headings",
            height=17,
        )
        for column, text, width in (
            ("type", "Type", 100),
            ("name", "Name / ID", 190),
            ("port", "Serial port", 150),
        ):
            self.tree.heading(column, text=text)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        toolbar = ttk.Frame(left, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(10, 0))
        ttk.Button(
            toolbar, text="New device", command=self._new
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Delete",
            style="Danger.TButton",
            command=self._delete,
        ).pack(side="right")

        ttk.Label(right, text="Device settings", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        fields = (
            ("Device type", "type"),
            ("Device ID", "id"),
            ("Display name", "name"),
            ("Serial port", "port"),
            ("Address", "address"),
            ("Protocol", "protocol"),
            ("Baud rate", "baudrate"),
            ("Timeout (seconds)", "timeout"),
            ("PZC flow control", "flow"),
            ("ESP300 axes", "axes"),
        )
        for row, (label, key) in enumerate(fields, 1):
            ttk.Label(right, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=5
            )
            if key == "type":
                type_combo = ttk.Combobox(
                    right,
                    textvariable=self.variables[key],
                    values=list(self.TYPE_TO_KEY),
                    state="readonly",
                )
                type_combo.bind("<<ComboboxSelected>>", self._type_changed)
                widget: tk.Widget = type_combo
            elif key == "protocol":
                widget = ttk.Combobox(
                    right,
                    textvariable=self.variables[key],
                    values=("iseries", "modbus"),
                    state="readonly",
                )
            elif key == "flow":
                widget = ttk.Combobox(
                    right,
                    textvariable=self.variables[key],
                    values=("both", "xonxoff", "rtscts", "none"),
                    state="readonly",
                )
            else:
                widget = ttk.Entry(right, textvariable=self.variables[key])
            widget.grid(row=row, column=1, sticky="ew", pady=5)
        right.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            right,
            text="Enable this device",
            variable=self.variables["enabled"],
            style="Card.TCheckbutton",
        ).grid(row=11, column=1, sticky="w", pady=(8, 4))
        ttk.Label(
            right,
            text=(
                "ESP300 axis IDs use the format <ID>.axis1-3.\n"
                "Leave the CNi8 address blank for RS-232; "
                "use 1-199 for RS-485 or Modbus."
            ),
            style="Hint.TLabel",
        ).grid(row=12, column=0, columnspan=2, sticky="w", pady=(8, 12))
        ttk.Button(
            right,
            text="Save device and reload",
            style="Accent.TButton",
            command=self._save,
        ).grid(row=13, column=0, columnspan=2, sticky="ew")

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(self.app.config.devices):
            label = SUPPORTED_DEVICE_TYPES.get(item["type"], item["type"])
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    label.split(" ")[1] if " " in label else label,
                    item.get("name", item["id"]),
                    item.get("port", ""),
                ),
            )

    def _selected(self, _event: tk.Event[Any]) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected_index = int(selection[0])
        item = self.app.config.devices[self.selected_index]
        self.variables["type"].set(
            SUPPORTED_DEVICE_TYPES.get(item["type"], item["type"])
        )
        for key in (
            "id",
            "name",
            "port",
            "address",
            "protocol",
            "timeout",
            "flow",
            "baudrate",
        ):
            value = item.get(key, "")
            self.variables[key].set("" if value is None else str(value))
        self.variables["axes"].set(
            ",".join(str(axis) for axis in item.get("axes", [1, 2, 3]))
        )
        self.variables["enabled"].set(bool(item.get("enabled", True)))

    def _new(self) -> None:
        self.selected_index = None
        self.tree.selection_remove(self.tree.selection())
        defaults = {
            "type": SUPPORTED_DEVICE_TYPES["esp300"],
            "id": "",
            "name": "",
            "port": "",
            "address": "0",
            "protocol": "iseries",
            "timeout": "1.0",
            "flow": "both",
            "baudrate": "9600",
            "axes": "1,2,3",
        }
        for key, value in defaults.items():
            self.variables[key].set(value)
        self.variables["enabled"].set(True)

    def _type_changed(self, _event: tk.Event[Any]) -> None:
        device_type = self.TYPE_TO_KEY.get(self.variables["type"].get())
        address = self.variables["address"].get().strip()
        if device_type == "omega_cni8" and address == "0":
            self.variables["address"].set("")
        elif device_type == "pzc200" and not address:
            self.variables["address"].set("0")

    def _save(self) -> None:
        try:
            item = self._form_item()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc), parent=self)
            return
        devices = [dict(device) for device in self.app.config.devices]
        old_id: str | None = None
        old_type: str | None = None
        if self.selected_index is None:
            if any(device["id"] == item["id"] for device in devices):
                messagebox.showerror(
                    "Invalid settings", "Device ID already exists", parent=self
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
                messagebox.showerror(
                    "Invalid settings", "Device ID already exists", parent=self
                )
                return
            devices[self.selected_index] = item
        self.app.replace_devices(
            devices,
            renamed_from=old_id,
            renamed_to=item["id"],
            old_type=old_type,
            new_type=item["type"],
        )
        self.destroy()

    def _form_item(self) -> dict[str, Any]:
        device_type = self.TYPE_TO_KEY.get(self.variables["type"].get())
        if not device_type:
            raise ValueError("Select a device type")
        device_id = self.variables["id"].get().strip()
        port = self.variables["port"].get().strip()
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
            "name": self.variables["name"].get().strip() or device_id,
            "port": port,
            "timeout": float(self.variables["timeout"].get()),
            "enabled": self.variables["enabled"].get(),
        }
        if item["timeout"] <= 0:
            raise ValueError("Timeout must be greater than zero")
        if device_type == "esp300":
            axes = {
                int(part.strip())
                for part in self.variables["axes"].get().split(",")
                if part.strip()
            }
            if not axes or not axes.issubset({1, 2, 3}):
                raise ValueError(
                    "ESP300 axes must be 1, 2, or 3; for example, 1,2,3"
                )
            item.update({"axes": sorted(axes), "rtscts": True})
        elif device_type == "pzc200":
            address = int(self.variables["address"].get())
            if not 0 <= address <= 255:
                raise ValueError("PZC200 address must be between 0 and 255")
            item.update(
                {
                    "address": address,
                    "flow": self.variables["flow"].get(),
                }
            )
        else:
            protocol = self.variables["protocol"].get()
            address_text = self.variables["address"].get().strip()
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
                    "baudrate": int(self.variables["baudrate"].get()),
                }
            )
        return item

    def _delete(self) -> None:
        if self.selected_index is None:
            return
        item = self.app.config.devices[self.selected_index]
        if not messagebox.askyesno(
            "Delete device",
            f"Delete {item.get('name', item['id'])}?\n"
            "Related degrees of freedom will switch to Manual.",
            parent=self,
        ):
            return
        devices = [dict(device) for device in self.app.config.devices]
        devices.pop(self.selected_index)
        self.app.replace_devices(
            devices,
            removed_id=item["id"],
            old_type=item["type"],
        )
        self.destroy()


def re_identifier(value: str) -> bool:
    return bool(value) and all(
        character.isalnum() or character in "._-" for character in value
    )


class G2DTCApplication(tk.Tk):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.config = load_config(config_path)
        self.executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="g2dtc"
        )
        self.status_var = tk.StringVar(value="Ready")
        self._closing = False
        self.commit_sha = current_commit_sha()
        self.module_sizes: dict[str, tuple[int, int]] = {}
        self.registry = DeviceRegistry(self.config, log_callback=self._device_log)

        self.title("G2DTC · General 2D Material Transfer Controller")
        self.geometry("1440x900")
        self.minsize(900, 640)
        self.resizable(True, True)
        self.configure(background=COLORS["background"])
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.stop_all_motors())
        self._configure_styles()
        self._build_shell()
        self.save()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Helvetica Neue", 12))
        style.configure(
            "TButton",
            foreground=COLORS["text"],
            background=COLORS["surface_alt"],
            borderwidth=0,
            padding=(11, 8),
        )
        style.map(
            "TButton",
            background=[("active", "#E7EDF5")],
        )
        style.configure(
            "TEntry",
            fieldbackground=COLORS["surface_alt"],
            foreground=COLORS["text"],
            borderwidth=0,
            padding=7,
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["surface_alt"],
            background=COLORS["surface_alt"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["muted"],
            borderwidth=0,
            padding=6,
        )
        style.configure(
            "TNotebook",
            background=COLORS["background"],
            borderwidth=0,
            tabmargins=(18, 10, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=COLORS["surface_alt"],
            foreground=COLORS["muted"],
            borderwidth=0,
            padding=(18, 8),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["surface"])],
            foreground=[("selected", COLORS["accent"])],
        )
        style.configure("Page.TFrame", background=COLORS["background"])
        style.configure(
            "Header.TFrame",
            background=COLORS["header"],
        )
        style.configure(
            "HeaderTitle.TLabel",
            background=COLORS["header"],
            foreground=COLORS["text"],
            font=("Helvetica Neue", 30, "bold"),
        )
        style.configure(
            "VersionLink.TLabel",
            background=COLORS["header"],
            foreground=COLORS["accent"],
            font=("Helvetica Neue", 9),
        )
        style.configure(
            "Card.TFrame",
            background=COLORS["surface"],
            relief="flat",
            borderwidth=0,
        )
        style.configure(
            "CardTitle.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=("Helvetica Neue", 20, "bold"),
        )
        style.configure(
            "ModuleMeta.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["accent"],
            font=("Helvetica Neue", 10, "bold"),
        )
        style.configure(
            "DeviceName.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Helvetica Neue", 11),
        )
        style.configure(
            "Status.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["success"],
            font=("Helvetica Neue", 10, "bold"),
        )
        style.configure(
            "Value.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=("Menlo", 30, "bold"),
        )
        style.configure(
            "TemperatureValue.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["accent"],
            font=("Menlo", 32, "bold"),
        )
        style.configure(
            "Unit.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Helvetica Neue", 12),
        )
        style.configure(
            "RightStatus.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Helvetica Neue", 10),
        )
        style.configure(
            "Field.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "Hint.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Helvetica Neue", 10),
        )
        style.configure(
            "Error.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["danger"],
            font=("Helvetica Neue", 10),
        )
        style.configure(
            "PageTitle.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Helvetica Neue", 30, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "EmptyState.TFrame",
            background=COLORS["surface"],
            relief="flat",
            borderwidth=0,
        )
        style.configure(
            "EmptyStateTitle.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=("Helvetica Neue", 22, "bold"),
        )
        style.configure(
            "Page.TCheckbutton",
            background=COLORS["background"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Card.TCheckbutton",
            background=COLORS["surface"],
            foreground=COLORS["text"],
        )
        style.configure(
            "SectionTitle.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Helvetica Neue", 22, "bold"),
        )
        style.configure(
            "AssignmentName.TLabel",
            background=COLORS["background"],
            foreground=COLORS["text"],
            font=("Helvetica Neue", 16, "bold"),
        )
        style.configure(
            "AssignmentKind.TLabel",
            background=COLORS["background"],
            foreground=COLORS["muted"],
            font=("Helvetica Neue", 10),
        )
        style.configure(
            "ResizeHandle.TLabel",
            background=COLORS["surface"],
            foreground="#CBD5E1",
            font=("Helvetica Neue", 12),
        )
        style.configure(
            "Accent.TButton",
            foreground="white",
            background=COLORS["accent"],
            borderwidth=0,
            padding=(10, 7),
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLORS["accent_dark"])],
        )
        style.configure(
            "Danger.TButton",
            foreground=COLORS["danger"],
            background=COLORS["danger_soft"],
            borderwidth=0,
            padding=(8, 5),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#FEE4E2")],
        )
        style.configure(
            "Small.TButton",
            padding=(9, 6),
            font=("Helvetica Neue", 10),
        )
        style.configure(
            "Header.TButton",
            foreground=COLORS["accent"],
            background=COLORS["accent_soft"],
            borderwidth=0,
            padding=(12, 7),
        )
        style.map(
            "Header.TButton",
            background=[("active", "#DCEAFF")],
        )

    def _build_shell(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(20, 13))
        header.pack(fill="x")
        title_area = ttk.Frame(header, style="Header.TFrame")
        title_area.pack(side="left")
        title_row = ttk.Frame(title_area, style="Header.TFrame")
        title_row.pack(anchor="w")
        ttk.Label(
            title_row,
            text="G2DTC",
            style="HeaderTitle.TLabel",
        ).pack(side="left")
        version_label = ttk.Label(
            title_row,
            text=f"{self.commit_sha}  ·  {REPOSITORY_URL}",
            style="VersionLink.TLabel",
            cursor="hand2",
        )
        version_label.pack(side="left", padx=(14, 0), pady=(7, 0))
        version_label.bind(
            "<Button-1>",
            lambda _event: webbrowser.open_new_tab(
                source_url(self.commit_sha)
            ),
        )
        ttk.Button(
            header,
            text="Connect assigned devices",
            style="Header.TButton",
            command=self.connect_assigned,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            header,
            text="Stop all motors  Esc",
            style="Danger.TButton",
            command=self.stop_all_motors,
        ).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.rebuild_views()

        status = ttk.Frame(self, style="Page.TFrame", padding=(12, 5))
        status.pack(fill="x")
        ttk.Label(
            status, textvariable=self.status_var, style="Muted.TLabel"
        ).pack(side="left")

    def rebuild_views(self, *, selected_tab: int | None = None) -> None:
        if selected_tab is None and self.notebook.tabs():
            selected_tab = self.notebook.index(self.notebook.select())
        for tab in self.notebook.tabs():
            page = self.nametowidget(tab)
            self.notebook.forget(tab)
            page.destroy()
        dashboard = Dashboard(self.notebook, self)
        assignments = AssignmentPage(self.notebook, self)
        self.notebook.add(dashboard, text="  Dashboard  ")
        self.notebook.add(assignments, text="  Assignments  ")
        if selected_tab is not None:
            self.notebook.select(min(selected_tab, 1))

    def submit(
        self,
        operation: Callable[[], Any],
        *,
        success: Callable[[Any], None] | None = None,
        owner: SlotCard | None = None,
        message: str = "",
    ) -> Future[Any]:
        future = self.executor.submit(operation)
        if message:
            self.set_status(message + "…")

        def poll() -> None:
            if self._closing:
                return
            if not future.done():
                self.after(35, poll)
                return
            try:
                value = future.result()
            except Exception as exc:
                if owner is not None and owner._alive:
                    if isinstance(owner, DeviceSlotCard):
                        owner._polling = False
                        owner.show_error(exc)
                if message:
                    self.set_status(f"{message} failed: {exc}")
                    messagebox.showerror(
                        "Device operation failed", str(exc), parent=self
                    )
                return
            if owner is not None and not owner._alive:
                return
            if success:
                success(value)
            if message:
                self.set_status(message + " complete")

        self.after(0, poll)
        return future

    def connect_assigned(self) -> None:
        drivers = self.registry.assigned_drivers(self.config.assignments.values())

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
                messagebox.showwarning(
                    "Some devices did not connect",
                    "\n".join(errors),
                    parent=self,
                )
            self.set_status(f"Connected {connected} assigned devices")

        self.submit(
            operation, success=success, message="Connect assigned devices"
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
                messagebox.showwarning(
                    "Some motors did not stop", "\n".join(errors), parent=self
                )
            self.set_status(
                "Stop command sent to all connected motors"
                if not errors
                else "Motor stop completed with errors"
            )

        self.submit(operation, success=success, message="Stop all motors")

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
                    if old_type == "esp300" and assigned and assigned.startswith(
                        old_id + ".axis"
                    ):
                        replacement = renamed_to + assigned[len(old_id) :]
                    elif assigned == old_id:
                        replacement = renamed_to
                if assigned == old_id or (
                    old_type == "esp300"
                    and isinstance(assigned, str)
                    and assigned.startswith(old_id + ".axis")
                ):
                    self.config.assignments[slot_key] = replacement
        self.config.devices = devices
        self.save()
        self._rebuild_registry(selected_tab=1)

    def _rebuild_registry(self, *, selected_tab: int) -> None:
        try:
            new_registry = DeviceRegistry(
                self.config, log_callback=self._device_log
            )
        except Exception as exc:
            messagebox.showerror(
                "Device configuration error", str(exc), parent=self
            )
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
            messagebox.showerror(
                "Configuration load failed", str(exc), parent=self
            )
            return
        self._rebuild_registry(selected_tab=1)

    def save(self) -> None:
        try:
            save_config(self.config, self.config_path)
        except Exception as exc:
            messagebox.showerror(
                "Configuration save failed", str(exc), parent=self
            )

    def open_config_folder(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(self.config_path.parent)])
            elif os.name == "nt":
                os.startfile(self.config_path.parent)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(self.config_path.parent)])
        except Exception as exc:
            messagebox.showerror("Cannot open folder", str(exc), parent=self)

    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _device_log(self, message: str) -> None:
        print(message)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.registry.shutdown()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()
