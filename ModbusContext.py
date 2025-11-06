# pymodbus imports (3.x)
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext, ModbusSequentialDataBlock
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartTcpServer, StartSerialServer

# try to import framer paths robustly (keeps compatibility across pymodbus versions)
try:
    from pymodbus.transaction import ModbusRtuFramer, ModbusAsciiFramer
except Exception:
    try:
        from pymodbus.framer.rtu_framer import ModbusRtuFramer
        from pymodbus.framer.ascii_framer import ModbusAsciiFramer
    except Exception:
        from pymodbus.framer import ModbusRtuFramer, ModbusAsciiFramer

# ------------------------------
# Dynamic data block (unbounded)
# ------------------------------
class DynamicDataBlock(ModbusSequentialDataBlock):
    """
    A ModbusSequentialDataBlock that auto-expands on writes and returns zeros for out-of-range reads.
    Addressing is zero-based.
    """
    def __init__(self, address=0, values=None):
        if values is None:
            values = []
        # ModbusSequentialDataBlock stores values in self.values and self.address
        super().__init__(address, list(values))

    def validate(self, address, count=1):
        # allow any address >= base address; reads beyond current length are allowed (zeros returned)
        if address < self.address:
            return False
        return True

    def getValues(self, address, count=1):
        start = address - self.address
        if start < 0:
            raise IndexError("Address before block start")
        end = start + count
        # when reading beyond current list, pad with zeros
        if end <= len(self.values):
            return self.values[start:end]
        else:
            vals = self.values[start:] if start < len(self.values) else []
            vals.extend([0] * (count - len(vals)))
            return vals

    def setValues(self, address, values):
        if isinstance(values, int):
            values = [values]
        start = address - self.address
        if start < 0:
            raise IndexError("Address before block start")
        end = start + len(values)
        # grow underlying list if needed (unbounded)
        if end > len(self.values):
            self.values.extend([0] * (end - len(self.values)))
        for i, v in enumerate(values):
            self.values[start + i] = int(v)


# ------------------------------
# SimpleModbusContext (dynamic)
# ------------------------------
class SimpleModbusContext:
    """Wrap ModbusSlaveContext to provide easy set/get and use dynamic blocks."""
    def __init__(self, initial_block_size=1000):
        self.block_size = initial_block_size

        di_block = DynamicDataBlock(0, [0] * self.block_size)
        co_block = DynamicDataBlock(0, [0] * self.block_size)
        hr_block = DynamicDataBlock(0, [0] * self.block_size)
        ir_block = DynamicDataBlock(0, [0] * self.block_size)

        self.store = ModbusSlaveContext(
            di=di_block,
            co=co_block,
            hr=hr_block,
            ir=ir_block,
            zero_mode=True
        )

    def set(self, table, address, value):
        fx_map = {'co': 1, 'di': 2, 'hr': 3, 'ir': 4}
        fx = fx_map.get(table)
        if fx is None:
            raise KeyError(f"Invalid table: {table}")
        # ModbusSlaveContext.setValues expects (fx, address, list_of_values)
        try:
            self.store.setValues(fx, address, [int(value)])
        except Exception as e:
            print(f"Failed to set {table}[{address}] = {value}: {e}")
            raise

    def get(self, table, address):
        fx_map = {'co': 1, 'di': 2, 'hr': 3, 'ir': 4}
        fx = fx_map.get(table)
        if fx is None:
            raise KeyError(f"Invalid table: {table}")
        try:
            r = self.store.getValues(fx, address, count=1)
            return r[0] if r else None
        except Exception as e:
            print(f"Failed to get {table}[{address}]: {e}")
            raise