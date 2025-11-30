"""
Protocol and timing constants for ACE Pro communication.
"""

# Protocol Constants
PROTOCOL_HEAD_BYTES = bytes([0xFF, 0xAA])
PROTOCOL_TAIL_BYTE = 0xFE
PROTOCOL_MIN_PACKET_SIZE = 7
CRC_INIT_VALUE = 0xFFFF

# Timing Constants (matched to reference implementation)
DEFAULT_EVENT_DELAY = 0.1
READY_WAIT_DELAY = 2.0  # Match reference implementation
CONNECT_RETRY_DELAY = 1.0
CONNECT_RETRY_MAX = 10  # Maximum connection retry attempts
CONNECT_RETRY_BACKOFF = 1.5  # Exponential backoff multiplier
READER_POLL_INTERVAL = 0.2  # Match reference - fast response reading
WRITER_POLL_INTERVAL = 0.5  # Match reference - poll status 2x per second
SENSOR_POLL_INTERVAL = 0.5  # Reasonable sensor polling rate
REQUEST_TIMEOUT = 2.0  # Match reference - fail fast on communication errors
FEED_ASSIST_DELAY = 0.7
FEED_ASSIST_DISABLE_DELAY = 0.3

# ACE Device Constants
DEFAULT_NUM_GATES = 4
GATES_PER_ACE = 4
DEFAULT_BAUD_RATE = 115200
DEFAULT_MAX_DRYER_TEMP = 55
DEFAULT_FEED_SPEED = 50
DEFAULT_RETRACT_SPEED = 50
DEFAULT_EXTRUDER_SPEED = 10
DEFAULT_TOOLHEAD_HOMING_SPEED = 10
DEFAULT_TOOLCHANGE_RETRACT_LENGTH = 100
DEFAULT_TOOLCHANGE_FEED_LENGTH = 100
DEFAULT_TOOLHEAD_HOMING_MAX = 100

# Request ID bounds
MAX_REQUEST_ID = 300000

# Default colors and materials
DEFAULT_COLOR = 'FFFFFF'
DEFAULT_MATERIAL = ''
DEFAULT_TEMP = 230
