"""
IniImportDialog.py

Two-step wizard for importing registers from an .ini file, where the ini
file is treated purely as a NAME -> ADDRESS map:

    [Sensors]
    Temperature = 100
    Pressure    = 102
    FlowRate    = 104

Each `key = value` pair inside a section becomes one register:
    - key   -> register name
    - value -> register address (int; "0x64", "100", etc. are accepted)

The INI file does NOT define the Modbus table, data type, endianness,
writable flag, or initial value — the user chooses all of those in the
dialog for each register before import.

Step 1 (IniSectionSelectDialog):
    - Browse for an .ini file
    - Parse it and list every section it contains
    - Let the user check which section(s) to import

Step 2 (IniValueImportDialog):
    - List every key/value (name/address) pair from the selected section(s)
    - Let the user check which ones to import
    - For each selected one, the user sets: register name (editable,
      defaults to the ini key), address (editable, pre-filled from the ini
      value), Modbus table, data type, endianness, writable, and initial
      value.
"""

import configparser
import os
from PyQt5 import QtWidgets, QtCore


# ------------------------------------------------------------------
# Step 1: pick file + sections
# ------------------------------------------------------------------
class IniSectionSelectDialog(QtWidgets.QDialog):
    """Pick an .ini file and choose which of its sections to import."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Import Registers from INI — Select Sections')
        self.resize(440, 440)

        self.config = configparser.ConfigParser()
        self.ini_path = None

        layout = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QLabel(
            'The INI file should map register names to addresses, e.g.\n'
            '[Section]\nTemperature = 100\nPressure = 102'
        )
        info.setStyleSheet('color: #666;')
        layout.addWidget(info)

        file_row = QtWidgets.QHBoxLayout()
        self.file_label = QtWidgets.QLabel('No file selected')
        self.file_label.setStyleSheet('color: #666;')
        browse_btn = QtWidgets.QPushButton('📂 Choose .ini File...')
        browse_btn.clicked.connect(self.choose_file)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        layout.addWidget(QtWidgets.QLabel('Sections found:'))
        self.section_list = QtWidgets.QListWidget()
        layout.addWidget(self.section_list)

        select_row = QtWidgets.QHBoxLayout()
        all_btn = QtWidgets.QPushButton('Select All')
        all_btn.clicked.connect(lambda: self._set_all_checked(True))
        none_btn = QtWidgets.QPushButton('Select None')
        none_btn.clicked.connect(lambda: self._set_all_checked(False))
        select_row.addWidget(all_btn)
        select_row.addWidget(none_btn)
        select_row.addStretch()
        layout.addLayout(select_row)

        btns = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        self.bb = QtWidgets.QDialogButtonBox(btns)
        self.bb.accepted.connect(self.on_accept)
        self.bb.rejected.connect(self.reject)
        layout.addWidget(self.bb)

        # Nothing to import until a valid file is loaded
        self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)

    def choose_file(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Select INI File', '', 'INI Files (*.ini);;All Files (*)'
        )
        if not fname:
            return

        cfg = configparser.ConfigParser()
        # Preserve key case as written in the file (default lower-cases keys)
        cfg.optionxform = str
        try:
            read_files = cfg.read(fname)
            if not read_files:
                raise ValueError('File could not be opened or is not valid INI')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Failed to parse INI file:\n{e}')
            return

        sections = cfg.sections()
        if not sections:
            QtWidgets.QMessageBox.warning(
                self, 'No Sections', 'This INI file has no [section] headers to import.'
            )
            return

        self.config = cfg
        self.ini_path = fname
        self.file_label.setText(os.path.basename(fname))
        self.file_label.setStyleSheet('color: black;')

        self.section_list.clear()
        for sec in sections:
            n = len(cfg[sec])
            item = QtWidgets.QListWidgetItem(f"{sec}   ({n} value{'s' if n != 1 else ''})")
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            item.setData(QtCore.Qt.UserRole, sec)
            self.section_list.addItem(item)

        self.bb.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(True)

    def _set_all_checked(self, checked):
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for i in range(self.section_list.count()):
            self.section_list.item(i).setCheckState(state)

    def on_accept(self):
        if not self.selected_sections():
            QtWidgets.QMessageBox.warning(self, 'Warning', 'Select at least one section to continue.')
            return
        self.accept()

    def selected_sections(self):
        result = []
        for i in range(self.section_list.count()):
            item = self.section_list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                result.append(item.data(QtCore.Qt.UserRole))
        return result


# ------------------------------------------------------------------
# Step 2: pick name/address pairs + user-supplied register settings
# ------------------------------------------------------------------
class IniValueImportDialog(QtWidgets.QDialog):
    """
    Show every name/address pair from the selected sections. The user
    checks which to import and fills in the Modbus table, data type,
    endianness, writable flag, and initial value for each — none of
    that comes from the ini file.
    """

    DATA_TYPES = ['uint16', 'int16', 'int32', 'uint32', 'float32',
                  'int64', 'uint64', 'double64', 'string', 'bool']

    (COL_IMPORT, COL_SECTION, COL_NAME, COL_ADDRESS, COL_TABLE,
     COL_DTYPE, COL_ENDIAN, COL_WRITABLE, COL_VALUE) = range(9)

    def __init__(self, parent, config: configparser.ConfigParser, sections: list):
        super().__init__(parent)
        self.setWindowTitle('Import Registers from INI — Configure Each Register')
        self.resize(980, 520)

        self.config = config

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(
            'Only the register name and address come from the INI file. '
            'Choose which entries to import and set the table, data type, '
            'endianness, writable flag, and initial value for each.'
        ))

        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            'Import', 'Section', 'Register Name', 'Address', 'Table',
            'Data Type', 'Endian', 'Writable', 'Initial Value'
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            self.COL_NAME, QtWidgets.QHeaderView.Stretch
        )
        layout.addWidget(self.table)

        row_btns = QtWidgets.QHBoxLayout()
        all_btn = QtWidgets.QPushButton('Check All')
        all_btn.clicked.connect(lambda: self._set_all_checked(True))
        none_btn = QtWidgets.QPushButton('Uncheck All')
        none_btn.clicked.connect(lambda: self._set_all_checked(False))
        row_btns.addWidget(all_btn)
        row_btns.addWidget(none_btn)
        row_btns.addStretch()
        layout.addLayout(row_btns)

        # Apply-to-all-selected controls, since users usually want the same
        # table/type/endian for a whole batch of imported tags.
        bulk_box = QtWidgets.QGroupBox('Apply to all checked rows')
        bulk_layout = QtWidgets.QHBoxLayout(bulk_box)

        self.bulk_table_combo = QtWidgets.QComboBox()
        self.bulk_table_combo.addItems(['co', 'di', 'hr', 'ir'])
        self.bulk_table_combo.setCurrentText('hr')
        bulk_layout.addWidget(QtWidgets.QLabel('Table:'))
        bulk_layout.addWidget(self.bulk_table_combo)

        self.bulk_dtype_combo = QtWidgets.QComboBox()
        self.bulk_dtype_combo.addItems(self.DATA_TYPES)
        bulk_layout.addWidget(QtWidgets.QLabel('Data Type:'))
        bulk_layout.addWidget(self.bulk_dtype_combo)

        self.bulk_endian_combo = QtWidgets.QComboBox()
        self.bulk_endian_combo.addItems(['big', 'little'])
        bulk_layout.addWidget(QtWidgets.QLabel('Endian:'))
        bulk_layout.addWidget(self.bulk_endian_combo)

        apply_bulk_btn = QtWidgets.QPushButton('Apply')
        apply_bulk_btn.clicked.connect(self._apply_bulk_settings)
        bulk_layout.addWidget(apply_bulk_btn)
        bulk_layout.addStretch()

        layout.addWidget(bulk_box)

        self._populate_rows(sections)

        btns = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        self.bb = QtWidgets.QDialogButtonBox(btns)
        self.bb.accepted.connect(self.on_accept)
        self.bb.rejected.connect(self.reject)
        layout.addWidget(self.bb)

    # -- helpers ----------------------------------------------------

    @staticmethod
    def _register_size(dtype, string_len=10):
        sizes = {
            'uint16': 1, 'int16': 1, 'int32': 2, 'uint32': 2, 'float32': 2,
            'int64': 4, 'uint64': 4, 'double64': 4, 'bool': 1, 'string': string_len,
        }
        return sizes.get(dtype, 1)

    @staticmethod
    def _default_initial_value(dtype):
        if dtype in ('float32', 'double64'):
            return '0.0'
        if dtype == 'string':
            return ''
        if dtype == 'bool':
            return '0'
        return '0'

    @staticmethod
    def _parse_ini_address(raw: str):
        """Best-effort integer parse of an INI address.

        Supports decimal, hexadecimal, binary, octal, and
        float-formatted integer values such as '1300.000000'.
        Returns 0 if the value cannot be parsed as an integer.
        """
        try:
            value = str(raw).strip()

            try:
                return int(float(value))
            except ValueError:
                pass

            number = float(value)

            if number.is_integer():
                return int(number)

        except (ValueError, TypeError):
            pass

        return 0

    def _populate_rows(self, sections):
        rows = []
        for sec in sections:
            for key, val in self.config[sec].items():
                rows.append((sec, key, val))

        self.table.setRowCount(len(rows))
        for r, (sec, key, val) in enumerate(rows):
            chk_item = QtWidgets.QTableWidgetItem()
            chk_item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            chk_item.setCheckState(QtCore.Qt.Checked)
            self.table.setItem(r, self.COL_IMPORT, chk_item)

            sec_item = QtWidgets.QTableWidgetItem(sec)
            sec_item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(r, self.COL_SECTION, sec_item)

            # Register name comes from the ini key, but stays user-editable.
            name_item = QtWidgets.QTableWidgetItem(key)
            self.table.setItem(r, self.COL_NAME, name_item)

            # Address comes from the ini value, but stays user-editable.
            addr_spin = QtWidgets.QSpinBox()
            addr_spin.setRange(0, 999999)
            addr_spin.setValue(self._parse_ini_address(val))
            addr_spin.setToolTip(f'From INI: {key} = {val}')
            self.table.setCellWidget(r, self.COL_ADDRESS, addr_spin)

            # Everything below is chosen by the user — nothing comes from the ini.
            table_combo = QtWidgets.QComboBox()
            table_combo.addItems(['co', 'di', 'hr', 'ir'])
            table_combo.setCurrentText('hr')
            table_combo.currentTextChanged.connect(lambda t, row=r: self._on_row_table_changed(row, t))
            self.table.setCellWidget(r, self.COL_TABLE, table_combo)

            dtype_combo = QtWidgets.QComboBox()
            dtype_combo.addItems(self.DATA_TYPES)
            dtype_combo.currentTextChanged.connect(lambda t, row=r: self._on_row_dtype_changed(row, t))
            self.table.setCellWidget(r, self.COL_DTYPE, dtype_combo)

            endian_combo = QtWidgets.QComboBox()
            endian_combo.addItems(['big', 'little'])
            self.table.setCellWidget(r, self.COL_ENDIAN, endian_combo)

            writable_check = QtWidgets.QCheckBox()
            writable_check.setChecked(True)
            # Center the checkbox in its cell
            wrapper = QtWidgets.QWidget()
            wl = QtWidgets.QHBoxLayout(wrapper)
            wl.addWidget(writable_check)
            wl.setAlignment(QtCore.Qt.AlignCenter)
            wl.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, self.COL_WRITABLE, wrapper)

            value_item = QtWidgets.QTableWidgetItem(self._default_initial_value('uint16'))
            self.table.setItem(r, self.COL_VALUE, value_item)

            # apply read-only defaults for co/di to match the rest of the app's convention
            self._on_row_table_changed(r, 'hr')

    def _on_row_dtype_changed(self, row, dtype):
        """Reset the initial-value placeholder when the user changes a row's type."""
        value_item = self.table.item(row, self.COL_VALUE)
        if value_item is not None and not value_item.text().strip():
            value_item.setText(self._default_initial_value(dtype))
        endian_combo = self.table.cellWidget(row, self.COL_ENDIAN)
        if endian_combo:
            endian_combo.setEnabled(dtype not in ('uint16', 'bool', 'string'))

    def _on_row_table_changed(self, row, table_name):
        """Discrete inputs / input registers are conventionally read-only."""
        wrapper = self.table.cellWidget(row, self.COL_WRITABLE)
        if not wrapper:
            return
        checkbox = wrapper.findChild(QtWidgets.QCheckBox)
        if not checkbox:
            return
        if table_name in ('di', 'ir'):
            checkbox.setChecked(False)
            checkbox.setEnabled(False)
        else:
            checkbox.setEnabled(True)
            checkbox.setChecked(True)

    def _apply_bulk_settings(self):
        """Apply the chosen table/data type/endian to every checked row."""
        tbl = self.bulk_table_combo.currentText()
        dtype = self.bulk_dtype_combo.currentText()
        endian = self.bulk_endian_combo.currentText()
        for r in range(self.table.rowCount()):
            if self.table.item(r, self.COL_IMPORT).checkState() != QtCore.Qt.Checked:
                continue
            self.table.cellWidget(r, self.COL_TABLE).setCurrentText(tbl)
            self.table.cellWidget(r, self.COL_DTYPE).setCurrentText(dtype)
            endian_combo = self.table.cellWidget(r, self.COL_ENDIAN)
            if endian_combo.isEnabled():
                endian_combo.setCurrentText(endian)

    def _set_all_checked(self, checked):
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for r in range(self.table.rowCount()):
            self.table.item(r, self.COL_IMPORT).setCheckState(state)

    def on_accept(self):
        if not self._any_checked():
            QtWidgets.QMessageBox.warning(self, 'Warning', 'Select at least one entry to import.')
            return
        try:
            self.get_selected_registers()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, 'Warning', str(exc))
            return
        self.accept()

    def _any_checked(self):
        for r in range(self.table.rowCount()):
            if self.table.item(r, self.COL_IMPORT).checkState() == QtCore.Qt.Checked:
                return True
        return False

    def get_selected_registers(self):
        """
        Build register dicts for every checked row, using the address the
        user set (pre-filled from the ini value) and the table/type/endian/
        writable/value the user chose for that row.
        """
        results = []
        seen_ranges = {}  # {table: [(start, end, name)]}
        for r in range(self.table.rowCount()):
            if self.table.item(r, self.COL_IMPORT).checkState() != QtCore.Qt.Checked:
                continue

            name = self.table.item(r, self.COL_NAME).text().strip()
            if not name:
                name = self.table.item(r, self.COL_SECTION).text()

            addr = self.table.cellWidget(r, self.COL_ADDRESS).value()
            tbl = self.table.cellWidget(r, self.COL_TABLE).currentText()
            dtype = self.table.cellWidget(r, self.COL_DTYPE).currentText()
            endian = self.table.cellWidget(r, self.COL_ENDIAN).currentText()
            wrapper = self.table.cellWidget(r, self.COL_WRITABLE)
            writable = wrapper.findChild(QtWidgets.QCheckBox).isChecked()
            value_text = self.table.item(r, self.COL_VALUE).text()

            value = self._coerce_value(value_text, dtype)
            size = self._register_size(dtype)

            # Reject overlaps between rows selected in this same import batch.
            for (start, end, other_name) in seen_ranges.get(tbl, []):
                if addr < end and start < addr + size:
                    raise ValueError(
                        f"'{name}' at {tbl.upper()}:{addr} overlaps '{other_name}' "
                        f"at {tbl.upper()}:{start} in this import"
                    )
            seen_ranges.setdefault(tbl, []).append((addr, addr + size, name))

            reg = {
                'address': addr,
                'table': tbl,
                'data_type': dtype,
                'endian': endian,
                'name': name,
                'value': value,
                'writable': writable,
                'auto_gen': {'enabled': False, 'active': False},
            }
            if dtype == 'string':
                reg['string_length'] = size
            results.append(reg)
        return results

    @staticmethod
    def _coerce_value(text: str, dtype: str):
        text = text.strip()
        try:
            if dtype in ('float32', 'double64'):
                return float(text) if text else 0.0
            if dtype == 'bool':
                return 1 if text.lower() in ('1', 'true', 'yes', 'on') else 0
            if dtype == 'string':
                return text
            return int(text, 0) if text else 0
        except ValueError:
            return text if dtype == 'string' else 0