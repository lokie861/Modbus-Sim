"""
Enhanced PyQt5 Modbus Simulator (TCP + Serial) with Data Types & Auto-Refresh

Features:
- Create TCP or Serial (RTU) Modbus slaves with custom unit id and connection settings.
- Add registers with multiple data types (uint16, int32, uint32, float32, int64, uint64, double64, string)
- Big/Little endian support for multi-register data types
- Auto-refresh option to continuously update register values
- Start/Stop slaves; interactive table to view and control register values.
- Save/load full simulator configuration to custom .mbsim format (JSON-based)

Requirements:
- Python 3.8+
- PyQt5
- pymodbus>=3.0.0
- pyserial (for serial RTU)

Install:
pip install pyqt5 pymodbus pyserial

Run:
python enhanced_modbus_simulator.py
"""

import sys
import json
import threading
from functools import partial
from Converstion import TypeConversions
from SalveHandler import SlaveRuntime, SlaveDialog
from RegisterDialog import RegisterDialog
from PyQt5 import QtWidgets, QtCore


# --------------------- PyQt GUI ---------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PyQt5 Modbus Simulator - Enhanced')
        self.resize(1400, 800)
        self.showMaximized()
        
        # state
        self.slaves = []
        self.runtimes = {}
        self.converter = TypeConversions()
        
        # Auto-refresh
        self.auto_refresh_enabled = False
        self.refresh_timer = QtCore.QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh_registers)

        # Search 
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText('Search registers...')
        self.search_box.textChanged.connect(self.search_refresh_table_values)

        # UI
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        h = QtWidgets.QHBoxLayout(central)

        # Left panel
        left = QtWidgets.QVBoxLayout()
        h.addLayout(left, 2)

        left.addWidget(QtWidgets.QLabel('<b>Modbus Slaves</b>'))
        
        self.slave_list = QtWidgets.QListWidget()
        left.addWidget(self.slave_list)

        add_btn = QtWidgets.QPushButton('➕ Add Slave')
        add_btn.clicked.connect(self.add_slave_dialog)
        left.addWidget(add_btn)


        start_btn = QtWidgets.QPushButton('▶ Start Selected')
        start_btn.clicked.connect(self.start_selected_slave)
        left.addWidget(start_btn)

        stop_btn = QtWidgets.QPushButton('⏹ Stop Selected')
        stop_btn.clicked.connect(self.stop_selected_slave)
        left.addWidget(stop_btn)

        edit_slave = QtWidgets.QPushButton('📝 Edit Selected')
        edit_slave.clicked.connect(self.edit_selected_slave)
        left.addWidget(edit_slave)

        remove_btn = QtWidgets.QPushButton('🗑 Remove Selected')
        remove_btn.clicked.connect(self.remove_selected_slave)
        left.addWidget(remove_btn)

        left.addWidget(QtWidgets.QLabel(''))

        save_btn = QtWidgets.QPushButton('💾 Save Config')
        save_btn.clicked.connect(self.save_config)
        left.addWidget(save_btn)

        load_btn = QtWidgets.QPushButton('📂 Load Config')
        load_btn.clicked.connect(self.load_config)
        left.addWidget(load_btn)

        # Right panel
        right = QtWidgets.QVBoxLayout()
        h.addLayout(right, 4)
        self.current_label = QtWidgets.QLabel('<i>Select a slave to edit registers</i>')
        right.addWidget(self.current_label)

        # Auto-refresh controls
        refresh_control = QtWidgets.QHBoxLayout()
        self.auto_refresh_check = QtWidgets.QCheckBox('Auto-Refresh')
        self.auto_refresh_check.stateChanged.connect(self.toggle_auto_refresh)
        refresh_control.addWidget(self.auto_refresh_check)
        
        refresh_control.addWidget(QtWidgets.QLabel('Interval (ms):'))
        self.refresh_interval = QtWidgets.QSpinBox()
        self.refresh_interval.setRange(100, 10000)
        self.refresh_interval.setValue(1000)
        self.refresh_interval.setSingleStep(100)
        self.refresh_interval.valueChanged.connect(self.update_refresh_interval)
        refresh_control.addWidget(self.refresh_interval)
        refresh_control.addStretch()
        
        right.addLayout(refresh_control)
        right.addWidget(self.search_box)

        # Table
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            'Address', 'Type', 'Data Type', 'Endian', 'Name', 'Value', 'Writable', 'Actions'
        ])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
        right.addWidget(self.table)

        btn_layout = QtWidgets.QHBoxLayout()
        add_reg_btn = QtWidgets.QPushButton('➕ Add Register')
        add_reg_btn.clicked.connect(self.add_register_dialog)
        btn_layout.addWidget(add_reg_btn)

        refresh_btn = QtWidgets.QPushButton('🔄 Refresh Values')
        refresh_btn.clicked.connect(self.refresh_table_values)
        btn_layout.addWidget(refresh_btn)

        edit_reg_btn = QtWidgets.QPushButton('📝 Edit Selected')
        edit_reg_btn.clicked.connect(self.edit_selected_register)
        btn_layout.addWidget(edit_reg_btn)

        remove_reg_btn = QtWidgets.QPushButton('🗑 Remove Selected')
        remove_reg_btn.clicked.connect(self.remove_selected_register)
        btn_layout.addWidget(remove_reg_btn)


        right.addLayout(btn_layout)

        self.statusBar().showMessage('Ready')
        self.slave_list.currentItemChanged.connect(self.on_slave_selected)
    


    # ----- Auto-refresh methods -----
    def toggle_auto_refresh(self, state):
        self.auto_refresh_enabled = (state == QtCore.Qt.Checked)
        if self.auto_refresh_enabled:
            self.refresh_timer.start(self.refresh_interval.value())
            self.statusBar().showMessage('Auto-refresh enabled')
        else:
            self.refresh_timer.stop()
            self.statusBar().showMessage('Auto-refresh disabled')

    def update_refresh_interval(self, value):
        if self.auto_refresh_enabled:
            self.refresh_timer.setInterval(value)

    def auto_refresh_registers(self):
        """Called by timer to refresh register values"""
        if self.slave_list.currentRow() >= 0:
            self.refresh_table_values(silent=True)

    # ----- Slave management -----
    def add_slave_dialog(self):
        dlg = SlaveDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            s = dlg.get_data()
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
        name = item.text().split(' (')[0]
        
        rt = self.runtimes.get(name)
        if rt:
            rt.stop()
            del self.runtimes[name]
        del self.slaves[cur]
        self.update_slave_list()
        self.table.setRowCount(0)
        self.current_label.setText('<i>Select a slave to edit registers</i>')
        self.statusBar().showMessage(f"Removed slave: {name}")

    def edit_selected_slave(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'No slave selected')
            return

        slave = self.slaves[cur]

        # Prevent editing while running
        if slave['name'] in self.runtimes:
            QtWidgets.QMessageBox.warning(
                self, 'Warning',
                'Stop the slave before editing its settings.'
            )
            return

        dlg = SlaveDialog(self)

        # Pre-fill dialog fields with existing data
        dlg.setWindowTitle(f"Edit Slave: {slave['name']}")
        dlg.name_edit.setText(slave.get('name', ''))

        dlg.type_combo.setCurrentText(slave.get('type', 'tcp'))
        dlg.unit_edit.setValue(int(slave.get('unit_id', 1)))

        if slave.get('type') == 'tcp':
            dlg.tcp_host.setText(slave.get('host', '0.0.0.0'))
            dlg.tcp_port.setValue(int(slave.get('port', 5020)))
        else:
            dlg.serial_port.setText(slave.get('port', 'COM1'))
            dlg.serial_baud.setCurrentText(str(slave.get('baudrate', 9600)))
            dlg.serial_parity.setCurrentText(slave.get('parity', 'N'))
            dlg.serial_bytesize.setCurrentText(str(slave.get('bytesize', 8)))
            dlg.serial_stopbits.setCurrentText(str(slave.get('stopbits', 1)))

        # --- Accept dialog updates ---
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            updated = dlg.get_data()

            # Keep registers unchanged
            updated['registers'] = slave.get('registers', [])

            # Check name conflict if name changed
            if updated['name'] != slave['name'] and any(
                s['name'] == updated['name'] for s in self.slaves
            ):
                QtWidgets.QMessageBox.warning(
                    self, 'Warning', 'A slave with this name already exists'
                )
                return

            self.slaves[cur] = updated
            self.update_slave_list()
            self.statusBar().showMessage(f"Updated slave: {updated['name']}")


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
        
        # Load registers with proper data type handling
        for reg in slave.get('registers', []):
            self.write_register_value(rt, reg, reg.get('value', 0))
        
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
        
        if 0 <= current_row < self.slave_list.count():
            self.slave_list.setCurrentRow(current_row)

    def on_status_changed(self, name, status):
        self.update_slave_list()
        self.statusBar().showMessage(f"{name}: {status}")

    # ----- Register data type handling -----

    def get_register_size(self, data_type):
        """Return number of registers needed for data type"""
        sizes = {
            'uint16': 1, 'int32': 2, 'uint32': 2, 'float32': 2,
            'int64': 4, 'uint64': 4, 'double64': 4
        }
        return sizes.get(data_type, 1)

    def write_register_value(self, rt, reg, value):
        """Write value to registers based on data type"""
        table = reg['table']
        addr = int(reg['address'])
        data_type = reg.get('data_type', 'uint16')
        endian = reg.get('endian', 'big')
        inverse = (endian == 'big')
        
        try:
            if data_type == 'uint16':
                rt.set_register(table, addr, int(value))
            elif data_type == 'int32':
                words = self.converter.from_int32(int(value), inverse)
                for i, w in enumerate(words):
                    rt.set_register(table, addr + i, w)
            elif data_type == 'uint32':
                words = self.converter.from_uint32(int(value), inverse)
                for i, w in enumerate(words):
                    rt.set_register(table, addr + i, w)
            elif data_type == 'float32':
                words = self.converter.from_float32(float(value), inverse)
                for i, w in enumerate(words):
                    rt.set_register(table, addr + i, w)
            elif data_type == 'int64':
                words = self.converter.from_long64(int(value), inverse)
                for i, w in enumerate(words):
                    rt.set_register(table, addr + i, w)
            elif data_type == 'uint64':
                words = self.converter.from_ulong64(int(value), inverse)
                for i, w in enumerate(words):
                    rt.set_register(table, addr + i, w)
            elif data_type == 'double64':
                words = self.converter.from_double64(float(value), inverse)
                for i, w in enumerate(words):
                    rt.set_register(table, addr + i, w)
            elif data_type == 'string':
                words = self.converter.from_string(str(value), inverse)
                for i, w in enumerate(words):
                    rt.set_register(table, addr + i, w)
        except Exception as e:
            print(f"Error writing register: {e}")

    def read_register_value(self, rt, reg):
        """Read value from registers based on data type"""
        table = reg['table']
        addr = int(reg['address'])
        data_type = reg.get('data_type', 'uint16')
        endian = reg.get('endian', 'big')
        inverse = (endian == 'big')
        
        try:
            if data_type == 'uint16':
                return rt.get_register(table, addr)
            
            size = self.get_register_size(data_type)
            words = []
            for i in range(size):
                w = rt.get_register(table, addr + i)
                if w is None:
                    return None
                words.append(w)
            
            if data_type == 'int32':
                return self.converter.to_int32(words, 0, inverse)
            elif data_type == 'uint32':
                return self.converter.to_uint32(words, 0, inverse)
            elif data_type == 'float32':
                return self.converter.to_float32(words, 0, inverse)
            elif data_type == 'int64':
                return self.converter.to_long64(words, 0, inverse)
            elif data_type == 'uint64':
                return self.converter.to_ulong64(words, 0, inverse)
            elif data_type == 'double64':
                return self.converter.to_double64(words, 0, inverse)
            elif data_type == 'string':
                return self.converter.to_string(words, inverse)
        except Exception as e:
            print(f"Error reading register: {e}")
            return None

    # ----- Register management -----
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
        
        dtype_item = QtWidgets.QTableWidgetItem(reg.get('data_type', 'uint16'))
        dtype_item.setFlags(dtype_item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        endian_item = QtWidgets.QTableWidgetItem(reg.get('endian', 'big'))
        endian_item.setFlags(endian_item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        name_item = QtWidgets.QTableWidgetItem(reg.get('name', ''))
        name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        value_item = QtWidgets.QTableWidgetItem(str(reg.get('value', 0)))
        
        writable_item = QtWidgets.QTableWidgetItem('✓ Yes' if reg.get('writable', False) else '✗ No')
        writable_item.setFlags(writable_item.flags() & ~QtCore.Qt.ItemIsEditable)

        self.table.setItem(row, 0, addr_item)
        self.table.setItem(row, 1, type_item)
        self.table.setItem(row, 2, dtype_item)
        self.table.setItem(row, 3, endian_item)
        self.table.setItem(row, 4, name_item)
        self.table.setItem(row, 5, value_item)
        self.table.setItem(row, 6, writable_item)

        btn = QtWidgets.QPushButton('Apply')
        btn.clicked.connect(partial(self.apply_table_row, row))
        self.table.setCellWidget(row, 7, btn)

    def add_register_dialog(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'Select a slave first')
            return
        dlg = RegisterDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            r = dlg.get_data()
            slave = self.slaves[cur]
            
            # Check for overlapping addresses
            reg_size = self.get_register_size(r['data_type'])
            new_range = range(r['address'], r['address'] + reg_size)
            
            for reg in slave.get('registers', []):
                if reg['table'] != r['table']:
                    continue
                existing_size = self.get_register_size(reg.get('data_type', 'uint16'))
                existing_range = range(reg['address'], reg['address'] + existing_size)
                
                if any(addr in existing_range for addr in new_range):
                    QtWidgets.QMessageBox.warning(
                        self, 'Warning', 
                        f"Address range overlaps with existing register at {reg['table'].upper()}:{reg['address']}"
                    )
                    return
            
            slave.setdefault('registers', []).append(r)
            
            rt = self.runtimes.get(slave['name'])
            if rt:
                self.write_register_value(rt, r, r.get('value', 0))
            
            self.populate_table(slave)
            self.statusBar().showMessage(f"Added register: {r['table'].upper()}:{r['address']} ({r['data_type']})")

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

    def edit_selected_register(self):
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
        dlg = RegisterDialog(self, reg)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            r = dlg.get_data()
            regs[reg_row] = r
            
            rt = self.runtimes.get(slave['name'])
            if rt:
                self.write_register_value(rt, r, r.get('value', 0))
            
            self.populate_table(slave)
            self.statusBar().showMessage(f"Edited register: {r['table'].upper()}:{r['address']}")



    def apply_table_row(self, row):
        cur = self.slave_list.currentRow()
        if cur < 0:
            return
        slave = self.slaves[cur]
        regs = slave.get('registers', [])
        if row >= len(regs):
            return
        reg = regs[row]
        val_item = self.table.item(row, 5)
        if not val_item:
            return
        
        try:
            val_text = val_item.text()
            data_type = reg.get('data_type', 'uint16')
            
            # Validate based on data type
            if data_type in ['float32', 'double64']:
                value = float(val_text)
            elif data_type == 'string':
                value = val_text
            else:
                value = int(val_text)
                
        except ValueError:
            QtWidgets.QMessageBox.warning(self, 'Warning', f'Invalid value for {data_type}')
            return
        
        reg['value'] = value
        
        rt = self.runtimes.get(slave['name'])
        if rt:
            self.write_register_value(rt, reg, value)
            self.statusBar().showMessage(f"Applied: {reg['table'].upper()}:{reg['address']} = {value}")
        else:
            self.statusBar().showMessage(f"Updated (not running): {reg['table'].upper()}:{reg['address']} = {value}")

    def refresh_table_values(self, silent=False):
        cur = self.slave_list.currentRow()
        if cur < 0:
            return
        slave = self.slaves[cur]
        rt = self.runtimes.get(slave['name'])
        
        if not rt:
            if not silent:
                QtWidgets.QMessageBox.information(self, 'Info', 'Slave is not running')
            return
        
        regs = slave.get('registers', [])
        for i, reg in enumerate(regs):
            v = self.read_register_value(rt, reg)
            if v is not None:
                reg['value'] = v
                item = self.table.item(i, 5)
                if item:
                    item.setText(str(v))
        
        if not silent:
            self.statusBar().showMessage('Values refreshed from running slave')

    def search_refresh_table_values(self, silent: bool = False):
        search_text = self.search_box.text().strip().lower()
        current_index = self.slave_list.currentRow()
        if current_index < 0:
            return

        slave = self.slaves[current_index]
        runtime = self.runtimes.get(slave['name'])

        # If no search → show all registers
        if not search_text:
            self.populate_table(slave)
            return

        filtered_regs = []
        for reg in slave.get('registers', []):
            if search_text in reg.get('name', '').lower():
                filtered_regs.append(reg)

        # Update table with filtered registers only
        self.table.setRowCount(0)
        for reg in filtered_regs:
            self._add_table_row(reg)

        if not silent:
            self.statusBar().showMessage(f"Filtered: {len(filtered_regs)} matches")

    # ----- Save/Load with custom format -----
    def save_config(self):
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Configuration', '', 'Modbus Simulator Files (*.mbsim);;All Files (*)'
        )
        if not fname:
            return
        
        # Add .mbsim extension if not present
        if not fname.endswith('.mbsim'):
            fname += '.mbsim'
            
        try:
            config = {
                'version': '2.0',
                'format': 'modbus_simulator_config',
                'slaves': self.slaves,
                'settings': {
                    'auto_refresh': self.auto_refresh_enabled,
                    'refresh_interval': self.refresh_interval.value()
                }
            }
            with open(fname, 'w') as f:
                json.dump(config, f, indent=2)
            QtWidgets.QMessageBox.information(self, 'Saved', f'Configuration saved to:\n{fname}')
            self.statusBar().showMessage(f"Saved: {fname}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to save:\n{e}')

    def load_config(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load Configuration', '', 'Modbus Simulator Files (*.mbsim);;JSON Files (*.json);;All Files (*)'
        )
        if not fname:
            return
        try:
            with open(fname, 'r') as f:
                config = json.load(f)
            
            # Stop all running slaves
            for name, rt in list(self.runtimes.items()):
                rt.stop()
            self.runtimes.clear()
            
            # Load slaves
            self.slaves = config.get('slaves', [])
            
            # Load settings if available
            settings = config.get('settings', {})
            if 'auto_refresh' in settings:
                self.auto_refresh_check.setChecked(settings['auto_refresh'])
            if 'refresh_interval' in settings:
                self.refresh_interval.setValue(settings['refresh_interval'])
            
            self.update_slave_list()
            self.table.setRowCount(0)
            self.current_label.setText('<i>Select a slave to edit registers</i>')
            
            version = config.get('version', '1.0')
            QtWidgets.QMessageBox.information(
                self, 'Loaded', 
                f'Configuration loaded from:\n{fname}\nVersion: {version}'
            )
            self.statusBar().showMessage(f"Loaded: {fname}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to load:\n{e}')





# --------------------- Main ---------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()