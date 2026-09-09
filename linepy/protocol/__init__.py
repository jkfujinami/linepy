# -*- coding: utf-8 -*-
"""Wire protocols LINEPY speaks.

* :mod:`~linepy.protocol.thrift` -- binary and compact Thrift codecs, plus
  the TMoreCompact variant LINE uses for Talk sync payloads.
* :mod:`~linepy.protocol.compact` -- the minimal /CA5 and /ECA5 message
  frames that bypass Thrift entirely for fast sends.
* :mod:`~linepy.protocol.legy` -- LEGY's encrypted /enc envelope, its header
  codec and HMAC.

These modules serialise bytes; they never open a socket. That is
:mod:`linepy.transport`.
"""
