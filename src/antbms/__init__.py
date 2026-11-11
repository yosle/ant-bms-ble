"""ant-bms-ble — read-only BLE client and protocol decoder for ANT BMS.

The protocol spec lives in PROTOCOL.md at the repository root. The decoder
(`antbms.protocol`) is pure Python with no dependencies; BLE transport
(`bleak`) and the TUI (`rich`) are only imported by the CLI.
"""

from .protocol import (  # noqa: F401
    SERVICE_UUID,
    CHAR_UUID,
    READ_COMMANDS,
    DEFAULT_PASSWORD,
    SYSTEM_STATE,
    BATTERY_TYPE,
    DIS_MOS_STATE,
    CH_MOS_STATE,
    BALANCE_STATE,
    PROTECT_BITS,
    WARNING_BITS,
    crc16,
    build_read_request,
    build_auth_request,
    find_frames,
    frame_extra,
    raw_payload,
    decode_realtime,
    decode_old,
    decode_params,
    decode_chip_id,
    decode_info,
    decode_auth,
    decode_extra,
    decode_ascii,
)
from .params import PARAM_BLOCKS, PARAM_MAP, PARAM_META  # noqa: F401

__version__ = "0.1.0"
