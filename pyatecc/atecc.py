# SPDX-FileCopyrightText: 2018 Arduino SA
# SPDX-FileCopyrightText: 2019 Brent Rubell for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# Copyright (c) 2018 Arduino SA. All rights reserved.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

"""
`pyatecc`
================================================================================

Python package for the Microchip ATECCx08A Cryptographic Co-Processor


* Author(s): Brent Rubell, Calin Crisan

Implementation Notes
--------------------

**Software and Dependencies:**

 * https://github.com/kplindegaard/smbus2

"""

import time

from binascii import hexlify
from struct import pack

from smbus2 import SMBus, i2c_msg


# Device Address
_REG_ATECC_ADDR = 0xC0
_REG_ATECC_DEVICE_ADDR = _REG_ATECC_ADDR >> 1

# Version Registers
_ATECC_508_VER = 0x50
_ATECC_608_VER = 0x60

# Clock constants
_WAKE_CLK_FREQ = 100000  # slower clock speed
_TWLO_TIME = 6e-5  # TWlo, in microseconds

# Command Opcodes (9-1-3)
OP_COUNTER = 0x24
OP_INFO = 0x30
OP_NONCE = 0x16
OP_RANDOM = 0x1B
OP_SHA = 0x47
OP_LOCK = 0x17
OP_GEN_KEY = 0x40
OP_SIGN = 0x41
OP_WRITE = 0x12

# Maximum execution times, in milliseconds (9-4)
EXEC_TIME = {
    OP_COUNTER: 20,
    OP_INFO: 1,
    OP_NONCE: 7,
    OP_RANDOM: 23,
    OP_SHA: 47,
    OP_LOCK: 32,
    OP_GEN_KEY: 115,
    OP_SIGN: 70,
    OP_WRITE: 26,
}


CFG_TLS = b"\x01#\x00\x00\x00\x00P\x00\x00\x00\x00\x00\x00\xc0q\x00 \
            \xc0\x00U\x00\x83 \x87 \x87 \x87/\x87/\x8f\x8f\x9f\x8f\xaf \
            \x8f\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00 \
            \xaf\x8f\xff\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff\xff\x00 \
            \x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff \
            \xff\xff\xff\xff\x00\x00UU\xff\xff\x00\x00\x00\x00\x00\x003 \
            \x003\x003\x003\x003\x00\x1c\x00\x1c\x00\x1c\x00<\x00<\x00<\x00< \
            \x00<\x00<\x00<\x00\x1c\x00"


class ATECC:
    """
    Python interface for the ATECCx08A Crypto Co-Processor Devices.
    """

    def __init__(self, i2c_no, address=_REG_ATECC_DEVICE_ADDR, debug=False):
        """Initializes an ATECC device.
        :param int i2c_no: I2C bus number.
        :param int address: Device address, defaults to _REG_ATECC_DEVICE_ADDR.
        :param bool debug: Library debugging enabled

        """
        self._debug = debug
        self._address = address
        self._i2c = SMBus(i2c_no)
        self.wakeup()
        if (self.version >> 8) not in (_ATECC_508_VER, _ATECC_608_VER):
            raise RuntimeError(
                "Failed to find 608 or 508 chip. Please check your wiring."
            )

    def wakeup(self):
        """Wakes up THE ATECC608A from sleep or idle modes."""
        # This is a hack to generate the ATECC Wake condition, which is SDA
        # held low for t > 60us (twlo). For an I2C clock freq of 100kHz, 8
        # clock cycles will be 80us. This signal is generated by trying to
        # address something at 0x00. It will fail, but the pattern should
        # wake up the ATECC.
        # pylint: disable=bare-except
        try:
            self._i2c.write_byte_data(0x00, 0, 0x00)
        except:
            pass
        time.sleep(0.001)

    def idle(self):
        """Puts the chip into idle mode
        until wakeup is called.
        """
        self._i2c.write_byte_data(self._address, 0, 0x02)
        time.sleep(0.001)

    def sleep(self):
        """Puts the chip into low-power
        sleep mode until wakeup is called.
        """
        self._i2c.write_byte_data(self._address, 0, 0x01)
        time.sleep(0.001)

    @property
    def locked(self):
        """Returns if the ATECC is locked."""
        config = self._read(0x00, 0x15, 4)
        time.sleep(0.001)
        return config[2] == 0x0 and config[3] == 0x00

    @property
    def serial_number(self):
        """Returns the ATECC serial number."""
        # 4-byte reads only
        serial_num = self._read(0, 0x00, 4)
        time.sleep(0.001)
        serial_num += self._read(0, 0x02, 4)
        time.sleep(0.001)
        # Append Rev
        serial_num += self._read(0, 0x03, 4)[:1]
        time.sleep(0.001)
        # neaten up the serial for printing
        serial_num = str(hexlify(bytes(serial_num)), "utf-8")
        serial_num = serial_num.upper()
        return serial_num

    @property
    def version(self):
        """Returns the ATECC608As revision number"""
        self.wakeup()
        self.idle()
        vers = self.info(0x00)
        return (vers[2] << 8) | vers[3]

    def lock_all_zones(self):
        """Locks Config, Data and OTP Zones."""
        self.lock(0)
        self.lock(1)

    def lock(self, zone):
        """Locks specific ATECC zones.
        :param int zone: ATECC zone to lock.
        """
        self.wakeup()
        self._send_command(0x17, 0x80 | zone, 0x0000)
        time.sleep(EXEC_TIME[OP_LOCK] / 1000)
        res = self._get_response(1)
        assert res[0] == 0x00, "Failed locking ATECC!"
        self.idle()

    def info(self, mode, param=None):
        """Returns device state information
        :param int mode: Mode encoding, see Table 9-26.

        """
        self.wakeup()
        if not param:
            self._send_command(OP_INFO, mode)
        else:
            self._send_command(OP_INFO, mode, param)
        time.sleep(EXEC_TIME[OP_INFO] / 1000)
        info_out = self._get_response(4)
        self.idle()
        return info_out

    def nonce(self, data, mode=0, zero=0x0000):
        """Generates a nonce by combining internally generated random number
        with an input value.
        :param bytearray data: Input value from system or external.
        :param int mode: Controls the internal RNG and seed mechanism.
        :param int zero: Param2, see Table 9-35.

        """
        self.wakeup()
        if mode in (0x00, 0x01):
            if zero == 0x00:
                assert len(data) == 20, "Data value must be 20 bytes long."
            self._send_command(OP_NONCE, mode, zero, data)
            # nonce returns 32 bytes
            calculated_nonce_len = 32
        elif mode == 0x03:
            # Operating in Nonce pass-through mode
            assert len(data) == 32, "Data value must be 32 bytes long."
            self._send_command(OP_NONCE, mode, zero, data)
            # nonce returns 1 byte
            calculated_nonce_len = 1
        else:
            raise RuntimeError("Invalid mode specified!")
        time.sleep(EXEC_TIME[OP_NONCE] / 1000)
        calculated_nonce = self._get_response(calculated_nonce_len)
        time.sleep(1 / 1000)
        if mode == 0x03:
            assert (
                calculated_nonce[0] == 0x00
            ), "Incorrectly calculated nonce in pass-thru mode"
        self.idle()
        return calculated_nonce

    def counter(self, counter=0, increment_counter=True):
        """Reads the binary count value from one of the two monotonic
        counters located on the device within the configuration zone.
        The maximum value that the counter may have is 2,097,151.
        :param int counter: Device's counter to increment.
        :param bool increment_counter: Increments the value of the counter specified.

        """
        counter = 0x00
        self.wakeup()
        if counter == 1:
            counter = 0x01
        if increment_counter:
            self._send_command(OP_COUNTER, 0x01, counter)
        else:
            self._send_command(OP_COUNTER, 0x00, counter)
        time.sleep(EXEC_TIME[OP_COUNTER] / 1000)
        count = self._get_response(4)
        self.idle()
        return count

    def random(self, rnd_min=0, rnd_max=0):
        """Generates a random number for use by the system.
        :param int rnd_min: Minimum Random value to generate.
        :param int rnd_max: Maximum random value to generate.

        """
        if rnd_max:
            rnd_min = 0
        if rnd_min >= rnd_max:
            return rnd_min
        delta = rnd_max - rnd_min
        r = bytes(16)
        r = self._random(r)
        data = 0
        for i in enumerate(r):
            data += r[i[0]]
        if data < 0:
            data = -data
        data = data % delta
        return data + rnd_min

    def _random(self, data):
        """Initializes the random number generator and returns.
        :param bytearray data: Response buffer.

        """
        self.wakeup()
        data_len = len(data)
        while data_len:
            self._send_command(OP_RANDOM, 0x00, 0x0000)
            time.sleep(EXEC_TIME[OP_RANDOM] / 1000)
            resp = self._get_response(32)
            copy_len = min(32, data_len)
            data = resp[0:copy_len]
            data_len -= copy_len
        self.idle()
        return data

    # SHA-256 Commands
    def sha_start(self):
        """Initializes the SHA-256 calculation engine
        and the SHA context in memory.
        This method MUST be called before sha_update or sha_digest
        """
        self.wakeup()
        self._send_command(OP_SHA, 0x00)
        time.sleep(EXEC_TIME[OP_SHA] / 1000)
        status = self._get_response(1)
        assert status[0] == 0x00, "Error during sha_start."
        self.idle()
        return status

    def sha_update(self, message):
        """Appends bytes to the message. Can be repeatedly called.
        :param bytes message: Up to 64 bytes of data to be included
                                into the hash operation.

        """
        self.wakeup()
        self._send_command(OP_SHA, 0x01, 64, message)
        time.sleep(EXEC_TIME[OP_SHA] / 1000)
        status = self._get_response(1)
        assert status[0] == 0x00, "Error during SHA Update"
        self.idle()
        return status

    def sha_digest(self, message=None):
        """Returns the digest of the data passed to the
        sha_update method so far.
        :param bytearray message: Up to 64 bytes of data to be included
                                    into the hash operation.

        """
        if not hasattr(message, "append") and message is not None:
            message = pack("B", message)
        self.wakeup()
        # Include optional message
        if message:
            self._send_command(OP_SHA, 0x02, len(message), message)
        else:
            self._send_command(OP_SHA, 0x02)
        time.sleep(EXEC_TIME[OP_SHA] / 1000)
        digest = self._get_response(32)
        assert len(digest) == 32, "SHA response length does not match expected length."
        self.idle()
        return digest

    def gen_key(self, slot_num, private_key=False):
        """Generates a private or public key.
        :param int slot_num: ECC slot (from 0 to 4).
        :param bool private_key: Generates a private key if true.

        """
        assert 0 <= slot_num <= 4, "Provided slot must be between 0 and 4."
        self.wakeup()
        if private_key:
            self._send_command(OP_GEN_KEY, 0x04, slot_num)
        else:
            self._send_command(OP_GEN_KEY, 0x00, slot_num)
        time.sleep(EXEC_TIME[OP_GEN_KEY] / 1000)
        key = self._get_response(64)
        time.sleep(0.001)
        self.idle()
        return key

    def ecdsa_sign(self, slot, message):
        """Generates and returns a signature using the ECDSA algorithm.
        :param int slot: Which ECC slot to use.
        :param bytearray message: Message to be signed.

        """
        # Load the message digest into TempKey using Nonce (9.1.8)
        self.nonce(message, 0x03)
        # Generate and return a signature
        sig = self.sign(slot)
        return sig

    def sign(self, slot_id):
        """Performs ECDSA signature calculation with key in provided slot.
        :param int slot_id: ECC slot containing key for use with signature.
        """
        self.wakeup()
        self._send_command(0x41, 0x80, slot_id)
        time.sleep(EXEC_TIME[OP_SIGN] / 1000)
        signature = self._get_response(64)
        self.idle()
        return signature

    def write_config(self, data):
        """Writes configuration data to the device's EEPROM.
        :param bytearray data: Configuration data to-write
        """
        # First 16 bytes of data are skipped, not writable
        for i in range(16, 128, 4):
            if i == 84:
                # can't write
                continue
            self._write(0, i // 4, data[i : i + 4])

    def _write(self, zone, address, buffer):
        self.wakeup()
        if len(buffer) not in (4, 32):
            raise RuntimeError("Only 4 or 32-byte writes supported.")
        if len(buffer) == 32:
            zone |= 0x80
        self._send_command(0x12, zone, address, buffer)
        time.sleep(26 / 1000)
        status = self._get_response(1)
        self.idle()

    def _read(self, zone, address, length):
        self.wakeup()
        if length not in (4, 32):
            raise RuntimeError("Only 4 and 32 byte reads supported")
        if length == 32:
            zone |= 0x80
        self._send_command(2, zone, address)
        time.sleep(0.005)
        buffer = self._get_response(length)
        time.sleep(0.001)
        self.idle()
        return buffer

    def _send_command(self, opcode, param_1, param_2=0x00, data=""):
        """Sends a security command packet over i2c.
        :param byte opcode: The command Opcode
        :param byte param_1: The first parameter
        :param byte param_2: The second parameter, can be two bytes.
        :param byte param_3 data: Optional remaining input data.
        """
        # assembling command packet
        command_packet = bytearray(8 + len(data))
        # word address
        command_packet[0] = 0x03
        # i/o group: count
        command_packet[1] = len(command_packet) - 1  # count
        # security command packets
        command_packet[2] = opcode
        command_packet[3] = param_1
        command_packet[4] = param_2 & 0xFF
        command_packet[5] = param_2 >> 8
        for i, cmd in enumerate(data):
            command_packet[6 + i] = cmd
        # Checksum, CRC16 verification
        crc = self._at_crc(command_packet[1:-2])
        command_packet[-1] = crc >> 8
        command_packet[-2] = crc & 0xFF
        if self._debug:
            print("Command Packet Sz: ", len(command_packet))
            print("\tSending:", [hex(i) for i in command_packet])

        self.wakeup()
        w_msg = i2c_msg.write(self._address, command_packet)
        self._i2c.i2c_rdwr(w_msg)

        # small sleep
        time.sleep(0.001)

    def _get_response(self, length, retries=20):
        self.wakeup()
        for _ in range(retries):
            try:
                r_msg = i2c_msg.read(self._address, length + 3)
                self._i2c.i2c_rdwr(r_msg)
                response = list(r_msg)
                break
            except OSError:
                pass
        else:
            raise RuntimeError("Failed to read data from chip")
        if self._debug:
            print("\tReceived: ", [hex(i) for i in response])
        crc = response[-2] | (response[-1] << 8)
        crc2 = self._at_crc(response[0:-2])
        if crc != crc2:
            raise RuntimeError("CRC Mismatch")
        return response[1:-2]

    @staticmethod
    def _at_crc(data, length=None):
        if length is None:
            length = len(data)
        if not data or not length:
            return 0
        polynom = 0x8005
        crc = 0x0
        for b in data:
            for shift in range(8):
                data_bit = 0
                if b & (1 << shift):
                    data_bit = 1
                crc_bit = (crc >> 15) & 0x1
                crc <<= 1
                crc &= 0xFFFF
                if data_bit != crc_bit:
                    crc ^= polynom
                    crc &= 0xFFFF
        return crc & 0xFFFF