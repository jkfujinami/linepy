#!/usr/bin/env python3
"""
Device-config tests validated against 本家 (linejs devices.ts).

The expected table below is transcribed directly from
resource/linejs/packages/linejs/base/core/utils/devices.ts.
"""

import pytest

from linepy.config import (
    DEFAULT_VERSIONS,
    TOKEN_V3_SUPPORT,
    build_app_name,
    get_device_details,
)

# device -> (appVersion, systemName, systemVersion) per 本家 devices.ts
EXPECTED = {
    "DESKTOPWIN": ("9.7.0.3556", "WINDOWS", "10.0.0-NT-x64"),
    "DESKTOPMAC": ("26.2.0", "MAC", "13.0.0"),
    "CHROMEOS": ("3.0.3", "Chrome_OS", "1"),
    "ANDROID": ("26.6.2", "Android OS", "16"),
    "ANDROIDSECONDARY": ("26.6.2", "Android OS", "16"),
    "IOS": ("26.7.2", "iOS", "18.0"),
    "IOSIPAD": ("26.7.2", "iOS", "18.0"),
    "WATCHOS": ("26.7.2", "Watch OS", "11.0"),
    "WEAROS": ("13.4.1", "Wear OS", "3.0"),
}


@pytest.mark.parametrize("device,expected", EXPECTED.items())
def test_device_details(device, expected):
    d = get_device_details(device)
    assert d is not None, device
    assert (d.app_version, d.system_name, d.system_version) == expected


def test_default_versions():
    for device, (ver, _, _) in EXPECTED.items():
        assert DEFAULT_VERSIONS[device] == ver


def test_token_v3_support():
    # 本家 isV3Support: DESKTOPWIN, DESKTOPMAC, IOS, ANDROID, ANDROIDSECONDARY
    assert set(TOKEN_V3_SUPPORT) == {
        "DESKTOPWIN", "DESKTOPMAC", "IOS", "ANDROID", "ANDROIDSECONDARY"
    }


def test_custom_version_override():
    d = get_device_details("ANDROID", version="99.9.9")
    assert d.app_version == "99.9.9"


def test_build_app_name():
    d = get_device_details("ANDROID")
    assert build_app_name(d) == "ANDROID\t26.6.2\tAndroid OS\t16"
