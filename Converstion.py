import struct
from typing import List, Union

# --------------------- Type Conversion Library ---------------------
class TypeConversions():
    def normalize_words(self, words: List[int]) -> List[int]:
        """Ensure values are treated as unsigned 16-bit integers."""
        return [w & 0xFFFF for w in words]

    def _read_words(self, data: List[int], count: int, index: int, inverse: bool) -> bytes:
        words = data[index:index + count]
        words = self.normalize_words(words[::-1] if inverse else words)
        return struct.pack(f'>{count}H', *words)

    def _write_words(self, raw: bytes, count: int, inverse: bool) -> List[int]:
        words = list(struct.unpack(f'>{count}H', raw))
        return words[::-1] if inverse else words

    # === 32-bit FLOAT ===
    def to_float32(self, data: List[int], index: int = 0, inverse: bool = True) -> float:
        return round(struct.unpack('>f', self._read_words(data, 2, index, inverse))[0], 3)

    def from_float32(self, value: float, inverse: bool = True) -> List[int]:
        return self._write_words(struct.pack('>f', value), 2, inverse)

    # === 64-bit DOUBLE ===
    def to_double64(self, data: List[int], index: int = 0, inverse: bool = True) -> float:
        return round(struct.unpack('>d', self._read_words(data, 4, index, inverse))[0], 3)

    def from_double64(self, value: float, inverse: bool = True) -> List[int]:
        return self._write_words(struct.pack('>d', value), 4, inverse)

    # === 64-bit LONG (signed) ===
    def to_long64(self, data: List[int], index: int = 0, inverse: bool = True) -> int:
        return struct.unpack('>q', self._read_words(data, 4, index, inverse))[0]

    def from_long64(self, value: int, inverse: bool = True) -> List[int]:
        return self._write_words(struct.pack('>q', value), 4, inverse)

    # === 64-bit ULONG (unsigned) ===
    def to_ulong64(self, data: List[int], index: int = 0, inverse: bool = True) -> int:
        return struct.unpack('>Q', self._read_words(data, 4, index, inverse))[0]

    def from_ulong64(self, value: int, inverse: bool = True) -> List[int]:
        return self._write_words(struct.pack('>Q', value), 4, inverse)

    # === 32-bit SIGNED INTEGER ===
    def to_int32(self, data: List[int], index: int = 0, inverse: bool = True) -> int:
        return struct.unpack('>i', self._read_words(data, 2, index, inverse))[0]

    def from_int32(self, value: int, inverse: bool = True) -> List[int]:
        return self._write_words(struct.pack('>i', value), 2, inverse)

    # === 32-bit UNSIGNED INTEGER ===
    def to_uint32(self, data: List[int], index: int = 0, inverse: bool = True) -> int:
        return struct.unpack('>I', self._read_words(data, 2, index, inverse))[0]

    def from_uint32(self, value: int, inverse: bool = True) -> List[int]:
        return self._write_words(struct.pack('>I', value), 2, inverse)

    # ===  STRINGS  ===
    def from_string(self, value: str, inverse: bool = False) -> List[int]:
        """Convert ASCII string into a list of u16 registers."""
        data = value.encode("ascii")
        if len(data) % 2 != 0:
            data += b"\x00"
        registers = []
        for i in range(0, len(data), 2):
            if not inverse:
                registers.append(data[i] | (data[i+1] << 8))
            else:
                registers.append((data[i] << 8) | data[i+1])
        return registers

    def to_string(self, registers: List[int], inverse: bool = False) -> str:
        """Convert a list of u16 registers into an ASCII string."""
        chars = []
        for reg in registers:
            if not inverse:
                chars.append(reg & 0xFF)
                chars.append((reg >> 8) & 0xFF)
            else:
                chars.append((reg >> 8) & 0xFF)
                chars.append(reg & 0xFF)
        return bytes(chars).decode("ascii", errors='ignore').rstrip("\x00")