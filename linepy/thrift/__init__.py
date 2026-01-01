"""
Thrift Protocol Implementation for LINEPY

Based on linejs implementation.
Supports Binary (protocol 3) and Compact (protocol 4) protocols.
"""

import struct
from typing import Any, Tuple, List, Dict, Optional, Union


import os

# Debug mode
DEBUG = os.getenv("LINEPY_DEBUG", "false").lower() == "true"


def set_debug(enabled: bool):
    """Enable/disable debug mode"""
    global DEBUG
    DEBUG = enabled


def debug_log(msg: str, data: Any = None):
    """Print debug message"""
    if DEBUG:
        if data is not None:
            if isinstance(data, bytes):
                print(f"[DEBUG] {msg}: {data.hex()}")
            else:
                print(f"[DEBUG] {msg}: {data}")
        else:
            print(f"[DEBUG] {msg}")


class TType:
    """Thrift type constants"""

    STOP = 0
    VOID = 1
    BOOL = 2
    BYTE = 3
    I08 = 3
    DOUBLE = 4
    I16 = 6
    I32 = 8
    I64 = 10
    STRING = 11
    UTF7 = 11
    STRUCT = 12
    MAP = 13
    SET = 14
    LIST = 15


class CompactType:
    """Compact protocol type constants"""

    STOP = 0x00
    TRUE = 0x01
    FALSE = 0x02
    BYTE = 0x03
    I16 = 0x04
    I32 = 0x05
    I64 = 0x06
    DOUBLE = 0x07
    BINARY = 0x08
    LIST = 0x09
    SET = 0x0A
    MAP = 0x0B
    STRUCT = 0x0C


# ========== Header Generation (from linejs) ==========


def gen_header_binary(name: str) -> bytes:
    """
    Generate Binary protocol header (protocol 3).
    Format: [0x80, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, len] + name + [0x00, 0x00, 0x00, 0x00]
    """
    name_bytes = name.encode("utf-8")
    prefix = bytes([0x80, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, len(name_bytes)])
    suffix = bytes([0x00, 0x00, 0x00, 0x00])
    return prefix + name_bytes + suffix


def gen_header_compact(name: str) -> bytes:
    """
    Generate Compact protocol header (protocol 4).
    Format: [0x82, 0x21, 0x00, len] + name
    """
    name_bytes = name.encode("utf-8")
    header = bytes([0x82, 0x21, 0x00, len(name_bytes)])
    return header + name_bytes


# ========== Compact Protocol Writer ==========


class CompactWriter:
    """
    Thrift Compact Protocol Writer (protocol 4).
    Based on linejs implementation.
    """

    def __init__(self):
        self._buffer = bytearray()
        self._last_fid = 0

    def get_bytes(self) -> bytes:
        return bytes(self._buffer)

    # ========== Varint ==========

    def _write_varint(self, n: int):
        """Write unsigned varint"""
        while True:
            byte = n & 0x7F
            n >>= 7
            if n:
                self._buffer.append(byte | 0x80)
            else:
                self._buffer.append(byte)
                break

    def _write_zigzag(self, n: int):
        """Write signed zigzag encoded varint"""
        self._write_varint((n << 1) ^ (n >> 63))

    # ========== Primitives ==========

    def write_bool(self, value: bool, fid: int):
        """Write bool with field header (inline)"""
        delta = fid - self._last_fid
        ctype = CompactType.TRUE if value else CompactType.FALSE
        if 0 < delta <= 15:
            self._buffer.append((delta << 4) | ctype)
        else:
            self._buffer.append(ctype)
            self._write_zigzag(fid)
        self._last_fid = fid

    def write_byte(self, value: int):
        self._buffer.append(value & 0xFF)

    def write_i16(self, value: int):
        self._write_zigzag(value)

    def write_i32(self, value: int):
        self._write_zigzag(value)

    def write_i64(self, value: int):
        self._write_zigzag(value)

    def write_double(self, value: float):
        self._buffer += struct.pack("<d", value)

    def write_binary(self, value: Union[str, bytes]):
        if isinstance(value, str):
            value = value.encode("utf-8")
        self._write_varint(len(value))
        self._buffer += value

    # ========== Field Writing ==========

    def write_field_begin(self, ftype: int, fid: int):
        """Write field header"""
        # Map TType to CompactType
        ctype_map = {
            TType.BOOL: CompactType.TRUE,  # Will be overwritten for actual bool
            TType.BYTE: CompactType.BYTE,
            TType.I16: CompactType.I16,
            TType.I32: CompactType.I32,
            TType.I64: CompactType.I64,
            TType.DOUBLE: CompactType.DOUBLE,
            TType.STRING: CompactType.BINARY,
            TType.STRUCT: CompactType.STRUCT,
            TType.MAP: CompactType.MAP,
            TType.SET: CompactType.SET,
            TType.LIST: CompactType.LIST,
        }
        ctype = ctype_map.get(ftype, ftype)

        delta = fid - self._last_fid
        if 0 < delta <= 15:
            self._buffer.append((delta << 4) | ctype)
        else:
            self._buffer.append(ctype)
            self._write_zigzag(fid)
        self._last_fid = fid

    def write_field_stop(self):
        """Write field stop marker"""
        self._buffer.append(0x00)

    def write_struct_begin(self):
        """Begin writing struct (save field id state)"""
        pass

    def write_struct_end(self):
        """End writing struct"""
        pass

    # ========== Collection Writing ==========

    def write_list_begin(self, etype: int, size: int):
        ctype_map = {
            TType.BOOL: CompactType.TRUE,
            TType.BYTE: CompactType.BYTE,
            TType.I16: CompactType.I16,
            TType.I32: CompactType.I32,
            TType.I64: CompactType.I64,
            TType.DOUBLE: CompactType.DOUBLE,
            TType.STRING: CompactType.BINARY,
            TType.STRUCT: CompactType.STRUCT,
            TType.MAP: CompactType.MAP,
            TType.SET: CompactType.SET,
            TType.LIST: CompactType.LIST,
        }
        ctype = ctype_map.get(etype, etype)

        if size <= 14:
            self._buffer.append((size << 4) | ctype)
        else:
            self._buffer.append(0xF0 | ctype)
            self._write_varint(size)

    def write_map_begin(self, ktype: int, vtype: int, size: int):
        if size == 0:
            self._buffer.append(0)
        else:
            self._write_varint(size)
            ctype_map = {
                TType.BOOL: CompactType.TRUE,
                TType.BYTE: CompactType.BYTE,
                TType.I16: CompactType.I16,
                TType.I32: CompactType.I32,
                TType.I64: CompactType.I64,
                TType.DOUBLE: CompactType.DOUBLE,
                TType.STRING: CompactType.BINARY,
                TType.STRUCT: CompactType.STRUCT,
            }
            kctype = ctype_map.get(ktype, ktype)
            vctype = ctype_map.get(vtype, vtype)
            self._buffer.append((kctype << 4) | vctype)


# ========== High-Level Writer ==========


def write_thrift(params: List, method_name: str, protocol: int = 4) -> bytes:
    """
    Write Thrift request in linejs format.

    Args:
        params: Parameters in [[type, id, value], ...] format
        method_name: RPC method name
        protocol: 3=binary, 4=compact

    Returns:
        Complete Thrift request bytes
    """
    debug_log(f"write_thrift: method={method_name}, protocol={protocol}")
    debug_log("params", params)

    if protocol == 4:
        header = gen_header_compact(method_name)
        writer = CompactWriter()
    else:
        header = gen_header_binary(method_name)
        writer = CompactWriter()  # TODO: Implement binary writer

    # Write struct
    _write_struct(writer, params)

    # Add field stop at the end if not already present
    body = writer.get_bytes()
    if not body or body[-1] != 0:
        body += bytes([0x00])

    result = header + body
    debug_log("request bytes", result)
    return result


def _write_struct(writer: CompactWriter, params: Union[List, Any]):
    """Write struct fields"""
    from pydantic import BaseModel
    from enum import Enum

    saved_fid = writer._last_fid
    writer._last_fid = 0

    if isinstance(params, BaseModel):
        # Handle Pydantic model
        # Iterate over pydantic fields to get values and aliases (IDs)
        for name, field in params.model_fields.items():
            value = getattr(params, name)
            if value is None:
                continue

            # Field ID (from alias)
            fid = int(field.alias) if field.alias and field.alias.isdigit() else 0
            if fid == 0:
                continue

            # Infer type
            if isinstance(value, str):
                ftype = TType.STRING
            elif isinstance(value, bool):
                ftype = TType.BOOL
            elif isinstance(value, (int, Enum)):
                ftype = TType.I64
            elif isinstance(value, float):
                ftype = TType.DOUBLE
            elif isinstance(value, list):
                ftype = TType.LIST
            elif isinstance(value, dict):
                ftype = TType.MAP
            elif isinstance(value, BaseModel):
                ftype = TType.STRUCT
            elif isinstance(value, (bytes, bytearray)):
                ftype = TType.STRING
            else:
                ftype = TType.STRUCT  # Default to struct for unknown complex types

            _write_value(writer, ftype, fid, value)
    elif isinstance(params, list):
        # Handle original list-of-lists format
        for param in params:
            if param is None:
                continue
            if len(param) < 3:
                continue

            ftype, fid, value = param[0], param[1], param[2]
            _write_value(writer, ftype, fid, value)

    writer.write_field_stop()  # Important: Terminate struct
    writer._last_fid = saved_fid


def _write_value(writer: CompactWriter, ftype: int, fid: int, value: Any):
    """Write a single value"""
    if value is None:
        return

    if ftype == TType.BOOL:  # 2
        writer.write_bool(bool(value), fid)

    elif ftype == TType.BYTE:  # 3
        writer.write_field_begin(ftype, fid)
        writer.write_byte(value)

    elif ftype == TType.DOUBLE:  # 4
        writer.write_field_begin(ftype, fid)
        writer.write_double(value)

    elif ftype == TType.I16:  # 6
        writer.write_field_begin(ftype, fid)
        writer.write_i16(value)

    elif ftype == TType.I32:  # 8
        writer.write_field_begin(ftype, fid)
        writer.write_i32(value)

    elif ftype == TType.I64:  # 10
        writer.write_field_begin(ftype, fid)
        if hasattr(value, "value"):  # Enum
            value = value.value
        writer.write_i64(value)

    elif ftype == TType.STRING:  # 11
        writer.write_field_begin(ftype, fid)
        writer.write_binary(value)

    elif ftype == TType.STRUCT:  # 12
        if not value:
            return
        writer.write_field_begin(ftype, fid)
        _write_struct(writer, value)

    elif ftype == TType.MAP:  # 13
        # value is [key_type, val_type, dict]
        if not value:
            return

        if isinstance(value, dict):
            # Try to infer types if it's a raw dict
            ktype = TType.STRING
            vtype = TType.STRING
            data = value
        else:
            ktype, vtype, data = value[0], value[1], value[2]

        writer.write_field_begin(ftype, fid)
        writer.write_map_begin(ktype, vtype, len(data))
        for k, v in data.items():
            _write_value_raw(writer, ktype, k)
            _write_value_raw(writer, vtype, v)

    elif ftype in (TType.SET, TType.LIST):  # 14, 15
        if not value:
            return

        if isinstance(value, list) and not (
            len(value) == 2 and isinstance(value[0], int)
        ):
            # It's a raw list, infer element type
            etype = (
                TType.STRUCT
                if value and hasattr(value[0], "model_fields")
                else TType.STRING
            )
            data = value
        else:
            etype, data = value[0], value[1]

        writer.write_field_begin(ftype, fid)
        writer.write_list_begin(etype, len(data))
        for item in data:
            _write_value_raw(writer, etype, item)


def _write_value_raw(writer: CompactWriter, ftype: int, value: Any):
    """Write value without field header"""
    from pydantic import BaseModel
    from enum import Enum

    if value is None:
        return

    if isinstance(value, Enum):
        value = value.value

    if ftype == TType.BOOL:
        writer.write_byte(1 if value else 0)
    elif ftype == TType.BYTE:
        writer.write_byte(value)
    elif ftype == TType.I16:
        writer.write_i16(value)
    elif ftype == TType.I32:
        writer.write_i32(value)
    elif ftype == TType.I64:
        writer.write_i64(value)
    elif ftype == TType.DOUBLE:
        writer.write_double(value)
    elif ftype == TType.STRING:
        writer.write_binary(value)
    elif ftype == TType.STRUCT:
        _write_struct(writer, value)
    elif ftype in (TType.SET, TType.LIST):  # handled as List for now
        # Fallback for nested lists (rarely used in LINE)
        pass


# ========== Compact Protocol Reader ==========


class CompactReader:
    """Thrift Compact Protocol Reader"""

    def __init__(self, data: bytes):
        self.data = data
        self._pos = 0
        self._last_fid = 0
        self._bool_value = None
        debug_log(
            "CompactReader initialized with data",
            data[:100] if len(data) > 100 else data,
        )

    def _read(self, n: int) -> bytes:
        result = self.data[self._pos : self._pos + n]
        self._pos += n
        return result

    # ========== Varint ==========

    def read_varint(self) -> int:
        result = 0
        shift = 0
        while True:
            byte = self.data[self._pos]
            self._pos += 1
            result |= (byte & 0x7F) << shift
            if (byte >> 7) == 0:
                return result
            shift += 7

    def read_zigzag(self) -> int:
        n = self.read_varint()
        return (n >> 1) ^ -(n & 1)

    # ========== Message Header ==========

    def read_message_begin(self) -> Tuple[str, int, int]:
        proto_id = self.data[self._pos]
        self._pos += 1

        debug_log(f"read_message_begin: proto_id={proto_id} (0x{proto_id:02x})")

        if proto_id != 0x82:
            # Check if it's binary protocol
            if proto_id == 0x80:
                debug_log("Detected binary protocol, switching...")
                self._pos -= 1
                return self._read_binary_message_begin()

            # Not thrift - might be error response
            debug_log("Response bytes", self.data[:200])
            try:
                text = self.data.decode("utf-8", errors="replace")
                debug_log("Response text", text[:500])
            except:
                pass
            raise Exception(f"Bad protocol id: {proto_id}")

        ver_type = self.data[self._pos]
        self._pos += 1
        _type = (ver_type >> 5) & 7
        version = ver_type & 0x1F

        seqid = self.read_varint()
        name_len = self.read_varint()
        name = self._read(name_len).decode("utf-8")

        debug_log(f"Message: name={name}, type={_type}, seqid={seqid}")
        return name, _type, seqid

    def _read_binary_message_begin(self) -> Tuple[str, int, int]:
        """Read binary protocol message header"""
        sz = struct.unpack("!i", self._read(4))[0]
        if sz < 0:
            version = sz & 0xFFFF0000
            if version != 0x80010000:
                raise Exception(f"Bad binary version: {version}")
            _type = sz & 0xFF
            name_len = struct.unpack("!i", self._read(4))[0]
            name = self._read(name_len).decode("utf-8")
            seqid = struct.unpack("!i", self._read(4))[0]
            return name, _type, seqid
        raise Exception(f"Bad binary message: {sz}")

    # ========== Field Reading ==========

    def read_field_begin(self) -> Tuple[Optional[str], int, int]:
        if self._pos >= len(self.data):
            return None, TType.STOP, 0

        type_byte = self.data[self._pos]
        self._pos += 1

        if type_byte == 0:
            return None, TType.STOP, 0

        delta = type_byte >> 4
        ctype = type_byte & 0x0F

        if delta == 0:
            fid = self.read_zigzag()
        else:
            fid = self._last_fid + delta

        self._last_fid = fid

        # Handle inline booleans
        if ctype == CompactType.TRUE:
            self._bool_value = True
        elif ctype == CompactType.FALSE:
            self._bool_value = False

        # Convert compact type to TType
        ctype_to_ttype = {
            CompactType.STOP: TType.STOP,
            CompactType.TRUE: TType.BOOL,
            CompactType.FALSE: TType.BOOL,
            CompactType.BYTE: TType.BYTE,
            CompactType.I16: TType.I16,
            CompactType.I32: TType.I32,
            CompactType.I64: TType.I64,
            CompactType.DOUBLE: TType.DOUBLE,
            CompactType.BINARY: TType.STRING,
            CompactType.LIST: TType.LIST,
            CompactType.SET: TType.SET,
            CompactType.MAP: TType.MAP,
            CompactType.STRUCT: TType.STRUCT,
        }
        ftype = ctype_to_ttype.get(ctype, ctype)

        return None, ftype, fid

    def read_collection_begin(self) -> Tuple[int, int]:
        size_type = self.data[self._pos]
        self._pos += 1
        size = size_type >> 4
        ctype = size_type & 0x0F
        if size == 15:
            size = self.read_varint()

        ctype_to_ttype = {
            CompactType.TRUE: TType.BOOL,
            CompactType.FALSE: TType.BOOL,
            CompactType.BYTE: TType.BYTE,
            CompactType.I16: TType.I16,
            CompactType.I32: TType.I32,
            CompactType.I64: TType.I64,
            CompactType.DOUBLE: TType.DOUBLE,
            CompactType.BINARY: TType.STRING,
            CompactType.STRUCT: TType.STRUCT,
        }
        return ctype_to_ttype.get(ctype, ctype), size

    def read_map_begin(self) -> Tuple[int, int, int]:
        size = self.read_varint()
        if size == 0:
            return TType.STOP, TType.STOP, 0
        types = self.data[self._pos]
        self._pos += 1
        ktype = types >> 4
        vtype = types & 0x0F

        ctype_to_ttype = {
            CompactType.TRUE: TType.BOOL,
            CompactType.BYTE: TType.BYTE,
            CompactType.I16: TType.I16,
            CompactType.I32: TType.I32,
            CompactType.I64: TType.I64,
            CompactType.DOUBLE: TType.DOUBLE,
            CompactType.BINARY: TType.STRING,
            CompactType.STRUCT: TType.STRUCT,
        }
        return ctype_to_ttype.get(ktype, ktype), ctype_to_ttype.get(vtype, vtype), size

    # ========== Value Reading ==========

    def read_bool(self) -> bool:
        return self._bool_value

    def read_byte(self) -> int:
        val = self.data[self._pos]
        self._pos += 1
        return val if val < 128 else val - 256

    def read_i16(self) -> int:
        return self.read_zigzag()

    def read_i32(self) -> int:
        return self.read_zigzag()

    def read_i64(self) -> int:
        return self.read_zigzag()

    def read_double(self) -> float:
        data = self._read(8)
        return struct.unpack("<d", data)[0]

    def read_binary(self) -> Union[str, bytes]:
        size = self.read_varint()
        data = self._read(size)
        try:
            return data.decode("utf-8")
        except:
            return data

    def read_value(self, ftype: int) -> Any:
        if ftype == TType.STOP:
            return None
        elif ftype == TType.BOOL:
            return self.read_bool()
        elif ftype == TType.BYTE:
            return self.read_byte()
        elif ftype == TType.DOUBLE:
            return self.read_double()
        elif ftype == TType.I16:
            return self.read_i16()
        elif ftype == TType.I32:
            return self.read_i32()
        elif ftype == TType.I64:
            return self.read_i64()
        elif ftype == TType.STRING:
            return self.read_binary()
        elif ftype == TType.STRUCT:
            return self.read_struct()
        elif ftype == TType.MAP:
            return self.read_map()
        elif ftype in (TType.SET, TType.LIST):
            return self.read_list()
        else:
            raise Exception(f"Cannot read type {ftype}")

    def read_struct(self) -> Dict[int, Any]:
        result = {}
        saved_fid = self._last_fid
        self._last_fid = 0
        while True:
            _, ftype, fid = self.read_field_begin()
            if ftype == TType.STOP:
                break
            result[fid] = self.read_value(ftype)
        self._last_fid = saved_fid
        return result

    def read_map(self) -> Dict[Any, Any]:
        ktype, vtype, size = self.read_map_begin()
        result = {}
        for _ in range(size):
            key = self.read_value(ktype)
            val = self.read_value(vtype)
            result[key] = val
        return result

    def read_list(self) -> List[Any]:
        etype, size = self.read_collection_begin()
        return [self.read_value(etype) for _ in range(size)]

    def parse_response(self) -> Any:
        """Parse complete Thrift response"""
        debug_log("parse_response start")

        name, _type, seqid = self.read_message_begin()

        debug_log(f"Parsing response for: {name}")

        _, ftype, fid = self.read_field_begin()

        if fid == 0:
            result = self.read_value(ftype)
            debug_log("Success response", result)
            return result
        elif fid == 1:
            error = self.read_value(ftype)
            debug_log("Error response", error)
            return {
                "error": {
                    "code": error.get(1) if isinstance(error, dict) else None,
                    "message": error.get(2) if isinstance(error, dict) else str(error),
                    "metadata": error.get(3) if isinstance(error, dict) else None,
                    "_data": error,
                }
            }
        else:
            error = self.read_value(ftype)
            debug_log(f"Unknown field {fid}", error)
            raise Exception(f"Unknown field id: {fid}")


# ========== Legacy Writer (for compatibility) ==========


class ThriftWriter:
    """Legacy Thrift Writer for compatibility"""

    def __init__(self):
        self._params = []

    def write_message_begin(self, name: str, msg_type: int, seqid: int):
        pass

    def write_field(self, fid: int, ftype: int, value: Any):
        self._params.append([ftype, fid, value])

    def write_field_begin(self, ftype: int, fid: int):
        pass

    def write_field_stop(self):
        pass

    def write_binary(self, value: bytes):
        pass

    def get_bytes(self) -> bytes:
        return b""


class ThriftReader:
    """Legacy Binary Reader"""

    def __init__(self, data: bytes):
        self.data = data
        self._pos = 0

    def parse_response(self) -> Any:
        # Use compact reader as fallback
        reader = CompactReader(self.data)
        return reader.parse_response()
