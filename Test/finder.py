from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.framer import ModbusAsciiFramer, ModbusRtuFramer
import itertools
import time

SERIAL_PORT = "COM6"          # adjust
SLAVE_ID = 1
REGISTER_ADDRESS = 0
REGISTER_COUNT = 1
TIMEOUT = 0.5

baudrates = [9600]
parities = ["N"]
databits = [ 8]
stopbits = [1]

framers = {
    "rtu": ModbusRtuFramer,
    "ascii": ModbusAsciiFramer,
}

def try_modbus_combination(baudrate, parity, databits, stopbits, framer_name, framer_cls):
    print(
        f"Trying: baud={baudrate}, parity={parity}, "
        f"data={databits}, stop={stopbits}, framer={framer_name}"
    )

    client = ModbusSerialClient(
        port=SERIAL_PORT,
        baudrate=baudrate,
        parity=parity,
        bytesize=databits,
        stopbits=stopbits,
        timeout=TIMEOUT,
        framer=framer_cls,
    )

    try:
        if not client.connect():
            return False

        result = client.read_holding_registers(
            address=REGISTER_ADDRESS,
            count=REGISTER_COUNT,
            slave=SLAVE_ID,
        )

        if result and not result.isError():
            print("✅ SUCCESS!", result.registers)
            return True

    except (ModbusException, Exception):
        pass
    finally:
        client.close()

    return False


def main():
    for baud, parity, data, stop, (fname, fcls) in itertools.product(
        baudrates, parities, databits, stopbits, framers.items()
    ):
        if try_modbus_combination(baud, parity, data, stop, fname, fcls):
            print("\n🎯 WORKING CONFIG FOUND")
            return
        time.sleep(0.1)

    print("\n❌ No valid configuration found")


if __name__ == "__main__":
    main()
