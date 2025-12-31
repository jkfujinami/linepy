"""
Device Configurations for LINEPY

Based on linejs (latest) and CHRLINE device configurations.
"""

from typing import Literal, Optional, NamedTuple


# Device type literals
Device = Literal[
    "DESKTOPWIN",
    "DESKTOPMAC",
    "CHROMEOS",
    "ANDROID",
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
    "DESKTOPWIN": "9.2.0.3403",
    "DESKTOPMAC": "9.2.0.3402",
    "CHROMEOS": "3.0.3",
    "ANDROID": "13.4.1",
    "IOS": "15.19.0",
    "IOSIPAD": "15.19.0",
    "WATCHOS": "15.19.0",
    "WEAROS": "13.4.1",
}

# Devices that support token v3
TOKEN_V3_SUPPORT = ["DESKTOPWIN", "DESKTOPMAC", "IOS", "ANDROID"]


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
    elif device == "CHROMEOS":
        app_version = version or DEFAULT_VERSIONS["CHROMEOS"]
        system_name = "Chrome_OS"
        system_version = "1"
    elif device == "ANDROID":
        app_version = version or DEFAULT_VERSIONS["ANDROID"]
        system_name = "Android OS"
    elif device == "IOS":
        app_version = version or DEFAULT_VERSIONS["IOS"]
        system_name = "iOS"
    elif device == "IOSIPAD":
        app_version = version or DEFAULT_VERSIONS["IOSIPAD"]
        system_name = "iOS"
    elif device == "WATCHOS":
        app_version = version or DEFAULT_VERSIONS["WATCHOS"]
        system_name = "Watch OS"
    elif device == "WEAROS":
        app_version = version or DEFAULT_VERSIONS["WEAROS"]
        system_name = "Wear OS"
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
