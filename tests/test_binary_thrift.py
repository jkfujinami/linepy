#!/usr/bin/env python3
"""TBinaryProtocol writer/reader round-trip tests (email-login fix)."""

import struct

from linepy.thrift import ThriftReader, TType, write_thrift


def test_binary_message_header():
    req = write_thrift([[12, 1, [[8, 2, 0]]]], "getRSAKeyInfo", 3)
    # strict binary header: version 0x80010001
    assert req[:4] == bytes([0x80, 0x01, 0x00, 0x01])
    (name_len,) = struct.unpack(">i", req[4:8])
    assert req[8:8 + name_len] == b"getRSAKeyInfo"


def _bin_response(name, fields, mtype=2):
    nb = name.encode()
    out = bytearray(bytes([0x80, 0x01, 0x00, mtype]) + struct.pack(">i", len(nb)) + nb + struct.pack(">i", 0))
    out += bytes([TType.STRUCT]) + struct.pack(">h", 0)  # success at field 0
    for fid, val in fields.items():
        b = val.encode()
        out += bytes([TType.STRING]) + struct.pack(">h", fid) + struct.pack(">i", len(b)) + b
    out += bytes([TType.STOP])  # struct stop
    out += bytes([TType.STOP])  # message stop
    return bytes(out)


def test_binary_reader_parse_response():
    data = _bin_response("getRSAKeyInfo", {1: "keynm", 2: "00abcd", 3: "10001", 4: "sess"})
    parsed = ThriftReader(data).parse_response()
    assert parsed == {1: "keynm", 2: "00abcd", 3: "10001", 4: "sess"}


def test_binary_reader_error_response():
    nb = b"m"
    out = bytearray(bytes([0x80, 0x01, 0x00, 2]) + struct.pack(">i", len(nb)) + nb + struct.pack(">i", 0))
    # error at field 1: struct {1: i32 code, 2: string reason}
    out += bytes([TType.STRUCT]) + struct.pack(">h", 1)
    out += bytes([TType.I32]) + struct.pack(">h", 1) + struct.pack(">i", 8)
    reason = b"BAD"
    out += bytes([TType.STRING]) + struct.pack(">h", 2) + struct.pack(">i", len(reason)) + reason
    out += bytes([TType.STOP]) + bytes([TType.STOP])
    parsed = ThriftReader(bytes(out)).parse_response()
    assert parsed["error"]["code"] == 8
    assert parsed["error"]["message"] == "BAD"


def test_binary_writer_types_roundtrip():
    # Struct with i32/i64/bool/binary/list, written then read back.
    # Put the struct at field 0 so parse_response reads it as the success value.
    params = [[
        12, 0, [
            [8, 1, 42],
            [10, 2, 123456789012],
            [2, 3, True],
            [11, 4, "hello"],
            [15, 5, [11, ["a", "b"]]],
        ]
    ]]
    data = write_thrift(params, "m", 3)
    inner = ThriftReader(data).parse_response()
    assert inner[1] == 42
    assert inner[2] == 123456789012
    assert inner[3] is True
    assert inner[4] == "hello"
    assert inner[5] == ["a", "b"]


def test_rsakeyinfo_model_parses_field_ids():
    from linepy.models import RSAKeyInfo
    from linepy.services.base import _convert_int_keys_to_str

    r = {1: "keynm", 2: "00ab", 3: "10001", 4: "sess"}
    m = RSAKeyInfo.model_validate(_convert_int_keys_to_str(r))
    assert (m.keynm, m.nvalue, m.evalue, m.sessionKey) == ("keynm", "00ab", "10001", "sess")
