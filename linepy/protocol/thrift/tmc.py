# -*- coding: utf-8 -*-
"""
TMoreCompactProtocol (TMC) decoder for LINEPY.

Faithful Python port of linejs
(resource/linejs/packages/linejs/base/thrift/readwrite/tmc.ts), which was in
turn ported from CHRLINE's Python implementation by YinMo.

TMC is LINE's ultra-dense variant of the Thrift compact protocol used for
Talk sync responses (Service 5/8) delivered over the PUSH stream: a Huffman
coded type sequence in the header, a per-message string table, delta-encoded
field-id bitmaps and zigzag varints.
"""

import struct
from typing import Any, Dict, List, Optional, Tuple


class TMoreCompactProtocol:
    def __init__(
        self,
        input_data: Optional[bytes] = None,
        base_exception: Optional[Dict[str, int]] = None,
        read_with: Optional[str] = None,
    ):
        self.huffman_tree: List[int] = []
        self.huffman_patterns: List[List[str]] = []
        self.type_sequence: List[int] = []
        self.string_table: List[str] = []
        self.last_field_id: int = 0
        self.current_position: int = 0
        self.last_string_id: int = 0
        self.data: bytes = b""
        self.res: Any = None
        self.base_exception = base_exception or {"code": 1, "message": 2, "metadata": 3}
        self.read_with = read_with
        self._initialize_huffman_tree()
        if input_data is not None:
            self.set_data_and_parse(input_data)

    # -------------------------------------------------- primitives

    def read_varint(self) -> int:
        result = 0
        shift = 0
        while True:
            byte = self.data[self.current_position]
            self.current_position += 1
            result |= (byte & 0x7F) << shift
            if (byte & 0x80) != 0x80:
                return result
            shift += 7

    def read_bytes(self, position: int, length: int) -> List[int]:
        if length == 0:
            return []
        return list(self.data[position:position + length])

    def read_single_byte(self) -> int:
        byte = self.data[self.current_position]
        self.current_position += 1
        return byte

    @staticmethod
    def decode_zigzag(encoded: int) -> int:
        n = encoded
        return (n >> 1) ^ -(n & 1)

    def has_more_data(self) -> bool:
        return len(self.data) > self.current_position

    # -------------------------------------------------- parse entry

    def set_data_and_parse(self, input_data: bytes) -> None:
        self.data = input_data
        self.parse_header()

    def parse_header(self) -> None:
        self.current_position = 3
        if len(self.data) == 4:
            raise ValueError(f"Invalid data: {self.data.hex()} (code: 20)")

        header_length = self.read_varint()
        header_bytes = self.read_bytes(self.current_position, header_length)
        self.type_sequence = [0] * (header_length << 1)

        node_index = 0
        type_index = 0
        current_node = 0
        for byte in header_bytes:
            bit_mask = 128
            for _ in range(8):
                if (byte & bit_mask) == 0:
                    node_index = (current_node << 1) + 1
                else:
                    node_index = (current_node << 1) + 2

                if self.huffman_tree[node_index] != 0:
                    if type_index >= len(self.type_sequence):
                        self.type_sequence += [0] * (len(self.type_sequence) * 3)
                    self.type_sequence[type_index] = self.huffman_tree[node_index]
                    type_index += 1
                    current_node = 0
                else:
                    current_node = node_index
                bit_mask >>= 1

        self.current_position += header_length
        self.read_string_table_and_parse_message()

    def read_string_table_and_parse_message(self) -> None:
        table_size = self.read_varint()
        for _ in range(table_size):
            first = chr(self.data[self.current_position])
            hexpart = self.data[
                self.current_position + 1:self.current_position + 17
            ].hex()
            self.string_table.append(first + hexpart)
            self.current_position += 17
        self.parse_message_body()

    def parse_message_body(self) -> None:
        result: Any = {}
        field_id_bits = self.read_varint()

        if field_id_bits == 0:
            pass
        elif field_id_bits in (1, 2):
            field_ids = self.decode_field_bitmap(field_id_bits)
            field_id = field_ids[0] if field_ids else None
            if field_id == 0:
                ftype = self.get_next_type()
                result[0] = self.read_data_by_type(ftype, field_id)[1]
            elif field_id == 1:
                ftype = self.get_next_type()
                result[1] = self.read_data_by_type(ftype, field_id)[1]
            elif field_id == 5:
                ftype = self.get_next_type()
                raise Exception(str(self.read_data_by_type(ftype, field_id)))
            else:
                raise Exception(f"fid {field_id} not implemented")
        else:
            ftype = self.get_next_type()
            result = self.read_data_by_type(ftype)[0]
            raise Exception(
                f"recv fid `{field_id_bits}`, expected `1`, message: `{result}`"
            )

        self.res = result

    # -------------------------------------------------- data reader

    def read_data_by_type(
        self, type_id: int, field_id: Optional[int] = None
    ) -> Tuple[Optional[int], Any]:
        value: Any = None
        val_data: Any = None

        if type_id == 2:  # BOOL
            value = bool(self.read_varint())
        elif type_id == 3:  # BYTE
            value = self.data[self.current_position]
            self.current_position += 1
        elif type_id == 4:  # DOUBLE
            value = struct.unpack_from("<d", self.data, self.current_position)[0]
            self.current_position += 8
        elif type_id == 8:  # I32 (zigzag varint)
            value = self.decode_zigzag(self.read_varint())
        elif type_id == 10:  # I64 (zigzag varint)
            value = self.decode_zigzag(self.read_varint())
        elif type_id == 11:  # STRING
            value = self.read_string()
        elif type_id == 12:  # STRUCT
            value = {}
            temp = self.read_varint()
            field_ids = self.decode_field_bitmap(temp)
            val_data = {}
            for fid in field_ids:
                _, field_value = self.read_data_by_type(self.get_next_type(), fid)
                val_data[fid] = field_value
        elif type_id == 13:  # MAP
            value = {}
            map_size = self.read_varint()
            val_data = {}
            if map_size != 0:
                types_byte = self.read_single_byte()
                key_type, value_type = self.decode_map_types(types_byte)
                for _ in range(map_size):
                    _, k_val = self.read_data_by_type(key_type)
                    _, v_val = self.read_data_by_type(value_type)
                    val_data[k_val] = v_val
        elif type_id in (14, 15):  # SET or LIST
            value = []
            size_type = self.data[self.current_position]
            self.current_position += 1
            count = size_type >> 4
            element_type = size_type & 0x0F
            if count == 15:
                count = self.read_varint()
            elem = self.convert_compact_type_to_ttype(element_type)
            val_data = []
            for _ in range(count):
                _, val = self.read_data_by_type(elem)
                val_data.append(val)
        elif type_id == 16:  # STRING (string ID delta)
            raw = self.read_varint()
            delta = (raw >> 1) ^ -(raw & 1)
            string_id = delta + self.last_string_id
            self.last_string_id = string_id
            value = str(string_id)
            type_id = 11
        elif type_id == 17:  # STRING (string table reference)
            temp = self.read_varint()
            if len(self.string_table) > temp:
                value = self.string_table[temp]
                type_id = 11
            else:
                # matches 本家's console.log fallback (value stays None)
                pass
        else:
            raise ValueError(f"can't read type: {type_id}")

        if val_data is None:
            val_data = value
        return field_id, val_data

    def read_string(self):
        length = self.read_varint()
        buffer = self.data[self.current_position:self.current_position + length]
        self.current_position += length
        try:
            return buffer.decode("utf-8")
        except UnicodeDecodeError:
            return buffer

    # -------------------------------------------------- helpers

    def decode_field_bitmap(self, bitmap: int) -> List[int]:
        field_ids = []
        bit_position = 0
        while True:
            mask = 1 << bit_position
            if mask > bitmap:
                break
            if (bitmap & mask) != 0:
                field_ids.append(bit_position)
            bit_position += 1
        return field_ids

    def decode_map_types(self, types_byte: int) -> Tuple[int, int]:
        return (
            self.convert_compact_type_to_ttype(types_byte >> 4),
            self.convert_compact_type_to_ttype(types_byte & 15),
        )

    def get_next_type(self) -> int:
        type_id = self.type_sequence[self.last_field_id]
        self.last_field_id += 1
        return type_id

    def _initialize_huffman_tree(self) -> None:
        self.huffman_tree = [0] * 512
        self.huffman_patterns = [[] for _ in range(18)]
        self._build_huffman_node(["1", "0", "1", "1"], 2)
        self._build_huffman_node(["1", "0", "1", "0", "1", "0", "0", "1"], 3)
        self._build_huffman_node(["1", "0", "1", "0", "1", "0", "0", "0"], 4)
        self._build_huffman_node(["1", "0", "1", "0", "1", "1", "1"], 6)
        self._build_huffman_node(["0", "1"], 8)
        self._build_huffman_node(["0", "0"], 10)
        self._build_huffman_node(["1", "0", "1", "0", "0"], 11)
        self._build_huffman_node(["1", "1", "0", "1"], 12)
        self._build_huffman_node(["1", "0", "1", "0", "1", "1", "0"], 13)
        self._build_huffman_node(["1", "0", "1", "0", "1", "0", "1"], 14)
        self._build_huffman_node(["1", "1", "0", "0"], 15)
        self._build_huffman_node(["1", "1", "1"], 16)
        self._build_huffman_node(["1", "0", "0"], 17)

    def _build_huffman_node(self, pattern: List[str], type_id: int) -> None:
        self.huffman_patterns[type_id] = pattern
        node_index = 0
        for bit in pattern:
            if bit == "0":
                node_index = (node_index << 1) + 1
            elif bit == "1":
                node_index = (node_index << 1) + 2
        self.huffman_tree[node_index] = type_id

    @staticmethod
    def convert_compact_type_to_ttype(compact_type: int) -> int:
        mapping = {0: 0, 1: 2, 2: 2, 3: 3, 4: 6, 5: 8, 6: 10, 7: 4,
                   8: 11, 9: 15, 10: 14, 11: 13, 12: 12}
        if compact_type not in mapping:
            raise ValueError(f"Invalid type: {compact_type}")
        return mapping[compact_type]


def decode_tmc(data: bytes) -> Any:
    """Convenience: decode a TMC message and return the parsed result."""
    return TMoreCompactProtocol(data).res
