"""
Pure hardware driver for a single ACE Pro device.
Handles serial communication, protocol, and basic device commands only.
Does NOT handle: tool changes, sensors, G-code commands (those belong in AceController).
"""

import serial
import threading
import time
import logging
import json
import queue
import traceback
from typing import Optional, Dict, Any, Callable

from ..protocol.constants import (
    READY_WAIT_DELAY,
    CONNECT_RETRY_DELAY,
    CONNECT_RETRY_MAX,
    CONNECT_RETRY_BACKOFF,
    READER_POLL_INTERVAL,
    WRITER_POLL_INTERVAL,
    REQUEST_TIMEOUT,
    MAX_REQUEST_ID,
    GATES_PER_ACE
)
from ..protocol.packet import AcePacket
from ..exceptions import AceException


class AceDevice:
    """
    Low-level hardware driver for a single ACE Pro device.

    Responsibilities:
    - Serial port communication
    - Protocol packet encoding/decoding
    - Device status polling
    - Simple command execution (feed, retract, dryer, feed_assist)

    Does NOT handle:
    - Tool change orchestration (belongs in AceController)
    - Sensor creation/management (belongs in AceController)
    - G-code command registration (belongs in AceController)
    """

    def __init__(self, port: str, baud: int, device_id: str, reactor, log_level=logging.INFO,
                 connect_retry_delay=CONNECT_RETRY_DELAY, connect_retry_max=CONNECT_RETRY_MAX):
        """
        Initialize ACE device driver.

        Args:
            port: Serial port path (e.g., '/dev/ttyACM0')
            baud: Baud rate (default 115200)
            device_id: Unique device identifier (from AceDeviceDiscovery)
            reactor: Klipper reactor for timer management
            log_level: Logging level (ERROR, INFO, DEBUG)
            connect_retry_delay: Delay between connection retries (default from constants)
            connect_retry_max: Maximum connection retry attempts (default from constants)
        """
        self.serial_id = port
        self.baud = baud
        self.device_id = device_id
        self.reactor = reactor
        self.log_level = log_level
        self.connect_retry_delay = connect_retry_delay
        self.connect_retry_max = connect_retry_max

        # Hardware state
        self._serial = None
        self._connected = False
        self._lock = threading.Lock()
        self._request_in_flight = False
        self._pending_request_id: Optional[int] = None
        self.send_time = None
        self.read_buffer = bytearray()

        # Request/response handling
        self._callback_map = {}
        self._request_id = 0
        self._queue = None  # Will be created in _handle_ready

        # Connection retry state
        self._connection_retry_count = 0
        self._connection_retry_backoff = 1.0

        # I/O error tracking
        self._consecutive_write_errors = 0
        self._io_error_cooldown = False
        self._max_consecutive_errors = 3

        # Device info
        self.num_gates = GATES_PER_ACE
        self._info = {
            'status': 'ready',
            'dryer_status': {
                'status': 'stop',
                'target_temp': 0,
                'duration': 0,
                'remain_time': 0
            },
            'temp': 0,
            'enable_rfid': 1,
            'fan_speed': 7000,
            'feed_assist_count': 0,
            'cont_assist_time': 0.0,
            'slots': []
        }

        # Initialize slots
        for i in range(self.num_gates):
            self._info['slots'].append({
                'index': i,
                'status': 'empty',
                'sku': '',
                'type': '',
                'color': [0, 0, 0]
            })

        self.gate_status = ['empty'] * self.num_gates

        logging.info(f"AceDevice: Created device {device_id} on {port}")

    def connect(self):
        """
        Initialize connection to ACE device.
        Called by controller when ready to connect.
        """
        logging.info(f'AceDevice: Connecting to {self.serial_id}')
        self._connected = False
        self._connection_retry_count = 0
        self._connection_retry_backoff = 1.0
        self._queue = queue.Queue()
        self.connect_timer = self.reactor.register_timer(self._connect, self.reactor.NOW)

    def disconnect(self):
        """Disconnect from ACE device and cleanup resources"""
        logging.info(f'AceDevice: Disconnecting from {self.serial_id}')
        self._serial_disconnect()
        if hasattr(self, 'connect_timer'):
            try:
                self.reactor.unregister_timer(self.connect_timer)
            except:
                pass

    def _connect(self, eventtime):
        """Attempt to connect to ACE device via serial port"""
        # If we're in I/O error cooldown, wait before attempting connection
        if self._io_error_cooldown:
            cooldown_delay = 5.0  # 5 second cooldown for I/O errors
            logging.info(f'AceDevice: I/O error cooldown active, waiting {cooldown_delay}s before reconnecting to {self.serial_id}')
            self._io_error_cooldown = False
            return eventtime + cooldown_delay

        logging.info(f'AceDevice: Attempting connection to {self.serial_id}')

        try:
            self._serial = serial.Serial(
                port=self.serial_id,
                baudrate=self.baud,
                exclusive=True,
                rtscts=True,
                timeout=0,
                write_timeout=0)

            if self._serial.is_open:
                # Reset state for new connection
                self._connected = True
                self._request_id = 0
                self._connection_retry_count = 0
                self._connection_retry_backoff = 1.0
                self._consecutive_write_errors = 0
                with self._lock:
                    self._request_in_flight = False
                    self._pending_request_id = None
                self.read_buffer = bytearray()

                logging.info(f'AceDevice: Successfully connected to {self.serial_id}')

                # Start communication timers
                self.writer_timer = self.reactor.register_timer(self._writer, eventtime + READY_WAIT_DELAY)
                self.reader_timer = self.reactor.register_timer(self._reader, eventtime + READY_WAIT_DELAY)

                # Request device info
                self.send_request(
                    request={"method": "get_info"},
                    callback=self._info_callback)

                # Stop connection retry timer
                if hasattr(self, 'connect_timer'):
                    self.reactor.unregister_timer(self.connect_timer)

                return self.reactor.NEVER

        except serial.serialutil.SerialException as e:
            self._serial = None
            self._connection_retry_count += 1

            if self._connection_retry_count >= self.connect_retry_max:
                logging.error(f'AceDevice: Failed to connect to {self.serial_id} after {self.connect_retry_max} attempts')
                return self.reactor.NEVER

            # Calculate retry delay with exponential backoff
            retry_delay = self.connect_retry_delay * self._connection_retry_backoff
            self._connection_retry_backoff *= CONNECT_RETRY_BACKOFF

            logging.warning(f'AceDevice: Serial connection error to {self.serial_id} (attempt {self._connection_retry_count}/{self.connect_retry_max}): {e}')
            logging.info(f'AceDevice: Retrying connection in {retry_delay:.1f}s...')
            return eventtime + retry_delay

        except Exception as e:
            self._serial = None
            self._connection_retry_count += 1
            logging.error(f'AceDevice: Unexpected connection error: {e}')

            if self._connection_retry_count >= self.connect_retry_max:
                return self.reactor.NEVER

            return eventtime + self.connect_retry_delay

    def _info_callback(self, response):
        """Handle device info response after connection"""
        if 'code' in response and response['code'] != 0:
            logging.error(f"AceDevice: Error getting device info: {response.get('msg', 'Unknown error')}")
            return

        result = response.get('result', {})
        model = result.get('model', 'Unknown')
        firmware = result.get('firmware', 'Unknown')

        logging.info(f'AceDevice: Connected to {model}, Firmware: {firmware}')
        logging.debug(f'AceDevice: Full device info: {json.dumps(result, indent=2)}')

    def _serial_disconnect(self) -> None:
        """Safely disconnect from serial port and cleanup timers"""
        try:
            if self._serial is not None and self._serial.is_open:
                self._serial.close()
                logging.info(f"AceDevice: Closed connection to {self.serial_id}")
        except Exception as e:
            logging.error(f"AceDevice: Error closing serial port: {e}")
        finally:
            self._connected = False

        try:
            if hasattr(self, 'reader_timer'):
                self.reactor.unregister_timer(self.reader_timer)
            if hasattr(self, 'writer_timer'):
                self.reactor.unregister_timer(self.writer_timer)
        except Exception as e:
            logging.error(f"AceDevice: Error unregistering timers: {e}")

        # Reset state
        with self._lock:
            self._request_in_flight = False
            self._pending_request_id = None
        self.read_buffer = bytearray()

    def _get_next_request_id(self) -> int:
        """Get next sequential request ID with wraparound"""
        self._request_id += 1
        if self._request_id >= MAX_REQUEST_ID:
            self._request_id = 0
        return self._request_id

    def _reader(self, eventtime):
        """Read and process responses from ACE device"""
        # Check for request timeout
        with self._lock:
            if self._request_in_flight and self.send_time and (self.reactor.monotonic() - self.send_time) > REQUEST_TIMEOUT:
                self._request_in_flight = False
                self._pending_request_id = None
                self.read_buffer = bytearray()
                logging.warning(f"AceDevice: Request timeout after {REQUEST_TIMEOUT}s")

        try:
            with self._lock:
                should_read = self._request_in_flight

            if should_read and self._serial.in_waiting:
                raw_bytes = self._serial.read(size=self._serial.in_waiting)
            else:
                raw_bytes = bytearray()
        except serial.SerialException as e:
            logging.error(f"AceDevice: Communication error: {e}")
            self._serial_disconnect()
            self.connect_timer = self.reactor.register_timer(self._connect, self.reactor.NOW)
            return self.reactor.NEVER
        except Exception as e:
            logging.error(f"AceDevice: Unable to communicate: {e}")
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None
            self._serial_disconnect()
            self.connect_timer = self.reactor.register_timer(self._connect, self.reactor.NOW)
            return self.reactor.NEVER

        if len(raw_bytes):
            # Use packet finder from protocol module
            self.read_buffer += raw_bytes
            packet, self.read_buffer = AcePacket.find_packet_in_buffer(self.read_buffer)

            if packet:
                buffer = packet
            else:
                return eventtime + READER_POLL_INTERVAL
        else:
            return eventtime + READER_POLL_INTERVAL

        # Decode packet
        response, error = AcePacket.decode(buffer)

        if error:
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None
            logging.warning(f"AceDevice: Packet decode error: {error}")
            return eventtime + READER_POLL_INTERVAL

        # Process response
        try:
            request_id = response.get('id')

            with self._lock:
                if request_id in self._callback_map:
                    callback = self._callback_map.pop(request_id)
                    self._request_in_flight = False
                    self._pending_request_id = None
                    # Execute callback outside lock to prevent deadlock
                    callback(response)
                else:
                    logging.warning(f"AceDevice: Received response for unknown request ID {request_id}")
        except Exception as e:
            logging.error(f"AceDevice: Error processing response: {e}")
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None

        return eventtime + READER_POLL_INTERVAL

    def _writer(self, eventtime):
        """Send requests to ACE device and poll status"""
        try:
            def status_callback(response):
                """Update internal state from status response"""
                if response is not None:
                    self._info = response.get('result', {})
                    # Dynamically detect number of gates from response
                    if 'slots' in self._info and len(self._info['slots']) > 0:
                        detected_gates = len(self._info['slots'])
                        if detected_gates != self.num_gates:
                            self.num_gates = detected_gates
                            self.gate_status = ['empty'] * self.num_gates
                            logging.info(f'AceDevice: Detected {self.num_gates} gates')
                    self.gate_status = [data['status'] for data in self._info.get('slots', [])]

            with self._lock:
                can_send = not self._request_in_flight

            if can_send:
                # Check for queued user requests first
                task = None
                try:
                    task = self._queue.get_nowait()
                except queue.Empty:
                    pass

                if task is not None:
                    request_id = self._get_next_request_id()
                    with self._lock:
                        self._callback_map[request_id] = task[1]
                        self._request_in_flight = True
                        self._pending_request_id = request_id
                    task[0]['id'] = request_id
                    self._send_request(task[0])
                    self.send_time = self.reactor.monotonic()
                else:
                    # Only poll status if no user requests pending
                    request_id = self._get_next_request_id()
                    with self._lock:
                        self._callback_map[request_id] = status_callback
                        self._request_in_flight = True
                        self._pending_request_id = request_id
                    self._send_request({"id": request_id, "method": "get_status"})
                    self.send_time = self.reactor.monotonic()

        except Exception as e:
            logging.error(f'AceDevice writer error: {e}\n{traceback.format_exc()}')
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None

            # Track consecutive errors for I/O issues
            self._consecutive_write_errors += 1

            # Only disconnect after multiple consecutive errors
            if self._consecutive_write_errors >= self._max_consecutive_errors:
                logging.error(f'AceDevice: {self._consecutive_write_errors} consecutive write errors, disconnecting...')
                self._io_error_cooldown = True
                self._serial_disconnect()
                self.connect_timer = self.reactor.register_timer(self._connect, self.reactor.NOW)
                return self.reactor.NEVER
            else:
                logging.warning(f'AceDevice: Write error {self._consecutive_write_errors}/{self._max_consecutive_errors}, continuing...')
                # Continue trying on next iteration
                return eventtime + WRITER_POLL_INTERVAL

        return eventtime + WRITER_POLL_INTERVAL

    def _send_request(self, request: Dict[str, Any]) -> None:
        """Send a JSON-RPC request to ACE device with retry logic"""
        if 'id' not in request:
            request['id'] = self._get_next_request_id()

        # Use AcePacket encoder
        packet_data = AcePacket.encode(request)

        # Retry write operation on I/O errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._serial.write(packet_data)
                # Reset consecutive error counter on successful write
                self._consecutive_write_errors = 0
                return
            except OSError as e:
                if attempt < max_retries - 1:
                    logging.warning(f"AceDevice: Write attempt {attempt + 1} failed: {e}, retrying...")
                    time.sleep(0.1)  # 100ms delay between retries
                else:
                    # All retries exhausted, re-raise
                    logging.error(f"AceDevice: Write failed after {max_retries} attempts: {e}")
                    raise

    def send_request(self, request: dict, callback: Callable):
        """
        Queue a request to send to ACE device.

        Args:
            request: JSON-RPC request dict (e.g., {"method": "feed_filament", "params": {...}})
            callback: Function to call with response: callback(response)
        """
        self._info['status'] = 'busy'
        self._queue.put([request, callback])

    def wait_ready(self, timeout: float = 30.0):
        """
        Wait for ACE device to become ready.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            AceException: If device doesn't become ready within timeout
        """
        start_time = self.reactor.monotonic()
        while self._info['status'] != 'ready':
            if self.reactor.monotonic() - start_time > timeout:
                raise AceException(f"Device {self.device_id} did not become ready within {timeout}s")
            currTs = self.reactor.monotonic()
            self.reactor.pause(currTs + 0.5)

    def is_ready(self) -> bool:
        """Check if device is ready to accept commands"""
        return self._info['status'] == 'ready'

    # ========================================================================
    # Simple command API - these just send requests, no orchestration
    # ========================================================================

    def feed(self, gate: int, length: int, speed: int, callback: Callable):
        """
        Feed filament from specified gate.

        Args:
            gate: Gate number (0-3)
            length: Feed length in mm
            speed: Feed speed in mm/s
            callback: Callback function(response)
        """
        if gate < 0 or gate >= self.num_gates:
            raise AceException(f"Invalid gate {gate} (valid: 0-{self.num_gates-1})")

        self.send_request(
            request={"method": "feed_filament", "params": {"index": gate, "length": length, "speed": speed}},
            callback=callback)

    def retract(self, gate: int, length: int, speed: int, callback: Callable):
        """
        Retract filament to specified gate.

        Args:
            gate: Gate number (0-3)
            length: Retract length in mm
            speed: Retract speed in mm/s
            callback: Callback function(response)
        """
        if gate < 0 or gate >= self.num_gates:
            raise AceException(f"Invalid gate {gate} (valid: 0-{self.num_gates-1})")

        self.send_request(
            request={"method": "unwind_filament", "params": {"index": gate, "length": length, "speed": speed}},
            callback=callback)

    def start_dryer(self, temp: int, duration: int, callback: Callable):
        """
        Start dryer.

        Args:
            temp: Target temperature in Celsius
            duration: Duration in minutes
            callback: Callback function(response)
        """
        self.send_request(
            request={"method": "drying", "params": {"temp": temp, "fan_speed": 7000, "duration": duration}},
            callback=callback)

    def stop_dryer(self, callback: Callable):
        """
        Stop dryer.

        Args:
            callback: Callback function(response)
        """
        self.send_request(
            request={"method": "drying_stop"},
            callback=callback)

    def start_feed_assist(self, gate: int, callback: Callable):
        """
        Start feed assist for specified gate.

        Args:
            gate: Gate number (0-3)
            callback: Callback function(response)
        """
        if gate < 0 or gate >= self.num_gates:
            raise AceException(f"Invalid gate {gate} (valid: 0-{self.num_gates-1})")

        self.send_request(
            request={"method": "start_feed_assist", "params": {"index": gate}},
            callback=callback)

    def stop_feed_assist(self, gate: int, callback: Callable):
        """
        Stop feed assist for specified gate.

        Args:
            gate: Gate number (0-3)
            callback: Callback function(response)
        """
        if gate < 0 or gate >= self.num_gates:
            raise AceException(f"Invalid gate {gate} (valid: 0-{self.num_gates-1})")

        self.send_request(
            request={"method": "stop_feed_assist", "params": {"index": gate}},
            callback=callback)

    def stop_feeding(self, gate: int, callback: Callable):
        """
        Stop feeding for specified gate.

        Args:
            gate: Gate number (0-3)
            callback: Callback function(response)
        """
        if gate < 0 or gate >= self.num_gates:
            raise AceException(f"Invalid gate {gate} (valid: 0-{self.num_gates-1})")

        self.send_request(
            request={"method": "stop_feed_filament", "params": {"index": gate}},
            callback=callback)

    def update_feeding_speed(self, gate: int, speed: int, callback: Callable):
        """
        Update feeding speed for specified gate.

        Args:
            gate: Gate number (0-3)
            speed: New speed in mm/s
            callback: Callback function(response)
        """
        if gate < 0 or gate >= self.num_gates:
            raise AceException(f"Invalid gate {gate} (valid: 0-{self.num_gates-1})")

        self.send_request(
            request={"method": "update_feeding_speed", "params": {"index": gate, "speed": speed}},
            callback=callback)

    def get_status(self) -> dict:
        """
        Get current device status (synchronous).

        Returns:
            Device status dictionary
        """
        return {
            'status': self._info['status'],
            'temp': self._info['temp'],
            'dryer_status': self._info['dryer_status'],
            'active_gate': self.gate_status,
            'num_gates': self.num_gates,
            'slots': self._info.get('slots', []),
            'device_id': self.device_id,
            'port': self.serial_id,
            'connected': self._connected
        }
