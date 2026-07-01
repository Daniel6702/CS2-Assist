from __future__ import annotations

import select
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable

try:
    from evdev import InputDevice, UInput, ecodes, list_devices
except ImportError:  # pragma: no cover
    InputDevice = None
    UInput = None
    ecodes = None
    list_devices = None


EventCallback = Callable[[object, UInput], bool]
ErrorCallback = Callable[[Exception], None]
AttachCallback = Callable[[UInput], None]
DetachCallback = Callable[[], None]


@dataclass
class _Subscriber:
    token: int
    name: str
    callback: EventCallback
    exclusive_keys: set[int]
    on_error: ErrorCallback | None = None


def supported() -> bool:
    return InputDevice is not None and UInput is not None and ecodes is not None and list_devices is not None


def emit(ui: UInput, key: int, value: int, syn: bool = True) -> None:
    ui.write(ecodes.EV_KEY, key, value)
    if syn:
        ui.syn()


def find_keyboard(required_keys: set[int]) -> str:
    if not supported():
        raise RuntimeError("evdev/uinput is not available on this platform.")
    for path in list_devices():
        with suppress(PermissionError):
            dev = InputDevice(path)
            keys = set(dev.capabilities().get(ecodes.EV_KEY, []))
            if required_keys.issubset(keys):
                return path
    raise RuntimeError("Could not auto-detect a matching keyboard device.")


def create_virtual_keyboard(real: InputDevice, extra_keys: set[int], name: str) -> UInput:
    keys = set(real.capabilities(absinfo=False).get(ecodes.EV_KEY, []))
    keys.update(extra_keys)
    ui = UInput(
        {ecodes.EV_KEY: sorted(keys)},
        name=name,
        bustype=0x03,
        vendor=0x1234,
        product=0x5678,
        version=1,
    )
    time.sleep(0.2)
    return ui


class _SharedKeyboardHub:
    def __init__(self, device_path: str) -> None:
        self.device_path = device_path
        self.real = InputDevice(device_path)
        self.ui = create_virtual_keyboard(
            self.real,
            extra_keys=set(),
            name="cs2-unified-shared-keyboard",
        )
        self.real.grab()

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread_started = False
        self._next_token = 1
        self._subscribers: dict[int, _Subscriber] = {}
        self._claimed_keys: dict[int, str] = {}

    def subscribe(
        self,
        *,
        name: str,
        callback: EventCallback,
        exclusive_keys: set[int],
        on_error: ErrorCallback | None = None,
    ) -> int:
        with self._lock:
            collisions: list[tuple[int, str]] = []
            for key in exclusive_keys:
                owner = self._claimed_keys.get(key)
                if owner is not None:
                    collisions.append((key, owner))

            if collisions:
                parts = [f"key {key} already owned by {owner}" for key, owner in collisions]
                raise RuntimeError("Device key conflict: " + ", ".join(parts))

            token = self._next_token
            self._next_token += 1
            self._subscribers[token] = _Subscriber(
                token=token,
                name=name,
                callback=callback,
                exclusive_keys=set(exclusive_keys),
                on_error=on_error,
            )
            for key in exclusive_keys:
                self._claimed_keys[key] = name

            if not self._thread_started:
                self._thread.start()
                self._thread_started = True

            return token

    def unsubscribe(self, token: int) -> None:
        with self._lock:
            sub = self._subscribers.pop(token, None)
            if sub is None:
                return
            for key in sub.exclusive_keys:
                owner = self._claimed_keys.get(key)
                if owner == sub.name:
                    self._claimed_keys.pop(key, None)
            if not self._subscribers:
                self._stop.set()

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def close(self) -> None:
        self._stop.set()
        if self._thread_started and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.0)
        with suppress(Exception):
            self.real.ungrab()
        with suppress(Exception):
            self.ui.close()
        with suppress(Exception):
            self.real.close()

    def _reader_loop(self) -> None:
        try:
            while not self._stop.is_set():
                readable, _, _ = select.select([self.real], [], [], 0.01)
                if self._stop.is_set():
                    break
                if not readable:
                    continue
                try:
                    batch = self.real.read()
                except BlockingIOError:
                    continue

                for event in batch:
                    subscribers = self._snapshot_subscribers()
                    consumed = False

                    for sub in subscribers:
                        try:
                            if sub.callback(event, self.ui):
                                consumed = True
                        except Exception as exc:  # pragma: no cover
                            if sub.on_error is not None:
                                sub.on_error(exc)

                    if not consumed and event.type == ecodes.EV_KEY:
                        emit(self.ui, event.code, event.value)
        finally:
            self.close()

    def _snapshot_subscribers(self) -> list[_Subscriber]:
        with self._lock:
            return list(self._subscribers.values())


_registry_lock = threading.RLock()
_hubs: dict[str, _SharedKeyboardHub] = {}


class LinuxKeyboardRunner:
    def __init__(
        self,
        device_path: str,
        required_keys: set[int],
        component_name: str,
        exclusive_keys: set[int] | None,
        event_callback: EventCallback,
        stop_event: threading.Event,
        on_attach: AttachCallback | None = None,
        on_detach: DetachCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self.device_path = device_path
        self.required_keys = required_keys
        self.component_name = component_name
        self.exclusive_keys = set(exclusive_keys or set())
        self.event_callback = event_callback
        self.stop_event = stop_event
        self.on_attach = on_attach
        self.on_detach = on_detach
        self.on_error = on_error

    def run(self) -> None:
        if not supported():
            raise RuntimeError("Linux keyboard filtering is only available with evdev + uinput.")

        resolved_path = self.device_path or find_keyboard(self.required_keys)
        hub = self._acquire_hub(resolved_path)
        token = None
        attached = False
        try:
            token = hub.subscribe(
                name=self.component_name,
                callback=self.event_callback,
                exclusive_keys=self.exclusive_keys,
                on_error=self.on_error,
            )
            if self.on_attach is not None:
                self.on_attach(hub.ui)
                attached = True
            self.stop_event.wait()
        finally:
            if attached and self.on_detach is not None:
                with suppress(Exception):
                    self.on_detach()
            if token is not None:
                hub.unsubscribe(token)
            self._release_hub_if_unused(resolved_path, hub)

    def _acquire_hub(self, resolved_path: str) -> _SharedKeyboardHub:
        with _registry_lock:
            hub = _hubs.get(resolved_path)
            if hub is None:
                hub = _SharedKeyboardHub(resolved_path)
                _hubs[resolved_path] = hub
            return hub

    def _release_hub_if_unused(self, resolved_path: str, hub: _SharedKeyboardHub) -> None:
        should_close = False
        with _registry_lock:
            current = _hubs.get(resolved_path)
            if current is hub and hub.subscriber_count() == 0:
                _hubs.pop(resolved_path, None)
                should_close = True
        if should_close:
            hub.close()
