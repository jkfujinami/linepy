# -*- coding: utf-8 -*-
"""Hand-written models for endpoints that do not return Thrift structs.

``login`` covers the /LF1 and /Q verification JSON plus the loginV2 /
qrCodeLoginV2 token structs; ``timeline`` covers the VOOM REST API, whose
responses are keyed by real JSON names rather than Thrift field ids.

Everything else is generated -- see :mod:`linepy.models.generated`.
"""

from . import login, timeline

__all__ = ["login", "timeline"]
