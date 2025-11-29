"""
ACE Pro serial protocol packet handling.
Handles packet encoding, decoding, and CRC calculation.
"""

import struct
import json
from typing import Dict, Any, Optional, Tuple
from .constants import (
    PROTOCOL_HEAD_BYTES,
    PROTOCOL_TAIL_BYTE,
    PROTOCOL_MIN_PACKET_SIZE,
    CRC_INIT_VALUE
)


def calc_crc(buffer: bytes) -> int:
    """
    Calculate CRC16 for ACE protocol.

    Args:
        buffer: Payload bytes to calculate CRC for

    Returns:
        CRC16 value
    """
    _crc = CRC_INIT_VALUE
    for byte in buffer:
        data = byte
        data ^= _crc & 0xff
        data ^= (data & 0x0f) << 4
        _crc = ((data << 8) | (_crc >> 8)) ^ (data >> 4) ^ (data << 3)
    return _crc


class AcePacket:
    """
    ACE protocol packet encoder/decoder.

    Packet format:
    [HEAD(2)] [LEN(2)] [PAYLOAD(n)] [CRC(2)] [TAIL(1)]

    - HEAD: 0xFF 0xAA (2 bytes)
    - LEN: Payload length (2 bytes, little-endian)
    - PAYLOAD: JSON-encoded request/response
    - CRC: CRC16 of payload (2 bytes)
    - TAIL: 0xFE (1 byte)
    """

    @staticmethod
    def encode(request: Dict[str, Any]) -> bytes:
        """
        Encode JSON request to ACE protocol packet.

        Args:
            request: Dictionary containing JSON-RPC request

        Returns:
            Encoded packet bytes ready to send over serial

        Example:
            >>> packet = AcePacket.encode({"id": 1, "method": "get_status"})
        """
        payload = json.dumps(request).encode('utf-8')

        data = PROTOCOL_HEAD_BYTES
        data += struct.pack('@H', len(payload))
        data += payload
        data += struct.pack('@H', calc_crc(payload))
        data += bytes([PROTOCOL_TAIL_BYTE])

        return data

    @staticmethod
    def decode(buffer: bytes) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Decode ACE protocol packet to JSON response.

        Args:
            buffer: Raw bytes received from serial port

        Returns:
            Tuple of (decoded_response, error_message) or (None, error_message)
            If successful, error_message is None

        Example:
            >>> response, error = AcePacket.decode(raw_bytes)
            >>> if error:
            ...     print(f"Decode error: {error}")
            >>> else:
            ...     print(f"Response: {response}")
        """
        # Check minimum packet size
        if len(buffer) < PROTOCOL_MIN_PACKET_SIZE:
            return None, f"Packet too small: {len(buffer)} < {PROTOCOL_MIN_PACKET_SIZE}"

        # Validate header
        if buffer[0:2] != PROTOCOL_HEAD_BYTES:
            return None, f"Invalid protocol header: {buffer[0:2].hex()}"

        # Extract payload length
        payload_len = struct.unpack('<H', buffer[2:4])[0]

        # Check if we have complete packet
        expected_len = 4 + payload_len + 2 + 1  # header + len + payload + crc + tail
        if len(buffer) < expected_len:
            return None, f"Incomplete packet: expected {expected_len}, got {len(buffer)}"

        # Extract payload
        payload = buffer[4:4 + payload_len]

        # Validate CRC
        crc_data = buffer[4 + payload_len:4 + payload_len + 2]
        crc_calculated = struct.pack('@H', calc_crc(payload))

        if crc_data != crc_calculated:
            return None, f"CRC mismatch: expected {crc_calculated.hex()}, got {crc_data.hex()}"

        # Validate tail byte
        tail_byte = buffer[4 + payload_len + 2]
        if tail_byte != PROTOCOL_TAIL_BYTE:
            return None, f"Invalid tail byte: {tail_byte:02X}"

        # Decode JSON payload
        try:
            response = json.loads(payload.decode('utf-8'))
            return response, None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return None, f"JSON decode error: {e}"

    @staticmethod
    def find_packet_in_buffer(buffer: bytearray) -> Tuple[Optional[bytes], bytearray]:
        """
        Search for a complete packet in a buffer.

        Args:
            buffer: Accumulated bytes from serial reads

        Returns:
            Tuple of (packet_bytes, remaining_buffer)
            If no complete packet found, returns (None, buffer)

        Example:
            >>> packet, remaining = AcePacket.find_packet_in_buffer(read_buffer)
            >>> if packet:
            ...     response, error = AcePacket.decode(packet)
            ...     read_buffer = remaining
        """
        # Look for tail byte (end of packet marker)
        tail_index = buffer.find(PROTOCOL_TAIL_BYTE)

        if tail_index >= 0:
            # Found potential packet - extract it
            packet = bytes(buffer[:tail_index + 1])
            remaining = bytearray(buffer[tail_index + 1:])
            return packet, remaining

        # No complete packet yet
        return None, buffer
