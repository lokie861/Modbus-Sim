"""
PyQt5 Modbus Simulator (TCP + Serial) using pymodbus

Features:
- Create TCP or Serial (RTU) Modbus slaves with custom unit id and connection settings.
- Add registers (coils, discrete inputs, holding registers, input registers) with address, name, initial value and writable flag.
- Start/Stop slaves; interactive table to view and control register values.
- Save/load full simulator configuration to JSON.

Requirements:
- Python 3.8+
- PyQt5
- pymodbus>=3.0.0
- pyserial (for serial RTU)

Install:
pip install pyqt5 pymodbus pyserial

Run:
python pyqt_modbus_simulator.py
"""

import sys
import json
import threading
from functools import partial

from PyQt5 import QtWidgets, QtCore

# pymodbus imports - updated for pymodbus 3.x
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
        # Try alternative import paths for different pymodbus versions
        from pymodbus.datastore.store import (
            ModbusSequentialDataBlock,
            ModbusSlaveContext, 
            ModbusServerContext
        )
        from pymodbus.device import ModbusDeviceIdentification
        from pymodbus.server import StartTcpServer, StartSerialServer
    except ImportError as e:
        print(f"pymodbus import failed: {e}")
        print("\nTrying to provide more info...")
        try:
            import pymodbus
            print(f"pymodbus version: {pymodbus.__version__}")
            print(f"pymodbus path: {pymodbus.__file__}")
        except:
            pass
        print("\nPlease install: pip install pymodbus==3.5.4 pyserial")
        sys.exit(1)


# --------------------- Helper: Modbus context wrapper ---------------------
class SimpleModbusContext:
    """Wrap ModbusSlaveContext to provide easy set/get and serialization."""
    def __init__(self):
        # allocate 0..999 by default (addresses are 0-based)
        self.block_size = 1000
        
        # Create data blocks for each register type
        di_block = ModbusSequentialDataBlock(0, [0] * self.block_size)  # Discrete Inputs
        co_block = ModbusSequentialDataBlock(0, [0] * self.block_size)  # Coils
        hr_block = ModbusSequentialDataBlock(0, [0] * self.block_size)  # Holding Registers
        ir_block = ModbusSequentialDataBlock(0, [0] * self.block_size)  # Input Registers
        
        # Create slave context
        self.store = ModbusSlaveContext(
            di=di_block,
            co=co_block,
            hr=hr_block,
            ir=ir_block,
            zero_mode=True  # Use 0-based addressing
        )

    def set(self, table, address, value):
        # table: 'co', 'di', 'hr', 'ir'
        # Map to pymodbus function codes
        fx_map = {
            'co': 1,  # Coils
            'di': 2,  # Discrete Inputs
            'hr': 3,  # Holding Registers
            'ir': 4,  # Input Registers
        }
        
        try:
            fx = fx_map.get(table)
            if fx is None:
                print(f"Unknown table type: {table}")
                return
                
            if isinstance(value, bool):
                self.store.setValues(fx, address, [int(value)])
            else:
                self.store.setValues(fx, address, [int(value)])
        except Exception as e:
            print(f"Failed to set {table}[{address}] = {value}: {e}")

    def get(self, table, address):
        # Map to pymodbus function codes
        fx_map = {
            'co': 1,  # Coils
            'di': 2,  # Discrete Inputs
            'hr': 3,  # Holding Registers
            'ir': 4,  # Input Registers
        }
        
        try:
            fx = fx_map.get(table)
            if fx is None:
                print(f"Unknown table type: {table}")
                return None
                
            r = self.store.getValues(fx, address, count=1)
            return r[0] if r else None
        except Exception as e:
            print(f"Failed to get {table}[{address}]: {e}")
            return None


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
        identity.MajorMinorRevision = '1.0'

        # Build server context with single slave (unit)
        server_context = ModbusServerContext(slaves={unit: self.context.store}, single=False)

        try:
            if kind == 'tcp':
                host = self.slave_def.get('host', '0.0.0.0')
                port = int(self.slave_def.get('port', 5020))
                self.status_changed.emit(f'listening {host}:{port}')
                
                # StartTcpServer blocks, runs in this thread
                StartTcpServer(
                    context=server_context,
                    identity=identity,
                    address=(host, port)
                )
                
            elif kind == 'serial':
                port = self.slave_def.get('port')
                baudrate = int(self.slave_def.get('baudrate', 9600))
                self.status_changed.emit(f'listening serial {port}@{baudrate}')
                
                StartSerialServer(
                    context=server_context,
                    identity=identity,
                    port=port,
                    baudrate=baudrate,
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


# --------------------- PyQt GUI ---------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PyQt5 Modbus Simulator')
        self.resize(1200, 700)

        # state
        self.slaves = []  # list of dicts
        self.runtimes = {}  # slave_name -> SlaveRuntime

        # UI
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        h = QtWidgets.QHBoxLayout(central)

        # Left: Slave list + controls
        left = QtWidgets.QVBoxLayout()
        h.addLayout(left, 2)

        left.addWidget(QtWidgets.QLabel('<b>Modbus Slaves</b>'))
        
        self.slave_list = QtWidgets.QListWidget()
        left.addWidget(self.slave_list)

        add_btn = QtWidgets.QPushButton('➕ Add Slave')
        add_btn.clicked.connect(self.add_slave_dialog)
        left.addWidget(add_btn)

        remove_btn = QtWidgets.QPushButton('🗑 Remove Selected')
        remove_btn.clicked.connect(self.remove_selected_slave)
        left.addWidget(remove_btn)

        start_btn = QtWidgets.QPushButton('▶ Start Selected')
        start_btn.clicked.connect(self.start_selected_slave)
        left.addWidget(start_btn)

        stop_btn = QtWidgets.QPushButton('⏹ Stop Selected')
        stop_btn.clicked.connect(self.stop_selected_slave)
        left.addWidget(stop_btn)

        left.addWidget(QtWidgets.QLabel(''))  # spacer

        save_btn = QtWidgets.QPushButton('💾 Save Config')
        save_btn.clicked.connect(self.save_config)
        left.addWidget(save_btn)

        load_btn = QtWidgets.QPushButton('📂 Load Config')
        load_btn.clicked.connect(self.load_config)
        left.addWidget(load_btn)

        # Right: Registers editor and table
        right = QtWidgets.QVBoxLayout()
        h.addLayout(right, 4)

        # Slave info label
        self.current_label = QtWidgets.QLabel('<i>Select a slave to edit registers</i>')
        right.addWidget(self.current_label)

        # Table
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Address', 'Type', 'Name', 'Value', 'Writable', 'Actions'])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        right.addWidget(self.table)

        btn_layout = QtWidgets.QHBoxLayout()
        add_reg_btn = QtWidgets.QPushButton('➕ Add Register')
        add_reg_btn.clicked.connect(self.add_register_dialog)
        btn_layout.addWidget(add_reg_btn)

        refresh_btn = QtWidgets.QPushButton('🔄 Refresh Values')
        refresh_btn.clicked.connect(self.refresh_table_values)
        btn_layout.addWidget(refresh_btn)

        remove_reg_btn = QtWidgets.QPushButton('🗑 Remove Selected')
        remove_reg_btn.clicked.connect(self.remove_selected_register)
        btn_layout.addWidget(remove_reg_btn)

        right.addLayout(btn_layout)

        # Status bar
        self.statusBar().showMessage('Ready')

        # signals
        self.slave_list.currentItemChanged.connect(self.on_slave_selected)

    # ----- slave management -----
    def add_slave_dialog(self):
        dlg = SlaveDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            s = dlg.get_data()
            # Check for duplicate names
            if any(slave['name'] == s['name'] for slave in self.slaves):
                QtWidgets.QMessageBox.warning(self, 'Warning', 'A slave with this name already exists')
                return
            self.slaves.append(s)
            self.update_slave_list()
            self.statusBar().showMessage(f"Added slave: {s['name']}")

    def remove_selected_slave(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'No slave selected')
            return
        
        reply = QtWidgets.QMessageBox.question(
            self, 'Confirm', 
            'Are you sure you want to remove this slave?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
            
        item = self.slave_list.item(cur)
        name = item.text().split(' (')[0]  # Extract name before status
        
        # stop if running
        rt = self.runtimes.get(name)
        if rt:
            rt.stop()
            del self.runtimes[name]
        del self.slaves[cur]
        self.update_slave_list()
        self.table.setRowCount(0)
        self.current_label.setText('<i>Select a slave to edit registers</i>')
        self.statusBar().showMessage(f"Removed slave: {name}")

    def start_selected_slave(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'No slave selected')
            return
        slave = self.slaves[cur]
        name = slave['name']
        if name in self.runtimes:
            QtWidgets.QMessageBox.information(self, 'Info', f"Slave '{name}' is already running")
            return
        
        rt = SlaveRuntime(slave)
        rt.status_changed.connect(partial(self.on_status_changed, name))
        
        # load registers if any preconfigured
        for reg in slave.get('registers', []):
            table = reg['table']
            addr = int(reg['address'])
            val = reg.get('value', 0)
            rt.set_register(table, addr, val)
        
        self.runtimes[name] = rt
        rt.start()
        self.update_slave_list()
        self.statusBar().showMessage(f"Started slave: {name}")

    def stop_selected_slave(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'No slave selected')
            return
        slave = self.slaves[cur]
        name = slave['name']
        rt = self.runtimes.get(name)
        if not rt:
            QtWidgets.QMessageBox.information(self, 'Info', f"Slave '{name}' is not running")
            return
        rt.stop()
        del self.runtimes[name]
        self.update_slave_list()
        self.statusBar().showMessage(f"Stopped slave: {name}")

    def update_slave_list(self):
        current_row = self.slave_list.currentRow()
        self.slave_list.clear()
        for s in self.slaves:
            name = s['name']
            status = '🟢 running' if name in self.runtimes else '🔴 stopped'
            stype = s['type'].upper()
            if s['type'] == 'tcp':
                detail = f"{s.get('host', '0.0.0.0')}:{s.get('port', 5020)}"
            else:
                detail = f"{s.get('port', 'COM1')}@{s.get('baudrate', 9600)}"
            item = QtWidgets.QListWidgetItem(f"{name} ({status}) - {stype} {detail}")
            self.slave_list.addItem(item)
        
        # Restore selection
        if 0 <= current_row < self.slave_list.count():
            self.slave_list.setCurrentRow(current_row)

    def on_status_changed(self, name, status):
        # update list display
        self.update_slave_list()
        self.statusBar().showMessage(f"{name}: {status}")

    # ----- register management -----
    def on_slave_selected(self, current, previous):
        row = self.slave_list.currentRow()
        if row < 0:
            self.current_label.setText('<i>Select a slave to edit registers</i>')
            return
        slave = self.slaves[row]
        self.current_label.setText(f"<b>Editing registers for:</b> {slave['name']}")
        self.populate_table(slave)

    def populate_table(self, slave):
        regs = slave.get('registers', [])
        self.table.setRowCount(0)
        for reg in regs:
            self._add_table_row(reg)

    def _add_table_row(self, reg):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        addr_item = QtWidgets.QTableWidgetItem(str(reg['address']))
        addr_item.setFlags(addr_item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        type_item = QtWidgets.QTableWidgetItem(reg['table'].upper())
        type_item.setFlags(type_item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        name_item = QtWidgets.QTableWidgetItem(reg.get('name', ''))
        name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        value_item = QtWidgets.QTableWidgetItem(str(reg.get('value', 0)))
        
        writable_item = QtWidgets.QTableWidgetItem('✓ Yes' if reg.get('writable', False) else '✗ No')
        writable_item.setFlags(writable_item.flags() & ~QtCore.Qt.ItemIsEditable)

        self.table.setItem(row, 0, addr_item)
        self.table.setItem(row, 1, type_item)
        self.table.setItem(row, 2, name_item)
        self.table.setItem(row, 3, value_item)
        self.table.setItem(row, 4, writable_item)

        btn = QtWidgets.QPushButton('Apply')
        btn.clicked.connect(partial(self.apply_table_row, row))
        self.table.setCellWidget(row, 5, btn)

    def add_register_dialog(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'Select a slave first')
            return
        dlg = RegisterDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            r = dlg.get_data()
            slave = self.slaves[cur]
            
            # Check for duplicate address/type combination
            for reg in slave.get('registers', []):
                if reg['address'] == r['address'] and reg['table'] == r['table']:
                    QtWidgets.QMessageBox.warning(
                        self, 'Warning', 
                        f"Register {r['table'].upper()}:{r['address']} already exists"
                    )
                    return
            
            slave.setdefault('registers', []).append(r)
            
            # if running, apply initial value
            rt = self.runtimes.get(slave['name'])
            if rt:
                rt.set_register(r['table'], int(r['address']), r.get('value', 0))
            
            self.populate_table(slave)
            self.statusBar().showMessage(f"Added register: {r['table'].upper()}:{r['address']}")

    def remove_selected_register(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'No slave selected')
            return
        
        reg_row = self.table.currentRow()
        if reg_row < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'No register selected')
            return
        
        slave = self.slaves[cur]
        regs = slave.get('registers', [])
        if reg_row >= len(regs):
            return
        
        reg = regs[reg_row]
        del regs[reg_row]
        self.populate_table(slave)
        self.statusBar().showMessage(f"Removed register: {reg['table'].upper()}:{reg['address']}")

    def apply_table_row(self, row):
        cur = self.slave_list.currentRow()
        if cur < 0:
            return
        slave = self.slaves[cur]
        regs = slave.get('registers', [])
        if row >= len(regs):
            return
        reg = regs[row]
        val_item = self.table.item(row, 3)
        if not val_item:
            return
        try:
            val = int(val_item.text())
            if val < 0 or val > 65535:
                raise ValueError("Value out of range")
        except ValueError:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'Value must be integer (0-65535)')
            return
        
        reg['value'] = val
        
        # if running, set in context
        rt = self.runtimes.get(slave['name'])
        if rt:
            rt.set_register(reg['table'], int(reg['address']), val)
            self.statusBar().showMessage(f"Applied: {reg['table'].upper()}:{reg['address']} = {val}")
        else:
            self.statusBar().showMessage(f"Updated (not running): {reg['table'].upper()}:{reg['address']} = {val}")

    def refresh_table_values(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            return
        slave = self.slaves[cur]
        rt = self.runtimes.get(slave['name'])
        
        if not rt:
            QtWidgets.QMessageBox.information(self, 'Info', 'Slave is not running')
            return
        
        regs = slave.get('registers', [])
        for i, reg in enumerate(regs):
            v = rt.get_register(reg['table'], int(reg['address']))
            if v is not None:
                reg['value'] = v
                item = self.table.item(i, 3)
                if item:
                    item.setText(str(v))
        
        self.statusBar().showMessage('Values refreshed from running slave')

    # ----- save/load -----
    def save_config(self):
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Configuration', '', 'JSON Files (*.json);;All Files (*)'
        )
        if not fname:
            return
        try:
            d = {'slaves': self.slaves}
            with open(fname, 'w') as f:
                json.dump(d, f, indent=2)
            QtWidgets.QMessageBox.information(self, 'Saved', f'Configuration saved to:\n{fname}')
            self.statusBar().showMessage(f"Saved: {fname}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to save:\n{e}')

    def load_config(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load Configuration', '', 'JSON Files (*.json);;All Files (*)'
        )
        if not fname:
            return
        try:
            with open(fname, 'r') as f:
                d = json.load(f)
            
            # Stop all running slaves
            for name, rt in list(self.runtimes.items()):
                rt.stop()
            self.runtimes.clear()
            
            self.slaves = d.get('slaves', [])
            self.update_slave_list()
            self.table.setRowCount(0)
            self.current_label.setText('<i>Select a slave to edit registers</i>')
            QtWidgets.QMessageBox.information(self, 'Loaded', f'Configuration loaded from:\n{fname}')
            self.statusBar().showMessage(f"Loaded: {fname}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load:\n{e}')


# ----- Dialogs -----
class SlaveDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Modbus Slave')
        self.resize(400, 300)
        layout = QtWidgets.QFormLayout(self)
        
        self.name_edit = QtWidgets.QLineEdit('slave1')
        
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(['tcp', 'serial'])
        
        self.unit_edit = QtWidgets.QSpinBox()
        self.unit_edit.setRange(1, 247)
        self.unit_edit.setValue(1)

        # tcp fields
        self.tcp_host = QtWidgets.QLineEdit('0.0.0.0')
        self.tcp_port = QtWidgets.QSpinBox()
        self.tcp_port.setRange(1, 65535)
        self.tcp_port.setValue(5020)

        # serial fields
        self.serial_port = QtWidgets.QLineEdit('/dev/ttyUSB0')
        self.serial_baud = QtWidgets.QComboBox()
        self.serial_baud.addItems(['9600', '19200', '38400', '57600', '115200'])

        layout.addRow('Name:', self.name_edit)
        layout.addRow('Type:', self.type_combo)
        layout.addRow('Unit ID:', self.unit_edit)
        layout.addRow('', QtWidgets.QLabel(''))  # spacer
        layout.addRow('<b>TCP Settings</b>', QtWidgets.QLabel(''))
        layout.addRow('Host:', self.tcp_host)
        layout.addRow('Port:', self.tcp_port)
        layout.addRow('', QtWidgets.QLabel(''))  # spacer
        layout.addRow('<b>Serial Settings</b>', QtWidgets.QLabel(''))
        layout.addRow('Port:', self.serial_port)
        layout.addRow('Baudrate:', self.serial_baud)

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
        return data


class RegisterDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Register')
        self.resize(350, 250)
        layout = QtWidgets.QFormLayout(self)
        
        self.addr = QtWidgets.QSpinBox()
        self.addr.setRange(0, 9999)
        
        self.table = QtWidgets.QComboBox()
        self.table.addItems(['co', 'di', 'hr', 'ir'])
        self.table.setItemData(0, 'Coil (read/write)', QtCore.Qt.ToolTipRole)
        self.table.setItemData(1, 'Discrete Input (read-only)', QtCore.Qt.ToolTipRole)
        self.table.setItemData(2, 'Holding Register (read/write)', QtCore.Qt.ToolTipRole)
        self.table.setItemData(3, 'Input Register (read-only)', QtCore.Qt.ToolTipRole)
        
        self.name = QtWidgets.QLineEdit('register1')
        
        self.value = QtWidgets.QSpinBox()
        self.value.setRange(0, 65535)
        self.value.setValue(0)
        
        self.writable = QtWidgets.QCheckBox()
        self.writable.setChecked(True)

        layout.addRow('Address:', self.addr)
        layout.addRow('Type:', self.table)
        layout.addRow('Name:', self.name)
        layout.addRow('Initial Value:', self.value)
        layout.addRow('Writable:', self.writable)

        btns = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        self.bb = QtWidgets.QDialogButtonBox(btns)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        layout.addWidget(self.bb)

    def get_data(self):
        return {
            'address': int(self.addr.value()),
            'table': self.table.currentText(),
            'name': self.name.text(),
            'value': int(self.value.value()),
            'writable': bool(self.writable.isChecked()),
        }


# --------------------- main ---------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern look
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()