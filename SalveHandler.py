

from PyQt5 import QtWidgets, QtCore
import threading
from ModbusContext import SimpleModbusContext
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


# --------------------- Slave runtime (server in thread) ---------------------
class SlaveRuntime(QtCore.QObject):
    status_changed = QtCore.pyqtSignal(str)

    def __init__(self, slave_def):
        super().__init__()
        self.slave_def = slave_def
        self.context = SimpleModbusContext()
        self._thread = None
        self._running = False
        self._stop_event = threading.Event()

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        self.status_changed.emit('starting')

    def stop(self):
        self._running = False
        self._stop_event.set()
        self.status_changed.emit('stopped')

    def _run_server(self):
        kind = self.slave_def.get('type')
        unit = int(self.slave_def.get('unit_id', 1))

        identity = ModbusDeviceIdentification()
        identity.VendorName = self.slave_def.get('name', 'PyQtModbusSim')
        identity.ProductCode = 'PM'
        identity.VendorUrl = 'https://example.local'
        identity.ProductName = self.slave_def.get('name', 'Simulator')
        identity.ModelName = 'PyQt Modbus Slave'
        identity.MajorMinorRevision = '2.0'

        server_context = ModbusServerContext(slaves={unit: self.context.store}, single=False)

        try:
            if kind == 'tcp':
                host = self.slave_def.get('host', '0.0.0.0')
                port = int(self.slave_def.get('port', 5020))
                self.status_changed.emit(f'listening {host}:{port}')
                StartTcpServer(context=server_context, identity=identity, address=(host, port))
                
            elif kind == 'serial':
                port = self.slave_def.get('port')
                baudrate = int(self.slave_def.get('baudrate', 9600))
                parity = self.slave_def.get('parity', 'N')
                bytesize = int(self.slave_def.get('bytesize', 8))
                stopbits = int(self.slave_def.get('stopbits', 1))
                self.status_changed.emit(f'listening serial {port}@{baudrate}')
                
                StartSerialServer(
                    context=server_context,
                    identity=identity,
                    port=port,
                    parity=parity,
                    bytesize=bytesize,
                    baudrate=baudrate,
                    stopbits=stopbits,
                    timeout=1
                )
            else:
                self.status_changed.emit('unknown type')
        except Exception as e:
            self.status_changed.emit(f'error: {e}')
            print(f"Server error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._running = False
            self.status_changed.emit('stopped')

    def set_register(self, table, address, value):
        self.context.set(table, address, value)

    def get_register(self, table, address):
        return self.context.get(table, address)

# ----- Dialogs -----
class SlaveDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Modbus Slave')
        self.resize(400, 400)
        layout = QtWidgets.QFormLayout(self)
        
        self.name_edit = QtWidgets.QLineEdit('slave1')
        
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(['tcp', 'serial'])
        
        self.unit_edit = QtWidgets.QSpinBox()
        self.unit_edit.setRange(1, 247)
        self.unit_edit.setValue(1)

        # TCP fields
        self.tcp_host = QtWidgets.QLineEdit('0.0.0.0')
        self.tcp_port = QtWidgets.QSpinBox()
        self.tcp_port.setRange(1, 65535)
        self.tcp_port.setValue(5020)

        # Serial fields
        self.serial_port = QtWidgets.QLineEdit('/dev/ttyUSB0')
        self.serial_baud = QtWidgets.QComboBox()
        self.serial_baud.addItems(['9600', '19200', '38400', '57600', '115200'])

        self.serial_parity = QtWidgets.QComboBox()
        self.serial_parity.addItems(['N', 'E', 'O', 'M', 'S'])

        self.serial_bytesize = QtWidgets.QComboBox()
        self.serial_bytesize.addItems(['7', '8'])
        self.serial_bytesize.setCurrentText('8')

        self.serial_stopbits = QtWidgets.QComboBox()
        self.serial_stopbits.addItems(['1', '2'])

        layout.addRow('Name:', self.name_edit)
        layout.addRow('Type:', self.type_combo)
        layout.addRow('Unit ID:', self.unit_edit)
        layout.addRow('', QtWidgets.QLabel(''))
        layout.addRow('<b>TCP Settings</b>', QtWidgets.QLabel(''))
        layout.addRow('Host:', self.tcp_host)
        layout.addRow('Port:', self.tcp_port)
        layout.addRow('', QtWidgets.QLabel(''))
        layout.addRow('<b>Serial Settings</b>', QtWidgets.QLabel(''))
        layout.addRow('Port:', self.serial_port)
        layout.addRow('Baudrate:', self.serial_baud)
        layout.addRow('Parity:', self.serial_parity)
        layout.addRow('Bytesize:', self.serial_bytesize)
        layout.addRow('Stopbits:', self.serial_stopbits)

        btns = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        self.bb = QtWidgets.QDialogButtonBox(btns)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        layout.addWidget(self.bb)

        self.type_combo.currentTextChanged.connect(self.on_type)
        self.on_type(self.type_combo.currentText())

    def on_type(self, t):
        is_tcp = (t == 'tcp')
        self.tcp_host.setEnabled(is_tcp)
        self.tcp_port.setEnabled(is_tcp)
        self.serial_port.setEnabled(not is_tcp)
        self.serial_baud.setEnabled(not is_tcp)
        self.serial_parity.setEnabled(not is_tcp)
        self.serial_stopbits.setEnabled(not is_tcp)
        self.serial_bytesize.setEnabled(not is_tcp)

    def get_data(self):
        data = {
            'name': self.name_edit.text(),
            'type': self.type_combo.currentText(),
            'unit_id': int(self.unit_edit.value()),
            'registers': [],
        }
        if data['type'] == 'tcp':
            data['host'] = self.tcp_host.text()
            data['port'] = int(self.tcp_port.value())
        else:
            data['port'] = self.serial_port.text()
            data['baudrate'] = int(self.serial_baud.currentText())
            data['parity'] = self.serial_parity.currentText()
            data['bytesize'] = int(self.serial_bytesize.currentText())
            data['stopbits'] = int(self.serial_stopbits.currentText())
        return data
