"""Async BLE client for the Movella DOT, built on bleak (works on macOS).

Typical use:

    async with DotClient.discover_and_connect() as dot:
        await dot.reset_heading()          # aim forearm down target line first
        await dot.start_streaming(on_sample=handle)
        ...
        await dot.stop_streaming()
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from bleak import BleakClient, BleakScanner

from . import protocol as p

log = logging.getLogger("swingcoach.ble")

DOT_NAMES = ("movella dot", "xsens dot")


async def find_dot(timeout: float = 10.0):
    """Scan for the first Movella/Xsens DOT advertising nearby."""
    log.info("Scanning for Movella DOT (%.0fs timeout)...", timeout)
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: (d.name or "").lower().startswith(DOT_NAMES),
        timeout=timeout,
    )
    return device


class DotClient:
    def __init__(self, client: BleakClient):
        self._client = client
        self._unwrap = p.TimestampUnwrapper()
        self._payload_mode: Optional[int] = None
        self._on_sample: Optional[Callable[[p.Sample], None]] = None

    # -- lifecycle -----------------------------------------------------------
    @classmethod
    async def discover_and_connect(cls, address: Optional[str] = None,
                                   timeout: float = 10.0) -> "DotClient":
        if address is None:
            device = await find_dot(timeout)
            if device is None:
                raise RuntimeError(
                    "No Movella DOT found. Is the sensor on (LED blinking) and "
                    "Bluetooth enabled? Also make sure no other app "
                    "(e.g. the Movella DOT app) is connected to it.")
            address = device
        client = BleakClient(address)
        await client.connect()
        log.info("Connected to %s", getattr(address, "name", address))
        return cls(client)

    async def __aenter__(self) -> "DotClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    async def disconnect(self) -> None:
        try:
            if self._payload_mode is not None:
                await self.stop_streaming()
        finally:
            if self._client.is_connected:
                await self._client.disconnect()
                log.info("Disconnected.")

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    # -- device info ---------------------------------------------------------
    async def battery(self) -> tuple[int, bool]:
        """Return (battery %, is_charging)."""
        data = await self._client.read_gatt_char(p.UUID_BATTERY)
        return data[0], bool(data[1])

    async def reset_heading(self) -> None:
        """Zero the heading at the current orientation.

        Do this at address with the sensor/forearm aimed down the target
        line, so yaw and swing-path directions are relative to the target.
        """
        await self._client.write_gatt_char(p.UUID_ORIENTATION_RESET,
                                           p.HEADING_RESET, response=True)
        log.info("Heading reset (target line = current heading).")

    # -- streaming -----------------------------------------------------------
    async def start_streaming(self, on_sample: Callable[[p.Sample], None],
                              payload_mode: int = p.PAYLOAD_CUSTOM_MODE_1) -> None:
        if payload_mode not in p.PARSERS:
            raise ValueError(f"Unsupported payload mode {payload_mode}")
        self._on_sample = on_sample
        self._payload_mode = payload_mode
        self._unwrap = p.TimestampUnwrapper()
        parser = p.PARSERS[payload_mode]

        def _notify(_char, data: bytearray) -> None:
            try:
                sample = parser(bytes(data), self._unwrap)
            except Exception:  # malformed packet: skip, don't kill the stream
                log.exception("Failed to parse payload: %s", data.hex())
                return
            if self._on_sample:
                self._on_sample(sample)

        await self._client.start_notify(p.UUID_MEDIUM_PAYLOAD, _notify)
        await self._client.write_gatt_char(
            p.UUID_MEASUREMENT_CONTROL,
            bytes([p.MEAS_TYPE_MEASUREMENT, p.MEAS_ACTION_START, payload_mode]),
            response=True)
        log.info("Streaming started (payload mode %d).", payload_mode)

    async def stop_streaming(self) -> None:
        if self._payload_mode is None:
            return
        mode, self._payload_mode = self._payload_mode, None
        try:
            await self._client.write_gatt_char(
                p.UUID_MEASUREMENT_CONTROL,
                bytes([p.MEAS_TYPE_MEASUREMENT, p.MEAS_ACTION_STOP, mode]),
                response=True)
            await self._client.stop_notify(p.UUID_MEDIUM_PAYLOAD)
        except Exception:
            log.debug("stop_streaming cleanup issue", exc_info=True)
        log.info("Streaming stopped.")


StatusCallback = Callable[..., None]  # (state: str, detail: str = "", battery: int|None = None)


async def stream_forever(on_sample: Callable[[p.Sample], None],
                         stop_event: asyncio.Event,
                         address: Optional[str] = None,
                         on_status: Optional[StatusCallback] = None) -> None:
    """Convenience loop: connect, reset heading, stream until stop_event.

    on_status reports the sensor lifecycle so a UI can show it:
      scanning -> connected -> ready -> disconnected (or error).
    """
    def st(state: str, detail: str = "", battery: Optional[int] = None) -> None:
        if on_status:
            try:
                on_status(state, detail, battery)
            except Exception:
                log.debug("status callback failed", exc_info=True)

    st("scanning", "looking for a Movella DOT…")
    try:
        dot = await DotClient.discover_and_connect(address)
    except Exception as e:
        st("error", str(e))
        raise
    try:
        st("connected", "setting up…")
        level, charging = await dot.battery()
        log.info("Battery: %d%%%s", level, " (charging)" if charging else "")
        st("connected", "calibrating — hold the sensor still for a second",
           battery=level)
        await dot.reset_heading()
        await dot.start_streaming(on_sample)
        st("ready", "streaming at 60 Hz", battery=level)
        await stop_event.wait()
    except Exception as e:
        st("error", str(e))
        raise
    finally:
        await dot.disconnect()
        st("disconnected", "sensor disconnected")
