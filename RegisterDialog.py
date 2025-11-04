
from PyQt5 import QtWidgets, QtCore

class RegisterDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, regs=None):
        super().__init__(parent)
        self.setWindowTitle('Add Register')
        self.resize(400, 350)
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
            'uint16',
            'int32',
            'uint32',
            'float32',
            'int64',
            'uint64',
            'double64',
            'string',
            'bool'
        ])
        self.data_type.currentTextChanged.connect(self.on_data_type_changed)
        
        self.endian = QtWidgets.QComboBox()
        self.endian.addItems(['big', 'little'])
        self.endian.setToolTip('Word order for multi-register values')
        
        self.name = QtWidgets.QLineEdit('register1')
        
        self.value = QtWidgets.QLineEdit('0')
        
        self.writable = QtWidgets.QCheckBox()
        self.writable.setChecked(True)
        
        # Info label for register size
        self.size_label = QtWidgets.QLabel('Size: 1 register')
        self.size_label.setStyleSheet('color: #666; font-style: italic;')

        layout.addRow('Address:', self.addr)
        layout.addRow('Type:', self.table)
        layout.addRow('Data Type:', self.data_type)
        layout.addRow('Endianness:', self.endian)
        layout.addRow('', self.size_label)
        layout.addRow('Name:', self.name)
        layout.addRow('Initial Value:', self.value)
        layout.addRow('Writable:', self.writable)

        btns = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        self.bb = QtWidgets.QDialogButtonBox(btns)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        layout.addWidget(self.bb)
        
        self.on_data_type_changed(self.data_type.currentText())
        self.on_reg_type_changed(self.table.currentText())
        if regs:
            self.addr.setValue(regs.get('address', 0))
            self.table.setCurrentText(regs.get('table', 'hr'))
            self.data_type.setCurrentText(regs.get('data_type', 'uint16'))
            self.endian.setCurrentText(regs.get('endian', 'big'))
            self.name.setText(regs.get('name', 'register1'))
            self.value.setText(str(regs.get('value', 0)))
            self.writable.setChecked(regs.get('writable', True))
    
    def on_reg_type_changed(self, t):
        if t in ['co', 'di']:
            self.data_type.setCurrentText('bool')
            self.data_type.setEnabled(False)
            self.endian.setEnabled(False)
        else:
            self.data_type.setCurrentText('uint16')
            self.data_type.setEnabled(True)
            self.endian.setEnabled(True)

    def on_data_type_changed(self, dtype):
        sizes = {
            'uint16': 1, 'int32': 2, 'uint32': 2, 'float32': 2,
            'int64': 4, 'uint64': 4, 'double64': 4, 'string': 'Variable'
        }
        size = sizes.get(dtype, 1)
        if isinstance(size, int):
            self.size_label.setText(f'Size: {size} register(s)')
        else:
            self.size_label.setText(f'Size: {size}')
        
        # Enable/disable endian for multi-register types
        self.endian.setEnabled(dtype != 'uint16')
        
        # Set appropriate default values
        if dtype in ['float32', 'double64']:
            self.value.setText('0.0')
        elif dtype == 'string':
            self.value.setText('Hello')
        else:
            self.value.setText('0')

    def get_data(self):
        data_type = self.data_type.currentText()
        val_text = self.value.text()
        
        # Convert value based on type
        try:
            if data_type in ['float32', 'double64']:
                value = float(val_text)
            elif data_type == 'string':
                value = val_text
            else:
                value = int(val_text)
        except ValueError:
            value = 0
        
        return {
            'address': int(self.addr.value()),
            'table': self.table.currentText(),
            'data_type': data_type,
            'endian': self.endian.currentText(),
            'name': self.name.text(),
            'value': value,
            'writable': bool(self.writable.isChecked()),
        }

