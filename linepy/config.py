"""
Device Configurations for LINEPY

Based on linejs (latest) and CHRLINE device configurations.
"""

from typing import Literal, NamedTuple, Optional

# Device type literals
Device = Literal[
    "DESKTOPWIN",
    "DESKTOPMAC",
    "CHROMEOS",
    "ANDROID",
    "ANDROIDSECONDARY",
    "IOS",
    "IOSIPAD",
    "WATCHOS",
    "WEAROS",
]


class DeviceDetails(NamedTuple):
    """Device configuration details"""

    device: str
    app_version: str
    system_name: str
    system_version: str


# Default versions (from linejs - most up to date)
DEFAULT_VERSIONS = {
    "DESKTOPWIN": "9.7.0.3556",
    "DESKTOPMAC": "26.2.0",
    "CHROMEOS": "3.0.3",
    "ANDROID": "26.6.2",
    "ANDROIDSECONDARY": "26.6.2",
    "IOS": "26.7.2",
    "IOSIPAD": "26.7.2",
    "WATCHOS": "26.7.2",
    "WEAROS": "13.4.1",
}

# Devices that support token v3
TOKEN_V3_SUPPORT = ["DESKTOPWIN", "DESKTOPMAC", "IOS", "ANDROID", "ANDROIDSECONDARY"]

# Primary devices (should not refresh token if using extracted token)
PRIMARY_DEVICES = ["ANDROID", "IOS"]


# ---- MID types -------------------------------------------------------------
# LINE's MIDType enum. Every mid carries its type in the first character.
MID_TYPE_USER = 0
MID_TYPE_ROOM = 1
MID_TYPE_GROUP = 2
MID_TYPE_SQUARE = 3
MID_TYPE_SQUARE_CHAT = 4
MID_TYPE_SQUARE_MEMBER = 5
MID_TYPE_BOT = 6

MID_PREFIX_TYPES = {
    "u": MID_TYPE_USER,
    "r": MID_TYPE_ROOM,
    "c": MID_TYPE_GROUP,
    "s": MID_TYPE_SQUARE,
    "m": MID_TYPE_SQUARE_CHAT,
    "p": MID_TYPE_SQUARE_MEMBER,
    "v": MID_TYPE_BOT,
    "t": 7,
}


def get_mid_type(mid: Optional[str]) -> Optional[int]:
    """MIDType for a mid, or None when it is empty / has an unknown prefix."""
    if not mid:
        return None
    return MID_PREFIX_TYPES.get(mid[0])


def get_device_details(
    device: Device,
    version: Optional[str] = None,
) -> Optional[DeviceDetails]:
    """
    Get device configuration details.

    Args:
        device: Device type
        version: Optional custom app version

    Returns:
        DeviceDetails or None if device not supported
    """
    system_version = "12.1.4"

    if device == "DESKTOPWIN":
        app_version = version or DEFAULT_VERSIONS["DESKTOPWIN"]
        system_name = "WINDOWS"
        system_version = "10.0.0-NT-x64"
    elif device == "DESKTOPMAC":
        app_version = version or DEFAULT_VERSIONS["DESKTOPMAC"]
        system_name = "MAC"
        system_version = "13.0.0"
    elif device == "CHROMEOS":
        app_version = version or DEFAULT_VERSIONS["CHROMEOS"]
        system_name = "Chrome_OS"
        system_version = "1"
    elif device == "ANDROID":
        app_version = version or DEFAULT_VERSIONS["ANDROID"]
        system_name = "Android OS"
        system_version = "16"
    elif device == "ANDROIDSECONDARY":
        app_version = version or DEFAULT_VERSIONS["ANDROIDSECONDARY"]
        system_name = "Android OS"
        system_version = "16"
    elif device == "IOS":
        app_version = version or DEFAULT_VERSIONS["IOS"]
        system_name = "iOS"
        system_version = "18.0"
    elif device == "IOSIPAD":
        app_version = version or DEFAULT_VERSIONS["IOSIPAD"]
        system_name = "iOS"
        system_version = "18.0"
    elif device == "WATCHOS":
        app_version = version or DEFAULT_VERSIONS["WATCHOS"]
        system_name = "Watch OS"
        system_version = "11.0"
    elif device == "WEAROS":
        app_version = version or DEFAULT_VERSIONS["WEAROS"]
        system_name = "Wear OS"
        system_version = "3.0"
    else:
        return None

    return DeviceDetails(
        device=device,
        app_version=app_version,
        system_name=system_name,
        system_version=system_version,
    )


def is_v3_support(device: Device) -> bool:
    """Check if device supports token v3"""
    return device in TOKEN_V3_SUPPORT


def build_app_name(details: DeviceDetails) -> str:
    """Build x-line-application header value"""
    return f"{details.device}\t{details.app_version}\t{details.system_name}\t{details.system_version}"
