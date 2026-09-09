#!/usr/bin/env python3
"""QR login is a secondary-device flow.

`BaseClient("ANDROID").login_with_qr()` used to reach the server and come
back with SecondaryQrCodeErrorCode 101, APP_UPGRADE_REQUIRED --
"LINEアプリをアップデートして、もう一度お試しください。" The app version is not
the problem: verified against /acct/lgn/sq/v1 createSession, ANDROID and IOS
are refused while ANDROIDSECONDARY, IOSIPAD, DESKTOPWIN, DESKTOPMAC, WATCHOS
and WEAROS all succeed on those exact same versions. The refusal is about the
device being a primary one, which is the side that *approves* a QR code
rather than the side that scans it.
"""

import os
import tempfile

import pytest

from linepy.base import BaseClient
from linepy.config import PRIMARY_DEVICES, SECONDARY_DEVICE_FOR
from linepy.exceptions import LoginError

SECONDARY_DEVICES = [
    "ANDROIDSECONDARY",
    "IOSIPAD",
    "DESKTOPWIN",
    "DESKTOPMAC",
    "WATCHOS",
    "WEAROS",
]


def _client(device):
    return BaseClient(device, storage=os.path.join(tempfile.mkdtemp(), "s.json"))


@pytest.mark.parametrize("device", PRIMARY_DEVICES)
def test_primary_devices_are_refused_before_any_request(device):
    client = _client(device)
    client.request.request = lambda **kw: pytest.fail("should not reach the server")

    with pytest.raises(LoginError) as ei:
        client.login_with_qr()

    assert device in str(ei.value)


@pytest.mark.parametrize("device", PRIMARY_DEVICES)
def test_the_error_names_the_device_to_use_instead(device):
    client = _client(device)

    with pytest.raises(LoginError) as ei:
        client.login_with_qr()

    assert SECONDARY_DEVICE_FOR[device] in str(ei.value)
    assert "login_with_email" in str(ei.value)


@pytest.mark.parametrize("device", SECONDARY_DEVICES)
def test_secondary_devices_get_through_to_the_flow(device):
    """The guard must not turn away a device the server accepts."""
    client = _client(device)
    reached = []

    def _blocked(**kwargs):
        reached.append(kwargs.get("path"))
        raise RuntimeError("stop here")

    client.request.request = _blocked

    with pytest.raises(RuntimeError):
        client.login_with_qr()

    assert reached, f"{device} was refused before reaching the network"


@pytest.mark.parametrize("device", PRIMARY_DEVICES)
def test_email_login_is_still_allowed_on_primary_devices(device):
    """Only the QR flow is secondary-only; email login is how these log in."""
    client = _client(device)
    reached = []

    def _blocked(**kwargs):
        reached.append(kwargs.get("path"))
        raise RuntimeError("stop here")

    client.request.request = _blocked

    with pytest.raises(RuntimeError):
        client.login_with_email("someone@example.com", "password123")

    assert reached


def test_every_primary_device_has_a_secondary_counterpart():
    assert set(SECONDARY_DEVICE_FOR) == set(PRIMARY_DEVICES)
