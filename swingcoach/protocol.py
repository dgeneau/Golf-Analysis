"""Movella DOT BLE protocol definitions and payload parsing.

UUIDs and byte layouts verified against Movella's official reference
implementation (github.com/xsens/xsens_dot_server, bleHandler.js) and the
Movella DOT BLE Services Specification.

All multi-byte values are little-endian. Units:
  - timestamp: microseconds (uint32, rolls over every ~71.6 min)
  - euler angles: degrees
  - free acceleration: m/s^2, gravity removed, expressed in the EARTH frame
  - angular velocity (gyro): deg/s, body frame
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Optional


def dot_uuid(short: int) -> str:
    """Expand a 16-bit Movella DOT short UUID into the full 128-bit form."""
    return f"1517{short:04x}-4947-11e9-8646-d663bd873d93"


# --- Services / characteristics -------------------------------------------
# Configuration service
UUID_DEVICE_INFO = dot_uuid(0x1001)          # read
UUID_DEVICE_CONTROL = dot_uuid(0x1002)       # read / write (output rate, etc.)
UUID_DEVICE_REPORT = dot_uuid(0x1004)        # notify

# Measurement service
UUID_MEASUREMENT_CONTROL = dot_uuid(0x2001)  # read / write
UUID_LONG_PAYLOAD = dot_uuid(0x2002)         # notify (payloads > 40 bytes)
UUID_MEDIUM_PAYLOAD = dot_uuid(0x2003)       # notify (payloads <= 40 bytes)
UUID_SHORT_PAYLOAD = dot_uuid(0x2004)        # notify (payloads <= 20 bytes)
UUID_ORIENTATION_RESET = dot_uuid(0x2006)    # write: heading reset control

# Battery service
UUID_BATTERY = dot_uuid(0x3001)              # read / notify: [level, charging]

# --- Measurement control commands ------------------------------------------
# Write to UUID_MEASUREMENT_CONTROL: bytes([TYPE, ACTION, PAYLOAD_MODE])
MEAS_TYPE_MEASUREMENT = 0x01
MEAS_ACTION_START = 0x01
MEAS_ACTION_STOP = 0x00

# Heading reset (write to UUID_ORIENTATION_RESET)
HEADING_RESET = bytes([0x01, 0x00])   # zero heading at current orientation
HEADING_REVERT = bytes([0x07, 0x00])  # revert to default heading

# --- Payload modes ----------------------------------------------------------
PAYLOAD_EXTENDED_QUATERNION = 2    # ts + quat + freeAcc + status (36 B, medium)
PAYLOAD_COMPLETE_EULER = 16        # ts + euler + freeAcc        (28 B, medium)
PAYLOAD_RATE_QUANTITIES_MAG = 20   # ts + acc + gyr + mag        (34 B, medium)
PAYLOAD_CUSTOM_MODE_1 = 22         # ts + euler + freeAcc + gyr  (40 B, medium)
PAYLOAD_CUSTOM_MODE_3 = 24         # ts + quat + gyr             (32 B, medium)

TIMESTAMP_ROLLOVER_US = 2 ** 32


@dataclass
class Sample:
    """One IMU sample, in SI-ish units.

    t: seconds since stream start (monotonic, rollover-corrected)
    roll/pitch/yaw: degrees (earth frame orientation of the sensor)
    ax/ay/az: free acceleration, m/s^2, EARTH frame (gravity removed)
    gx/gy/gz: angular velocity, deg/s, body frame
    """
    t: float
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    az: float = 0.0
    gx: float = 0.0
    gy: float = 0.0
    gz: float = 0.0

    @property
    def gyro_mag(self) -> float:
        return (self.gx ** 2 + self.gy ** 2 + self.gz ** 2) ** 0.5

    @property
    def acc_mag(self) -> float:
        return (self.ax ** 2 + self.ay ** 2 + self.az ** 2) ** 0.5

    def to_csv_row(self) -> str:
        return (f"{self.t:.6f},{self.roll:.3f},{self.pitch:.3f},{self.yaw:.3f},"
                f"{self.ax:.4f},{self.ay:.4f},{self.az:.4f},"
                f"{self.gx:.3f},{self.gy:.3f},{self.gz:.3f}")

    CSV_HEADER = "t,roll,pitch,yaw,ax,ay,az,gx,gy,gz"


class TimestampUnwrapper:
    """Convert the DOT's uint32 microsecond timestamp into monotonic seconds."""

    def __init__(self) -> None:
        self._first: Optional[int] = None
        self._last_raw: Optional[int] = None
        self._offset_us = 0

    def to_seconds(self, raw_us: int) -> float:
        if self._first is None:
            self._first = raw_us
            self._last_raw = raw_us
            return 0.0
        if raw_us < self._last_raw:  # rollover
            self._offset_us += TIMESTAMP_ROLLOVER_US
        self._last_raw = raw_us
        return (raw_us + self._offset_us - self._first) / 1e6


def parse_custom_mode_1(data: bytes, unwrap: TimestampUnwrapper) -> Sample:
    """Payload 22: timestamp(4) euler(12) freeAcc(12) gyr(12) = 40 bytes."""
    ts = struct.unpack_from("<I", data, 0)[0]
    vals = struct.unpack_from("<9f", data, 4)
    return Sample(
        t=unwrap.to_seconds(ts),
        roll=vals[0], pitch=vals[1], yaw=vals[2],
        ax=vals[3], ay=vals[4], az=vals[5],
        gx=vals[6], gy=vals[7], gz=vals[8],
    )


def parse_complete_euler(data: bytes, unwrap: TimestampUnwrapper) -> Sample:
    """Payload 16: timestamp(4) euler(12) freeAcc(12) = 28 bytes."""
    ts = struct.unpack_from("<I", data, 0)[0]
    vals = struct.unpack_from("<6f", data, 4)
    return Sample(
        t=unwrap.to_seconds(ts),
        roll=vals[0], pitch=vals[1], yaw=vals[2],
        ax=vals[3], ay=vals[4], az=vals[5],
    )


PARSERS = {
    PAYLOAD_CUSTOM_MODE_1: parse_custom_mode_1,
    PAYLOAD_COMPLETE_EULER: parse_complete_euler,
}
