# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\Personal Projects\\Modbus-Sim\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\Personal Projects\\Modbus-Sim/Converstion.py', '.'), ('D:\\Personal Projects\\Modbus-Sim/ModbusContext.py', '.'), ('D:\\Personal Projects\\Modbus-Sim/RegisterDialog.py', '.'), ('D:\\Personal Projects\\Modbus-Sim/SalveHandler.py', '.'), ('D:\\Personal Projects\\Modbus-Sim/logo', 'logo')],
    hiddenimports=['PIL.Image', 'pymodbus', 'bidict', 'PyQt5', 'PyQt5.QtWidgets', 'pyserial', 'wmi', 'pywintypes'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Modbus-Sim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\Personal Projects\\Modbus-Sim\\logo\\Modbus-Sim-Orignial-Logo.ico'],
    manifest='elevated.manifest',
)
