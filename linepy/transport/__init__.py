# -*- coding: utf-8 -*-
"""HTTP transport for LINEPY.

:mod:`~linepy.transport.http` owns the httpx client, header construction,
the LEGY encrypted-request path and the access-token lifecycle hooks. What
goes over the wire is built by :mod:`linepy.protocol`.
"""

from .http import RequestClient

__all__ = ["RequestClient"]
