import threading
import time
from PyQt5 import QtCore, QtWidgets
from pymodbus.server import StartTcpServer, StartSerialServer, ServerStop
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.transaction import ModbusRtuFramer, ModbusAsciiFramer
from ModbusContext import SimpleModbusContext

from pymodbus.pdu import ModbusPDU

class SlaveRuntime(QtCore.QObject):
    status_changed = QtCore.pyqtSignal(str)

    def __init__(self, slave_def):
        super().__init__()
        self.slave_def = slave_def
        self.context = SimpleModbusContext()

        self._thread = None
        self._running = False
        self._stop_event = threading.Event()
        self._shutdown_complete = threading.Event()

    # -----------------------
    # Public API
    # -----------------------
    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._shutdown_complete.clear()
        self._thread = threading.Thread(target=self._run_server_thread, daemon=True)
        self._thread.start()
        self.status_changed.emit("starting")

    def stop(self):
        print("Stop requested...")
        self._running = False
        self._stop_event.set()
        ServerStop()
        # Wait for graceful shutdown
        if self._shutdown_complete.wait(timeout=0.1):
            print("Server shutdown gracefully")
        else:
            print("WARNING: Server shutdown timeout")

        # Wait for worker thread
        if self._thread and self._thread.is_alive():
            print("Waiting for worker thread to exit...")
            self._thread.join(timeout=0.1)
            if self._thread.is_alive():
                print("WARNING: worker thread still alive after join timeout")

        time.sleep(0.1)  # allow COM port release
        self.status_changed.emit("stopped")
        print("Stop complete")

    # -----------------------
    # Internal: worker thread
    # -----------------------
    def _run_server_thread(self):
        kind = self.slave_def.get("type", "tcp")
        unit = int(self.slave_def.get("unit_id", 1))

        identity = ModbusDeviceIdentification()
        identity.VendorName = self.slave_def.get("name", "PyQtModbusSim")
        identity.ProductCode = "PM"
        identity.VendorUrl = "https://example.local"
        identity.ProductName = self.slave_def.get("name", "Simulator")
        identity.ModelName = "PyQt Modbus Slave"
        identity.MajorMinorRevision = "2.0"

        server_context = ModbusServerContext(slaves={unit: self.context.store}, single=False)

        try:
            if kind == "tcp":
                self._run_tcp_server(unit, identity, server_context)
            elif kind == "serial":
                self._run_serial_server(unit, identity, server_context)
        finally:
            self._running = False
            self._shutdown_complete.set()

    def _run_tcp_server(self, unit, identity, context):
        host = self.slave_def.get("host", "0.0.0.0")
        port = int(self.slave_def.get("port", 5020))
        self.status_changed.emit(f"Listening TCP {host}:{port}")
        print(f"Starting TCP Server {host}:{port} ...")

        # Synchronous TCP server
        try:
            StartTcpServer(
                context=context,
                identity=identity,
                address=(host, port)
            )
        except Exception as e:
            print(f"TCP server error: {e}")
        finally:
            print("TCP server thread exiting")

    def _run_serial_server(self, unit, identity, context):
        port = self.slave_def.get("port")
        baudrate = int(self.slave_def.get("baudrate", 9600))
        parity = self.slave_def.get("parity", "N")
        bytesize = int(self.slave_def.get("bytesize", 8))
        stopbits = int(self.slave_def.get("stopbits", 1))
        mode = self.slave_def.get("mode", "rtu").lower()
        unit_id = int(self.slave_def.get("unit_id", 1))
        framer_cls = ModbusAsciiFramer if mode == "ascii" else ModbusRtuFramer
        mode_display = "ASCII" if mode == "ascii" else "RTU"

        self.status_changed.emit(f"Listening Serial {mode_display} {port}@{baudrate}")
        print(f"Starting Serial Server {mode_display} ({port}@{baudrate}) ...")

        # Synchronous Serial server
        try:
            """
            classpymodbus.server.ModbusUdpServer(context: ModbusServerContext, *, framer=FramerType.SOCKET, 
            identity: ModbusDeviceIdentification | None = None, address: tuple[str, int] = ('', 502), 
            ignore_missing_devices: bool = False, 
            broadcast_enable: bool = False, 
            trace_packet: Callable[[bool, bytes], bytes] | None = None, 
            trace_pdu: Callable[[bool, ModbusPDU], ModbusPDU] | None = None, 
            trace_connect: Callable[[bool], None] | None = None, 
            custom_pdu: list[type[ModbusPDU]] | None = None)
            """
            pdu_settings= ModbusPDU(
                slave= unit_id,
                skip_encode=False,
                check=True,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
            )
            StartSerialServer(
                context=context,
                framer=framer_cls,
                identity=identity,
                port=port,
                timeout=0.5,
                custom_pdu=pdu_settings,
            )
        except Exception as e:
            print(f"Serial server error: {e}")
        finally:
            print("Serial server thread exiting")

    # -----------------------
    # Register API
    # -----------------------
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

        self.tcp_timout = QtWidgets.QSpinBox()
        self.tcp_timout.setRange(1, 60)
        self.tcp_timout.setValue(5)

        # Serial fields
        self.serial_port = QtWidgets.QComboBox()
        self.serial_port.setEditable(True)

        self.btn_refresh_ports = QtWidgets.QToolButton()
        self.btn_refresh_ports.setText("⟳")
        self.btn_refresh_ports.setToolTip("Refresh Serial Ports")

        port_layout = QtWidgets.QHBoxLayout()
        port_layout.addWidget(self.serial_port)
        port_layout.addWidget(self.btn_refresh_ports)

        port_widget = QtWidgets.QWidget()
        port_widget.setLayout(port_layout)

        self.serial_baud = QtWidgets.QComboBox()
        self.serial_baud.addItems(['9600', '19200', '38400', '57600', '115200'])

        self.serial_parity = QtWidgets.QComboBox()
        self.serial_parity.addItems(['N', 'E', 'O', 'M', 'S'])

        self.serial_bytesize = QtWidgets.QComboBox()
        self.serial_bytesize.addItems(['7', '8'])
        self.serial_bytesize.setCurrentText('8')

        self.serial_stopbits = QtWidgets.QComboBox()
        self.serial_stopbits.addItems(['1', '2'])

        # --- Add Serial Mode (RTU / ASCII) ---
        self.serial_mode_rtu = QtWidgets.QRadioButton("RTU")
        self.serial_mode_ascii = QtWidgets.QRadioButton("ASCII")
        self.serial_mode_rtu.setChecked(True)  # Default to RTU

        serial_mode_layout = QtWidgets.QHBoxLayout()
        serial_mode_layout.addWidget(self.serial_mode_rtu)
        serial_mode_layout.addWidget(self.serial_mode_ascii)

        serial_mode_widget = QtWidgets.QWidget()
        serial_mode_widget.setLayout(serial_mode_layout)

        layout.addRow('Name:', self.name_edit)
        layout.addRow('Type:', self.type_combo)
        layout.addRow('Unit ID:', self.unit_edit)
        layout.addRow('', QtWidgets.QLabel(''))
        layout.addRow('<b>TCP Settings</b>', QtWidgets.QLabel(''))
        layout.addRow('Host:', self.tcp_host)
        layout.addRow('Port:', self.tcp_port)
        layout.addRow('Timeout:', self.tcp_timout)
        layout.addRow('', QtWidgets.QLabel(''))
        layout.addRow('<b>Serial Settings</b>', QtWidgets.QLabel(''))
        layout.addRow('Mode:', serial_mode_widget)      # <-- NEW
        layout.addRow('Port:', port_widget)
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
        self.btn_refresh_ports.clicked.connect(self.scan_serial_ports)
        self.scan_serial_ports()  # Auto-load on dialog open


    def scan_serial_ports(self):
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        
        self.serial_port.clear()
        if not ports:
            self.serial_port.addItem("No Ports Found")
            return
        
        for p in ports:
            # Example: "COM3 - USB-SERIAL CH340"
            name = f"{p.device} - {p.description}"
            self.serial_port.addItem(name, p.device)

        # Set first port as default
        self.serial_port.setCurrentIndex(0)

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
            port_text = self.serial_port.currentText()

            # If user selected auto-detected item, extract real port
            port_data = self.serial_port.currentData()
            data['port'] = port_data if port_data else port_text.split(" - ")[0]
            data['baudrate'] = int(self.serial_baud.currentText())
            data['parity'] = self.serial_parity.currentText()
            data['bytesize'] = int(self.serial_bytesize.currentText())
            data['mode'] = 'rtu' if self.serial_mode_rtu.isChecked() else 'ascii'
            data['stopbits'] = int(self.serial_stopbits.currentText())
        return data


