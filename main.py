"""
Enhanced PyQt5 Modbus Simulator (TCP + Serial) with Data Types & Auto-Refresh

Features:
- Create TCP or Serial (RTU) Modbus slaves with custom unit id and connection settings.
- Add registers with multiple data types (uint16, int32, uint32, float32, int64, uint64, double64, string)
- Big/Little endian support for multi-register data types
- Auto-refresh option to continuously update register values
- Auto value generation modes: Random, Increment, Decrement, Toggle
- Configurable generation parameters: min/max, step size, interval
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

"""
Patches applied to MainWindow (drop-in replacement methods):

FIX 1 & 2  – populate_table batches all row inserts while signals/sorting are
             suspended → O(1) redraws instead of O(n).
             start_selected_slave writes registers in a background thread so the
             UI never freezes while bulk-writing.

FIX 3      – Every table row now stores the ORIGINAL register list index in
             Qt.UserRole on column-0.  apply_table_row, toggle_auto_gen,
             process_auto_gen, and refresh_table_values all resolve the real
             index through that stored value, so search-filtered views work
             correctly.
"""
"""
Patches applied to MainWindow (drop-in replacement methods):

FIX 1 & 2  – populate_table batches all row inserts while signals/sorting are
             suspended → O(1) redraws instead of O(n).
             start_selected_slave writes registers in a background thread so the
             UI never freezes while bulk-writing.

FIX 3      – Every table row now stores the ORIGINAL register list index in
             Qt.UserRole on column-0.  apply_table_row, toggle_auto_gen,
             process_auto_gen, and refresh_table_values all resolve the real
             index through that stored value, so search-filtered views work
             correctly.
"""

import sys
import json
import os
import threading
from functools import partial
from Converstion import TypeConversions
from SalveHandler import SlaveRuntime, SlaveDialog
from RegisterDialog import RegisterDialog
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtGui import QIcon
from serial.tools import list_ports


BASE_PATH = None
DEBUG_MODE = None

if getattr(sys, 'frozen', False):
    BASE_PATH = sys._MEIPASS
    DEBUG_MODE = False
else:
    BASE_PATH = os.getcwd()


# --------------------- PyQt GUI ---------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Modbus-Sim')
        self.resize(1400, 800)
        self.showMaximized()
        self.setWindowIcon(QIcon(os.path.join(BASE_PATH, "logo", "Modbus-Sim-Orignial-Logo.ico")))

        self.slaves = []
        self.runtimes = {}
        self.converter = TypeConversions()

        self.auto_gen_timer = QtCore.QTimer()
        self.auto_gen_timer.timeout.connect(self.process_auto_gen)
        self.auto_gen_timer.start(100)
        self.auto_gen_states = {}

        self.auto_refresh_enabled = False
        self.refresh_timer = QtCore.QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh_registers)

        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText('Search registers...')

        # Debounce: wait 200 ms after the user stops typing before filtering.
        # This means fast typing never triggers more than one rebuild.
        self._search_debounce = QtCore.QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(200)
        self._search_debounce.timeout.connect(self.search_refresh_table_values)
        self.search_box.textChanged.connect(self._search_debounce.start)

        # ── UI layout (unchanged from original) ──────────────────────────────
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        h = QtWidgets.QHBoxLayout(central)

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

        right = QtWidgets.QVBoxLayout()
        h.addLayout(right, 4)
        self.current_label = QtWidgets.QLabel('<i>Select a slave to edit registers</i>')
        right.addWidget(self.current_label)

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

        self.current_edit_row = None
        self.edit_grace_timers = {}
        self.table.itemDoubleClicked.connect(self.on_edit_start)
        self.table.itemClicked.connect(self.on_possible_edit_start)
        self.table.itemChanged.connect(self.on_item_changed_safe)

        self.statusBar().showMessage('Ready')
        self.slave_list.currentItemChanged.connect(self.on_slave_selected)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _set_cell_text_safe(self, row, col, text):
        """Set cell text without triggering itemChanged."""
        try:
            self.table.blockSignals(True)
            item = self.table.item(row, col)
            if item is None:
                item = QtWidgets.QTableWidgetItem()
                self.table.setItem(row, col, item)
            item.setText(str(text))
        finally:
            self.table.blockSignals(False)

    # FIX 3 – resolve the ORIGINAL register index stored in col-0 UserRole
    def _orig_index_for_row(self, visual_row: int):
        """Return the original slave['registers'] index for a visible table row."""
        item = self.table.item(visual_row, 0)
        if item is None:
            return visual_row          # fallback (should not happen)
        data = item.data(QtCore.Qt.UserRole)
        return data if data is not None else visual_row

    # ── edit-grace helpers (unchanged) ───────────────────────────────────────

    def on_possible_edit_start(self, item):
        pass

    def on_edit_start(self, item):
        if item is None:
            return
        row = item.row()
        self.current_edit_row = row
        timer = self.edit_grace_timers.pop(row, None)
        if timer:
            timer.stop()
            timer.deleteLater()

    def on_item_changed_safe(self, item):
        if item is None:
            return
        row = item.row()
        if self.current_edit_row == row:
            self.current_edit_row = None
            self._start_edit_grace(row)

    def _start_edit_grace(self, row):
        existing = self.edit_grace_timers.pop(row, None)
        if existing:
            existing.stop()
            existing.deleteLater()
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(3000)
        timer.timeout.connect(lambda r=row: self._end_edit_grace(r))
        timer.start()
        self.edit_grace_timers[row] = timer

    def _end_edit_grace(self, row):
        timer = self.edit_grace_timers.pop(row, None)
        if timer:
            timer.stop()
            timer.deleteLater()
        cur = self.slave_list.currentRow()
        if cur < 0:
            return
        slave = self.slaves[cur]
        rt = self.runtimes.get(slave['name'])
        if not rt:
            return
        orig = self._orig_index_for_row(row)   # FIX 3
        regs = slave.get('registers', [])
        if orig < 0 or orig >= len(regs):
            return
        reg = regs[orig]
        v = self.read_register_value(rt, reg)
        if v is not None:
            reg['value'] = v
            self._set_cell_text_safe(row, 5, v)

    # ── auto-refresh ─────────────────────────────────────────────────────────

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
        if self.slave_list.currentRow() >= 0:
            self.refresh_table_values(silent=True)

    # ── slave management ─────────────────────────────────────────────────────

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
            self, 'Confirm', 'Are you sure you want to remove this slave?',
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
        if slave['name'] in self.runtimes:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'Stop the slave before editing its settings.')
            return
        dlg = SlaveDialog(self)
        dlg.serial_port.clear()
        ports = [p.device for p in list_ports.comports()] or ["COM1"]
        dlg.serial_port.addItems(ports)
        dlg.name_edit.setText(slave.get('name', 'slave1'))
        dlg.type_combo.setCurrentText(slave.get('type', 'tcp'))
        dlg.unit_edit.setValue(int(slave.get('unit_id', 1)))
        if slave.get('type') == 'tcp':
            dlg.tcp_host.setText(slave.get('host', '0.0.0.0'))
            dlg.tcp_port.setValue(int(slave.get('port', 5020)))
            dlg.tcp_timout.setValue(int(slave.get('timeout', 1)))
        else:
            existing_port = slave.get('port', 'COM1')
            if existing_port not in ports:
                dlg.serial_port.addItem(existing_port)
            dlg.serial_port.setCurrentText(existing_port)
            dlg.serial_baud.setCurrentText(str(slave.get('baudrate', 9600)))
            dlg.serial_parity.setCurrentText(slave.get('parity', 'N'))
            dlg.serial_bytesize.setCurrentText(str(slave.get('bytesize', 8)))
            dlg.serial_stopbits.setCurrentText(str(slave.get('stopbits', 1)))
            mode = slave.get('mode', 'rtu').lower()
            dlg.serial_mode_rtu.setChecked(mode == 'rtu')
            dlg.serial_mode_ascii.setChecked(mode == 'ascii')
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_data()
            data['registers'] = slave.get('registers', [])
            self.slaves[cur] = data
            self.update_slave_list()
            self.populate_table(data)
            self.statusBar().showMessage(f"Slave '{data['name']}' updated")

    # ── FIX 2 – start slave without blocking the UI ───────────────────────────
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
        self.runtimes[name] = rt
        rt.start()                    # start the server first

        self.statusBar().showMessage(f"Starting slave: {name} – writing registers…")
        self.update_slave_list()

        regs = slave.get('registers', [])

        # Write registers in a background thread so the UI stays responsive
        def _bulk_write():
            for reg in regs:
                self.write_register_value(rt, reg, reg.get('value', 0))
            # Signal the main thread that we are done
            QtCore.QMetaObject.invokeMethod(
                self, "_on_bulk_write_done",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, name)
            )

        threading.Thread(target=_bulk_write, daemon=True).start()

    @QtCore.pyqtSlot(str)
    def _on_bulk_write_done(self, name: str):
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
            detail = (f"{s.get('host','0.0.0.0')}:{s.get('port',5020)}"
                      if s['type'] == 'tcp'
                      else f"{s.get('port','COM1')}@{s.get('baudrate',9600)}")
            self.slave_list.addItem(f"{name} ({status}) - {stype} {detail}")
        if 0 <= current_row < self.slave_list.count():
            self.slave_list.setCurrentRow(current_row)

    def on_status_changed(self, name, status):
        self.update_slave_list()
        self.statusBar().showMessage(f"{name}: {status}")

    # ── register data-type helpers (unchanged) ────────────────────────────────

    def get_register_size(self, data_type, reg=None):
        if data_type == 'string' and reg:
            return reg.get('string_length', 10)
        sizes = {
            'uint16': 1, 'int16': 1, 'int32': 2, 'uint32': 2, 'float32': 2,
            'int64': 4, 'uint64': 4, 'double64': 4
        }
        return sizes.get(data_type, 1)

    def write_register_value(self, rt, reg, value):
        table = reg['table']
        addr = int(reg['address'])
        data_type = reg.get('data_type', 'uint16')
        endian = reg.get('endian', 'big')
        inverse = (endian == 'big')
        try:
            if data_type == 'bool':
                value = str(value)
                if isinstance(value, str):
                    value = value.strip().lower() in ["1", "true", "yes", "on"]
                rt.set_register(table, addr, 1 if value else 0)
            elif data_type == 'uint16':
                rt.set_register(table, addr, int(value))
            elif data_type == 'int16':
                words = self.converter.from_int16(int(value))
                rt.set_register(table, addr, words[0])
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
                str_len = reg.get('string_length', 10)
                words = self.converter.from_string(str(value), inverse)
                for i, w in enumerate(words):
                    if i < str_len:
                        rt.set_register(table, addr + i, w)
        except Exception as e:
            print(f"Error writing register: {e}")

    def read_register_value(self, rt, reg):
        table = reg['table']
        addr = int(reg['address'])
        data_type = reg.get('data_type', 'uint16')
        endian = reg.get('endian', 'big')
        inverse = (endian == 'big')
        try:
            if data_type == 'bool':
                v = rt.get_register(table, addr)
                return int(bool(v))
            if data_type == 'uint16':
                return rt.get_register(table, addr)
            if data_type == 'int16':
                w = rt.get_register(table, addr)
                return self.converter.to_int16([w], 0)
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
                str_len = reg.get('string_length', 10)
                words = []
                for i in range(str_len):
                    w = rt.get_register(table, addr + i)
                    if w is None:
                        return None
                    words.append(w)
                return self.converter.to_string(words, inverse)
        except Exception as e:
            print(f"Error reading register: {e}")
            return None

    # ── register management ───────────────────────────────────────────────────

    def on_slave_selected(self, current, previous):
        row = self.slave_list.currentRow()
        if row < 0:
            self.current_label.setText('<i>Select a slave to edit registers</i>')
            return
        slave = self.slaves[row]
        self.current_label.setText(f"<b>Editing registers for:</b> {slave['name']}")
        self.populate_table(slave)

    # ── FIX 1 – batch populate with signals/sorting suspended ────────────────
    def populate_table(self, slave):
        """
        Rebuild the register table efficiently.

        Key optimisations:
        - setSortingEnabled(False) prevents a re-sort after every insertRow.
        - blockSignals(True) stops itemChanged firing for every cell we fill.
        - setRowCount(n) pre-allocates all rows in one call.
        - Each cell in column-0 stores the ORIGINAL list index in Qt.UserRole
          so that search-filtered views still resolve to the right register
          (FIX 3).
        """
        regs = slave.get('registers', [])
        n = len(regs)

        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)        # clear
            self.table.setRowCount(n)        # pre-allocate

            for orig_idx, reg in enumerate(regs):
                self._fill_table_row(orig_idx, orig_idx, reg)
        finally:
            self.table.blockSignals(False)
            self.table.setSortingEnabled(False)   # keep off – we don't need it

    def _fill_table_row(self, visual_row: int, orig_idx: int, reg: dict):
        """
        Fill one already-existing table row.  The original list index
        (orig_idx) is stored in column-0's UserRole for FIX 3.
        Assumes signals are already blocked by the caller.
        """
        NON_EDIT = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

        # Col 0 – Address  (stores orig_idx in UserRole)
        addr_item = QtWidgets.QTableWidgetItem(str(reg['address']))
        addr_item.setFlags(NON_EDIT)
        addr_item.setData(QtCore.Qt.UserRole, orig_idx)   # ← FIX 3 anchor
        self.table.setItem(visual_row, 0, addr_item)

        # Col 1 – Table type
        type_item = QtWidgets.QTableWidgetItem(reg['table'].upper())
        type_item.setFlags(NON_EDIT)
        self.table.setItem(visual_row, 1, type_item)

        # Col 2 – Data type
        dtype_item = QtWidgets.QTableWidgetItem(reg.get('data_type', 'uint16'))
        dtype_item.setFlags(NON_EDIT)
        self.table.setItem(visual_row, 2, dtype_item)

        # Col 3 – Endian
        endian_item = QtWidgets.QTableWidgetItem(reg.get('endian', 'big'))
        endian_item.setFlags(NON_EDIT)
        self.table.setItem(visual_row, 3, endian_item)

        # Col 4 – Name
        name_item = QtWidgets.QTableWidgetItem(reg.get('name', ''))
        name_item.setFlags(NON_EDIT)
        self.table.setItem(visual_row, 4, name_item)

        # Col 5 – Value  (editable)
        value_item = QtWidgets.QTableWidgetItem(str(reg.get('value', 0)))
        self.table.setItem(visual_row, 5, value_item)

        # Col 6 – Writable
        writable_item = QtWidgets.QTableWidgetItem('✓ Yes' if reg.get('writable', False) else '✗ No')
        writable_item.setFlags(NON_EDIT)
        self.table.setItem(visual_row, 6, writable_item)

        # Col 7 – Actions widget
        self._build_actions_widget(visual_row, orig_idx, reg)

    def _build_actions_widget(self, visual_row: int, orig_idx: int, reg: dict):
        """Build the Apply / Gen-toggle action widget for one row."""
        actions_widget = QtWidgets.QWidget()
        actions_layout = QtWidgets.QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(2, 2, 2, 2)

        apply_btn = QtWidgets.QPushButton('Apply')
        # FIX 3: pass visual_row; _orig_index_for_row() resolves orig_idx inside
        apply_btn.clicked.connect(partial(self.apply_table_row, visual_row))
        actions_layout.addWidget(apply_btn)

        auto_gen_config = reg.get('auto_gen', {})
        if auto_gen_config.get('enabled', False):
            gen_btn = QtWidgets.QPushButton('▶ Gen')
            gen_btn.setCheckable(True)
            gen_btn.setChecked(auto_gen_config.get('active', False))

            if gen_btn.isChecked():
                gen_btn.setText('⏸ Gen')
                gen_btn.setStyleSheet("background-color: #90EE90;")

            def on_toggle(btn, vrow):
                self.toggle_auto_gen(vrow)
                if btn.isChecked():
                    btn.setStyleSheet("background-color: #90EE90;")
                else:
                    btn.setStyleSheet("")

            gen_btn.clicked.connect(lambda checked, b=gen_btn, r=visual_row: on_toggle(b, r))
            actions_layout.addWidget(gen_btn)

            key = self._get_reg_key_by_orig(orig_idx)
            if key and key not in self.auto_gen_states:
                self.auto_gen_states[key] = {
                    'last_update': 0,
                    'current_value': reg.get('value', 0),
                    'toggle_state': False,
                }

        self.table.setCellWidget(visual_row, 7, actions_widget)

    # Keep old _add_table_row as a thin wrapper so nothing external breaks
    def _add_table_row(self, reg, orig_idx=None):
        """Append one row – used by search_refresh_table_values."""
        visual_row = self.table.rowCount()
        self.table.insertRow(visual_row)
        if orig_idx is None:
            orig_idx = visual_row
        self.table.blockSignals(True)
        try:
            self._fill_table_row(visual_row, orig_idx, reg)
        finally:
            self.table.blockSignals(False)

    # ── key helpers ──────────────────────────────────────────────────────────

    def _get_reg_key(self, visual_row: int):
        """Generate unique key using the original register index (FIX 3)."""
        cur = self.slave_list.currentRow()
        if cur < 0:
            return None
        orig = self._orig_index_for_row(visual_row)
        return self._get_reg_key_by_orig(orig)

    def _get_reg_key_by_orig(self, orig_idx: int):
        cur = self.slave_list.currentRow()
        if cur < 0:
            return None
        slave = self.slaves[cur]
        regs = slave.get('registers', [])
        if orig_idx >= len(regs):
            return None
        reg = regs[orig_idx]
        return f"{slave['name']}_{reg['table']}_{reg['address']}"

    # ── auto-gen ─────────────────────────────────────────────────────────────

    def toggle_auto_gen(self, visual_row: int):
        cur = self.slave_list.currentRow()
        if cur < 0:
            return
        slave = self.slaves[cur]
        regs = slave.get('registers', [])
        orig = self._orig_index_for_row(visual_row)   # FIX 3
        if orig >= len(regs):
            return
        reg = regs[orig]
        auto_gen = reg.get('auto_gen', {})
        auto_gen['active'] = not auto_gen.get('active', False)

        actions_widget = self.table.cellWidget(visual_row, 7)
        if actions_widget:
            layout = actions_widget.layout()
            if layout.count() > 1:
                gen_btn = layout.itemAt(1).widget()
                if auto_gen['active']:
                    gen_btn.setText('⏸ Gen')
                    gen_btn.setStyleSheet('background-color: #90EE90;')
                else:
                    gen_btn.setText('▶ Gen')
                    gen_btn.setStyleSheet('')

        status = 'started' if auto_gen['active'] else 'stopped'
        self.statusBar().showMessage(f"Auto-gen {status} for {reg['name']}")

    def process_auto_gen(self):
        import random
        import time

        cur = self.slave_list.currentRow()
        if cur < 0:
            return
        slave = self.slaves[cur]
        rt = self.runtimes.get(slave['name'])
        if not rt:
            return

        current_time = time.time() * 1000

        # Iterate over visible rows, resolve orig index via UserRole (FIX 3)
        for visual_row in range(self.table.rowCount()):
            orig = self._orig_index_for_row(visual_row)
            regs = slave.get('registers', [])
            if orig >= len(regs):
                continue
            reg = regs[orig]

            auto_gen = reg.get('auto_gen', {})
            if not auto_gen.get('enabled') or not auto_gen.get('active'):
                continue

            key = self._get_reg_key_by_orig(orig)
            if not key:
                continue
            state = self.auto_gen_states.get(key)
            if not state:
                continue

            interval = auto_gen.get('interval', 1000)
            if current_time - state['last_update'] < interval:
                continue

            state['last_update'] = current_time
            mode = auto_gen.get('mode', 'Random')
            data_type = reg.get('data_type', 'uint16')
            current_val = state['current_value']

            if mode == 'Toggle':
                if data_type == 'bool':
                    new_val = 0 if current_val else 1
                else:
                    state['toggle_state'] = not state['toggle_state']
                    new_val = 1 if state['toggle_state'] else 0

            elif mode == 'Random':
                min_val = auto_gen.get('min', 0)
                max_val = auto_gen.get('max', 100)
                if data_type in ['float32', 'double64']:
                    new_val = random.uniform(min_val, max_val)
                elif data_type == 'string':
                    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
                    new_val = ''.join(random.choice(chars) for _ in range(random.randint(5, 15)))
                else:
                    new_val = random.randint(int(min_val), int(max_val))

            elif mode == 'Increment':
                step = auto_gen.get('step', 1)
                max_val = auto_gen.get('max', 100)
                if data_type in ['float32', 'double64']:
                    new_val = current_val + step
                    if new_val > max_val:
                        new_val = auto_gen.get('min', 0)
                else:
                    new_val = int(current_val) + int(step)
                    if new_val > max_val:
                        new_val = int(auto_gen.get('min', 0))

            elif mode == 'Decrement':
                step = auto_gen.get('step', 1)
                min_val = auto_gen.get('min', 0)
                if data_type in ['float32', 'double64']:
                    new_val = current_val - step
                    if new_val < min_val:
                        new_val = auto_gen.get('max', 100)
                else:
                    new_val = int(current_val) - int(step)
                    if new_val < min_val:
                        new_val = int(auto_gen.get('max', 100))
            else:
                continue

            state['current_value'] = new_val
            reg['value'] = new_val
            self.write_register_value(rt, reg, new_val)

            if visual_row not in self.edit_grace_timers and self.current_edit_row != visual_row:
                self._set_cell_text_safe(visual_row, 5, new_val)

    @property
    def is_editing_cell(self):
        return self.current_edit_row is not None

    # ── register CRUD ─────────────────────────────────────────────────────────

    def add_register_dialog(self):
        cur = self.slave_list.currentRow()
        if cur < 0:
            QtWidgets.QMessageBox.warning(self, 'Warning', 'Select a slave first')
            return
        dlg = RegisterDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            r = dlg.get_data()
            slave = self.slaves[cur]

            reg_size = self.get_register_size(r['data_type'], r)
            new_range = range(r['address'], r['address'] + reg_size)
            for reg in slave.get('registers', []):
                if reg['table'] != r['table']:
                    continue
                existing_size = self.get_register_size(reg.get('data_type', 'uint16'), reg)
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
        orig = self._orig_index_for_row(reg_row)   # FIX 3
        if orig >= len(regs):
            return
        reg = regs[orig]
        del regs[orig]
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
        orig = self._orig_index_for_row(reg_row)   # FIX 3
        if orig >= len(regs):
            return
        reg = regs[orig]
        dlg = RegisterDialog(self, reg)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            r = dlg.get_data()
            regs[orig] = r
            rt = self.runtimes.get(slave['name'])
            if rt:
                self.write_register_value(rt, r, r.get('value', 0))
            self.populate_table(slave)
            self.statusBar().showMessage(f"Edited register: {r['table'].upper()}:{r['address']}")

    # FIX 3 – apply uses orig index resolved from UserRole
    def apply_table_row(self, visual_row: int):
        cur = self.slave_list.currentRow()
        if cur < 0:
            return
        slave = self.slaves[cur]
        regs = slave.get('registers', [])
        orig = self._orig_index_for_row(visual_row)   # FIX 3 ← core of the fix
        if orig >= len(regs):
            return
        reg = regs[orig]

        val_item = self.table.item(visual_row, 5)
        if not val_item:
            return
        try:
            val_text = val_item.text()
            data_type = reg.get('data_type', 'uint16')
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

        timer = self.edit_grace_timers.pop(visual_row, None)
        if timer:
            timer.stop()
            timer.deleteLater()
        if self.current_edit_row == visual_row:
            self.current_edit_row = None

        rt = self.runtimes.get(slave['name'])
        if rt:
            self.write_register_value(rt, reg, value)
            self._set_cell_text_safe(visual_row, 5, value)
            self.statusBar().showMessage(
                f"Applied: {reg['table'].upper()}:{reg['address']} = {value}"
            )
        else:
            self._set_cell_text_safe(visual_row, 5, value)
            self.statusBar().showMessage(
                f"Updated (not running): {reg['table'].upper()}:{reg['address']} = {value}"
            )

    def refresh_table_values(self, silent=False):
        if self.is_editing_cell:
            return
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
        for visual_row in range(self.table.rowCount()):
            if self.current_edit_row is not None and visual_row == self.current_edit_row:
                continue
            if visual_row in self.edit_grace_timers:
                continue
            orig = self._orig_index_for_row(visual_row)   # FIX 3
            if orig >= len(regs):
                continue
            reg = regs[orig]
            v = self.read_register_value(rt, reg)
            if v is not None:
                reg['value'] = v
                self._set_cell_text_safe(visual_row, 5, v)
        if not silent:
            self.statusBar().showMessage('Values refreshed from running slave')

    def search_refresh_table_values(self, silent: bool = False):
        """
        Filter the table by hiding/showing existing rows – no widgets are
        created or destroyed, so this is near-instant regardless of list size.
        Falls back to showing all rows when the search box is cleared.
        """
        search_text = self.search_box.text().strip().lower()
        current_index = self.slave_list.currentRow()
        if current_index < 0:
            return
        slave = self.slaves[current_index]

        if not search_text:
            # Reveal every row – no rebuild needed
            for row in range(self.table.rowCount()):
                self.table.showRow(row)
            self.statusBar().showMessage(f"{self.table.rowCount()} registers")
            return

        # Hide/show rows in-place – no QTableWidgetItem or QWidget is created
        visible = 0
        regs = slave.get('registers', [])
        for visual_row in range(self.table.rowCount()):
            orig = self._orig_index_for_row(visual_row)
            name = regs[orig].get('name', '').lower() if orig < len(regs) else ''
            if search_text in name:
                self.table.showRow(visual_row)
                visible += 1
            else:
                self.table.hideRow(visual_row)

        if not silent:
            self.statusBar().showMessage(f"Filtered: {visible} matches")

    # ── save / load ───────────────────────────────────────────────────────────

    def save_config(self):
        fname, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save Configuration', '', 'Modbus Simulator Files (*.mbsim);;All Files (*)'
        )
        if not fname:
            return
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
            self, 'Load Configuration', '',
            'Modbus Simulator Files (*.mbsim);;JSON Files (*.json);;All Files (*)'
        )
        if not fname:
            return
        try:
            with open(fname, 'r') as f:
                config = json.load(f)
            for name, rt in list(self.runtimes.items()):
                rt.stop()
            self.runtimes.clear()
            self.slaves = config.get('slaves', [])
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