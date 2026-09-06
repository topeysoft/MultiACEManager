"""Protocol layer: framing, CRC, and decode error handling. Pure Python, no I/O."""
import json
import struct

import pytest


@pytest.fixture
def packet(ace):
    from ace.protocol.packet import AcePacket, calc_crc
    from ace.protocol import constants
    return AcePacket, calc_crc, constants


def test_crc_regression_vectors(packet):
    _, calc_crc, _ = packet
    # Pinned so a refactor of calc_crc cannot silently change the wire format.
    assert calc_crc(b"") == 0xFFFF
    assert calc_crc(b'{"id": 1, "method": "get_info"}') == 0x5B5C


def test_encode_matches_wire_format(packet):
    AcePacket, calc_crc, c = packet
    request = {"id": 1, "method": "get_info"}
    data = AcePacket.encode(request)
    payload = json.dumps(request).encode()
    assert data[:2] == c.PROTOCOL_HEAD_BYTES
    assert struct.unpack("<H", data[2:4])[0] == len(payload)
    assert data[4:4 + len(payload)] == payload
    assert struct.unpack("<H", data[-3:-1])[0] == calc_crc(payload)
    assert data[-1] == c.PROTOCOL_TAIL_BYTE
    assert data.hex() == "ffaa1f007b226964223a20312c20226d6574686f64223a20226765745f696e666f227d5c5bfe"


def test_roundtrip(packet):
    AcePacket, _, _ = packet
    message = {"id": 42, "code": 0, "result": {"status": "ready", "slots": [{"index": 0}]}}
    decoded, error = AcePacket.decode(AcePacket.encode(message))
    assert error is None
    assert decoded == message


@pytest.mark.parametrize("mutate, expected", [
    (lambda d: d[:5], "Packet too small"),
    (lambda d: b"\x00\x00" + d[2:], "Invalid protocol header"),
    (lambda d: d[:-4], "Incomplete packet"),
    (lambda d: d[:-3] + bytes([d[-3] ^ 0xFF]) + d[-2:], "CRC mismatch"),
    (lambda d: d[:-1] + b"\x00", "Invalid tail byte"),
])
def test_decode_rejects_corruption(packet, mutate, expected):
    AcePacket, _, _ = packet
    data = AcePacket.encode({"id": 1, "method": "get_status"})
    decoded, error = AcePacket.decode(mutate(data))
    assert decoded is None
    assert expected in error


def test_decode_rejects_bad_json(packet):
    AcePacket, calc_crc, c = packet
    payload = b"not json"
    data = c.PROTOCOL_HEAD_BYTES + struct.pack("<H", len(payload)) + payload
    data += struct.pack("<H", calc_crc(payload)) + bytes([c.PROTOCOL_TAIL_BYTE])
    decoded, error = AcePacket.decode(data)
    assert decoded is None and "JSON decode error" in error


def test_find_packet_splits_two_packets(packet):
    AcePacket, _, _ = packet
    first = AcePacket.encode({"id": 1, "method": "a"})
    second = AcePacket.encode({"id": 2, "method": "b"})
    found, remaining = AcePacket.find_packet_in_buffer(bytearray(first + second))
    assert found == first
    assert bytes(remaining) == second


def test_find_packet_waits_for_tail(packet):
    AcePacket, _, _ = packet
    partial = AcePacket.encode({"id": 1, "method": "a"})[:-1]
    found, remaining = AcePacket.find_packet_in_buffer(bytearray(partial))
    assert found is None
    assert bytes(remaining) == partial


def test_find_packet_skips_leading_garbage(packet):
    AcePacket, _, _ = packet
    data = AcePacket.encode({"id": 1, "method": "a"})
    found, remaining = AcePacket.find_packet_in_buffer(bytearray(b"\x00\xfe\x12" + data))
    assert found == data and remaining == bytearray()


def test_find_packet_keeps_split_header(packet):
    AcePacket, _, c = packet
    found, remaining = AcePacket.find_packet_in_buffer(bytearray(b"junk" + c.PROTOCOL_HEAD_BYTES[:1]))
    assert found is None and bytes(remaining) == c.PROTOCOL_HEAD_BYTES[:1]


def test_find_packet_when_length_byte_is_tail_value(packet):
    AcePacket, _, _ = packet
    message = {"id": 1, "result": {"pad": "x" * 222}}
    data = AcePacket.encode(message)
    assert data[2] == 0xFE, "payload length must be 254 for this case"
    found, _ = AcePacket.find_packet_in_buffer(bytearray(data))
    decoded, error = AcePacket.decode(found)
    assert error is None and decoded == message


def test_find_packet_when_crc_contains_tail_byte(packet):
    AcePacket, calc_crc, _ = packet
    # Search for a payload whose CRC has an 0xFE byte (about 1 in 128 responses).
    for n in range(100000):
        message = {"id": n, "code": 0, "result": {}}
        crc = calc_crc(json.dumps(message).encode())
        if 0xFE in struct.pack("<H", crc):
            break
    else:
        pytest.skip("no CRC with 0xFE found")
    data = AcePacket.encode(message)
    found, _ = AcePacket.find_packet_in_buffer(bytearray(data))
    decoded, error = AcePacket.decode(found)
    assert error is None, error
    assert decoded == message
