from PyQt5 import QtWidgets, QtCore

class RegisterDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, regs=None):
        super().__init__(parent)
        self.setWindowTitle('Add Register')
        self.resize(400, 450)
        layout = QtWidgets.QFormLayout(self)
        
        self.addr = QtWidgets.QSpinBox()
        self.addr.setRange(0, 9999)

        self.table = QtWidgets.QComboBox()
        self.table.addItems(['co', 'di', 'hr', 'ir'])
        self.table.setItemData(0, 'Coil (read/write)', QtCore.Qt.ToolTipRole)
        self.table.setItemData(1, 'Discrete Input (read-only)', QtCore.Qt.ToolTipRole)
        self.table.setItemData(2, 'Holding Register (read/write)', QtCore.Qt.ToolTipRole)
        self.table.setItemData(3, 'Input Register (read-only)', QtCore.Qt.ToolTipRole)
        
        self.table.currentTextChanged.connect(self.on_reg_type_changed)
        
        self.data_type = QtWidgets.QComboBox()
        self.data_type.addItems([
            'uint16', 'int32', 'uint32', 'float32',
            'int64', 'uint64', 'double64', 'string', 'bool'
        ])
        self.data_type.currentTextChanged.connect(self.on_data_type_changed)
        
        self.endian = QtWidgets.QComboBox()
        self.endian.addItems(['big', 'little'])
        self.endian.setToolTip('Word order for multi-register values')
        
        # String length field (add this)
        self.string_length = QtWidgets.QSpinBox()
        self.string_length.setRange(1, 100)
        self.string_length.setValue(10)
        self.string_length.setToolTip('Number of registers for string storage')
        self.string_length.setVisible(False)
        self.string_length_label = QtWidgets.QLabel('String Registers:')
        self.string_length_label.setVisible(False)

        self.name = QtWidgets.QLineEdit('register1')
        self.value = QtWidgets.QLineEdit('0')
        self.writable = QtWidgets.QCheckBox()
        self.writable.setChecked(True)
        
        # Size label
        self.size_label = QtWidgets.QLabel('Size: 1 register')
        self.size_label.setStyleSheet('color: #666; font-style: italic;')

        # Auto-gen section
        self.auto_gen_group = QtWidgets.QGroupBox('Auto Generation')
        auto_gen_layout = QtWidgets.QVBoxLayout()
        
        self.auto_gen_enabled = QtWidgets.QCheckBox('Enable Auto Generation')
        self.auto_gen_enabled.stateChanged.connect(self.on_auto_gen_toggled)
        auto_gen_layout.addWidget(self.auto_gen_enabled)
        
        # Mode selection
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel('Mode:'))
        self.auto_gen_mode = QtWidgets.QComboBox()
        self.auto_gen_mode.addItems(['Toggle', 'Random', 'Increment', 'Decrement'])
        self.auto_gen_mode.currentTextChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.auto_gen_mode)
        auto_gen_layout.addLayout(mode_layout)
        
        # Min/Max for random
        range_layout = QtWidgets.QFormLayout()
        self.auto_gen_min = QtWidgets.QLineEdit('0')
        self.auto_gen_max = QtWidgets.QLineEdit('100')
        range_layout.addRow('Min Value:', self.auto_gen_min)
        range_layout.addRow('Max Value:', self.auto_gen_max)
        auto_gen_layout.addLayout(range_layout)
        
        # Step for increment/decrement
        step_layout = QtWidgets.QHBoxLayout()
        step_layout.addWidget(QtWidgets.QLabel('Step:'))
        self.auto_gen_step = QtWidgets.QLineEdit('1')
        step_layout.addWidget(self.auto_gen_step)
        auto_gen_layout.addLayout(step_layout)
        
        # Interval
        interval_layout = QtWidgets.QHBoxLayout()
        interval_layout.addWidget(QtWidgets.QLabel('Interval (ms):'))
        self.auto_gen_interval = QtWidgets.QSpinBox()
        self.auto_gen_interval.setRange(100, 60000)
        self.auto_gen_interval.setValue(1000)
        interval_layout.addWidget(self.auto_gen_interval)
        auto_gen_layout.addLayout(interval_layout)
        
        self.auto_gen_group.setLayout(auto_gen_layout)
        self.auto_gen_mode.setEnabled(False)
        self.auto_gen_min.setEnabled(False)
        self.auto_gen_max.setEnabled(False)
        self.auto_gen_step.setEnabled(False)
        self.auto_gen_interval.setEnabled(False)  

        self.string_length.valueChanged.connect(self.on_string_length_changed)

        # Add all to main layout
        layout.addRow('Address:', self.addr)
        layout.addRow('Type:', self.table)
        layout.addRow('Data Type:', self.data_type)
        layout.addRow('Endianness:', self.endian)
        layout.addRow(self.string_length_label, self.string_length)
        layout.addRow('', self.size_label)
        layout.addRow('Name:', self.name)
        layout.addRow('Initial Value:', self.value)
        layout.addRow('Writable:', self.writable)
        layout.addRow(self.auto_gen_group)

        btns = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        self.bb = QtWidgets.QDialogButtonBox(btns)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        layout.addWidget(self.bb)
        
        self.on_data_type_changed(self.data_type.currentText())
        self.on_reg_type_changed(self.table.currentText())
        self.on_mode_changed(self.auto_gen_mode.currentText())
        
        if regs:
            self.addr.setValue(regs.get('address', 0))
            self.table.setCurrentText(regs.get('table', 'hr'))
            self.data_type.setCurrentText(regs.get('data_type', 'uint16'))
            self.endian.setCurrentText(regs.get('endian', 'big'))
            self.name.setText(regs.get('name', 'register1'))
            self.value.setText(str(regs.get('value', 0)))
            self.writable.setChecked(regs.get('writable', True))
            
            # Load string length if applicable
            if regs.get('data_type') == 'string':
                self.string_length.setValue(regs.get('string_length', 10))
            
            if regs.get('data_type') == 'bool':
                self.auto_gen_min.isEnabled(False)
                self.auto_gen_max.isEnabled(False)

            # Load auto-gen settings
            auto_gen = regs.get('auto_gen', {})
            if auto_gen.get('enabled', False):
                self.auto_gen_enabled.setChecked(True)
                self.auto_gen_mode.setCurrentText(auto_gen.get('mode', 'Random'))
                self.auto_gen_min.setText(str(auto_gen.get('min', 0)))
                self.auto_gen_max.setText(str(auto_gen.get('max', 100)))
                self.auto_gen_step.setText(str(auto_gen.get('step', 1)))
                self.auto_gen_interval.setValue(auto_gen.get('interval', 1000))
        
    def on_string_length_changed(self, value):
        """Update size label when string length changes"""
        if self.data_type.currentText() == 'string':
            self.size_label.setText(f'Size: {value} register(s)')
            
    def on_auto_gen_toggled(self, state):
        enabled = (state == QtCore.Qt.Checked)
        # Enable/disable only the controls inside, not the checkbox itself
        self.auto_gen_mode.setEnabled(enabled)
        self.auto_gen_min.setEnabled(enabled)
        self.auto_gen_max.setEnabled(enabled)
        self.auto_gen_step.setEnabled(enabled)
        self.auto_gen_interval.setEnabled(enabled)
        
        # Update field visibility based on mode and data type if enabled
        if enabled:
            self.on_mode_changed(self.auto_gen_mode.currentText())
    
    def on_mode_changed(self, mode):
        # Show/hide relevant fields based on mode
        is_random = (mode == 'Random')
        is_increment = (mode in ['Increment', 'Decrement'])
        
        if self.data_type.currentText() == 'bool':
            self.auto_gen_min.setEnabled(False)
            self.auto_gen_max.setEnabled(False)
            self.auto_gen_step.setEnabled(False)
        else:
            self.auto_gen_min.setEnabled(is_random)
            self.auto_gen_max.setEnabled(is_random)
            self.auto_gen_step.setEnabled(is_increment)
    
    def on_reg_type_changed(self, t):
        if t in ['co', 'di']:
            self.data_type.setCurrentText('bool')
            self.data_type.setEnabled(False)
            self.endian.setEnabled(False)
            # Trigger data type change to update auto-gen options
            self.on_data_type_changed('bool')
        else:
            self.data_type.setCurrentText('uint16')
            self.data_type.setEnabled(True)
            self.endian.setEnabled(True)
            # Trigger data type change to update auto-gen options
            self.on_data_type_changed('uint16')


    def on_data_type_changed(self, dtype):
        sizes = {
            'uint16': 1, 'int32': 2, 'uint32': 2, 'float32': 2,
            'int64': 4, 'uint64': 4, 'double64': 4
        }
        
        # Show/hide string length field
        is_string = (dtype == 'string')
        self.string_length.setVisible(is_string)
        self.string_length_label.setVisible(is_string)
        
        if is_string:
            size = self.string_length.value()
            self.size_label.setText(f'Size: {size} register(s)')
        else:
            size = sizes.get(dtype, 1)
            if isinstance(size, int):
                self.size_label.setText(f'Size: {size} register(s)')
            else:
                self.size_label.setText(f'Size: {size}')
        
        self.endian.setEnabled(dtype != 'uint16' and dtype != 'string')
        
        # Configure auto-gen modes based on data type
        current_mode = self.auto_gen_mode.currentText()
        self.auto_gen_mode.clear()
        
        if dtype == 'bool':
            # Bool: only Toggle or Random (0/1)
            self.auto_gen_mode.addItems(['Toggle', 'Random'])
            self.value.setText('0')
            self.auto_gen_min.setText('0')
            self.auto_gen_max.setText('1')
            self.auto_gen_min.setEnabled(False)
            self.auto_gen_max.setEnabled(False)
            self.auto_gen_step.setEnabled(False)
        elif dtype == 'string':
            # String: only Random
            self.auto_gen_mode.addItems(['Random'])
            self.value.setText('Hello')
            self.auto_gen_min.setEnabled(False)
            self.auto_gen_max.setEnabled(False)
            self.auto_gen_step.setEnabled(False)
        elif dtype in ['float32', 'double64']:
            # Float/Double: all modes
            self.auto_gen_mode.addItems(['Random', 'Increment', 'Decrement', 'Toggle'])
            self.value.setText('0.0')
            self.auto_gen_min.setText('0.0')
            self.auto_gen_max.setText('100.0')
            self.auto_gen_step.setText('0.1')
        else:
            # Integer types: all modes
            self.auto_gen_mode.addItems(['Random', 'Increment', 'Decrement', 'Toggle'])
            self.value.setText('0')
            self.auto_gen_min.setText('0')
            self.auto_gen_max.setText('100')
            self.auto_gen_step.setText('1')
        
        # Restore previous mode if available
        index = self.auto_gen_mode.findText(current_mode)
        if index >= 0:
            self.auto_gen_mode.setCurrentIndex(index)
        
        # Update field visibility
        self.on_mode_changed(self.auto_gen_mode.currentText())
        
    def get_data(self):
        data_type = self.data_type.currentText()
        val_text = self.value.text()
        
        try:
            if data_type in ['float32', 'double64']:
                value = float(val_text)
            elif data_type == 'string':
                value = val_text
            else:
                value = int(val_text)
        except ValueError:
            value = 0
        
        result = {
            'address': int(self.addr.value()),
            'table': self.table.currentText(),
            'data_type': data_type,
            'endian': self.endian.currentText(),
            'name': self.name.text(),
            'value': value,
            'writable': bool(self.writable.isChecked()),
        }
        
        # Add string length if applicable
        if data_type == 'string':
            result['string_length'] = self.string_length.value()
        
        # Add auto-gen config
        if self.auto_gen_enabled.isChecked():
            try:
                min_val = float(self.auto_gen_min.text()) if data_type in ['float32', 'double64'] else int(self.auto_gen_min.text())
                max_val = float(self.auto_gen_max.text()) if data_type in ['float32', 'double64'] else int(self.auto_gen_max.text())
                step_val = float(self.auto_gen_step.text()) if data_type in ['float32', 'double64'] else int(self.auto_gen_step.text())
            except ValueError:
                min_val, max_val, step_val = 0, 100, 1
            
            result['auto_gen'] = {
                'enabled': True,
                'mode': self.auto_gen_mode.currentText(),
                'min': min_val,
                'max': max_val,
                'step': step_val,
                'interval': self.auto_gen_interval.value(),
                'active': False
            }
        else:
            result['auto_gen'] = {'enabled': False, 'active': False}
        
        return result