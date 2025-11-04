import sys

try:
    from pymodbus.datastore import (
        ModbusSequentialDataBlock,
        ModbusSlaveContext,
        ModbusServerContext
    )
    from pymodbus.device import ModbusDeviceIdentification
    from pymodbus.server import StartTcpServer, StartSerialServer
except ImportError:
    try:
        from pymodbus.datastore.store import (
            ModbusSequentialDataBlock,
            ModbusSlaveContext, 
            ModbusServerContext
        )
        from pymodbus.device import ModbusDeviceIdentification
        from pymodbus.server import StartTcpServer, StartSerialServer
    except ImportError as e:
        print(f"pymodbus import failed: {e}")
        print("\nPlease install: pip install pymodbus==3.5.4 pyserial")
        sys.exit(1)


# --------------------- Helper: Modbus context wrapper ---------------------
class SimpleModbusContext:
    """Wrap ModbusSlaveContext to provide easy set/get and serialization."""
    def __init__(self):
        self.block_size = 1000
        
        di_block = ModbusSequentialDataBlock(0, [0] * self.block_size)
        co_block = ModbusSequentialDataBlock(0, [0] * self.block_size)
        hr_block = ModbusSequentialDataBlock(0, [0] * self.block_size)
        ir_block = ModbusSequentialDataBlock(0, [0] * self.block_size)
        
        self.store = ModbusSlaveContext(
            di=di_block,
            co=co_block,
            hr=hr_block,
            ir=ir_block,
            zero_mode=True
        )

    def set(self, table, address, value):
        fx_map = {'co': 1, 'di': 2, 'hr': 3, 'ir': 4}
        try:
            fx = fx_map.get(table)
            if fx is None:
                return
            self.store.setValues(fx, address, [int(value)])
        except Exception as e:
            print(f"Failed to set {table}[{address}] = {value}: {e}")

    def get(self, table, address):
        fx_map = {'co': 1, 'di': 2, 'hr': 3, 'ir': 4}
        try:
            fx = fx_map.get(table)
            if fx is None:
                return None
            r = self.store.getValues(fx, address, count=1)
            return r[0] if r else None
        except Exception as e:
            print(f"Failed to get {table}[{address}]: {e}")
            return None

