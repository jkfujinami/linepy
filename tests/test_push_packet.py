#!/usr/bin/env python3
"""PUSH stream packet framing tests (Phase 3 Step 9)."""

from linepy.push.packet import (
    PushPacketParser, build_packet, PingFrame, SignOnResponseFrame, PushFrame,
)


def _collector():
    events = []
    p = PushPacketParser(
        on_ping=lambda f: events.append(("ping", f.ping_type, f.ping_id)),
        on_sign_on_response=lambda rid, fin, pl: events.append(("sign", rid, fin, pl)),
        on_push=lambda f: events.append(("push", f.service_type, f.push_id, f.payload)),
    )
    return p, events


def test_ping_frame():
    p, ev = _collector()
    # dt=1, dd=[pingType=1, pingId hi, lo]
    p.on_data_received(build_packet(1, bytes([1, 0x01, 0x02])))
    assert ev == [("ping", 1, 0x0102)]


def test_sign_on_response_fin():
    p, ev = _collector()
    # req high bit set => isFin; requestId = req & 0x7fff
    req = 0x8005
    dd = bytes([(req >> 8) & 0xFF, req & 0xFF]) + b"PAYLOAD"
    p.on_data_received(build_packet(3, dd))
    assert ev == [("sign", 5, True, b"PAYLOAD")]


def test_sign_on_response_fragmented():
    p, ev = _collector()
    rid = 7
    # first fragment: not fin (req = rid, high bit clear)
    p.on_data_received(build_packet(3, bytes([0x00, rid]) + b"AAA"))
    # second fragment: fin (high bit set)
    req_fin = 0x8000 | rid
    p.on_data_received(build_packet(3, bytes([(req_fin >> 8) & 0xFF, req_fin & 0xFF]) + b"BBB"))
    assert ev == [("sign", 7, True, b"AAABBB")]


def test_push_frame():
    p, ev = _collector()
    # dt=4, dd=[pushType, serviceType, pushId(4B), payload...]
    dd = bytes([0, 8, 0x00, 0x00, 0x00, 0x2A]) + b"NEW"
    p.on_data_received(build_packet(4, dd))
    assert ev == [("push", 8, 0x2A, b"NEW")]


def test_split_frame_buffering():
    p, ev = _collector()
    full = build_packet(1, bytes([1, 0x00, 0x09]))
    # feed byte-by-byte; only completes when all bytes arrive
    for i in range(len(full) - 1):
        p.on_data_received(full[i:i + 1] if i == 0 else full[i:i + 1])
    assert ev == []  # not complete yet
    p.on_data_received(full[-1:])
    assert ev == [("ping", 1, 0x09)]


def test_two_packets_in_one_read():
    p, ev = _collector()
    a = build_packet(1, bytes([1, 0x00, 0x01]))
    b = build_packet(1, bytes([1, 0x00, 0x02]))
    p.on_data_received(a + b)
    assert ev == [("ping", 1, 1), ("ping", 1, 2)]


def test_header_parse():
    dt, dd, dl = PushPacketParser.read_packet_header(build_packet(4, b"abcd"))
    assert dt == 4 and dd == b"abcd" and dl == 4
