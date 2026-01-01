# -*- coding: utf-8 -*-
import re
from typing import List, Dict, Tuple, Any, Optional


class ThriftParser:
    RESERVED_KEYWORDS = [
        "from",
        "id",
        "type",
        "class",
        "async",
        "await",
        "import",
        "def",
        "lambda",
        "global",
        "nonlocal",
        "del",
        "pass",
        "yield",
    ]

    def __init__(self, input_files, output_file, patterns=None, snake_case=False):
        if isinstance(input_files, str):
            input_files = [input_files]
        self.input_files = input_files
        self.output_file = output_file
        self.patterns = patterns or [".*"]
        self.snake_case = snake_case
        self.structs = {}
        self.enums = {}
        self.services = {}
        self.RESERVED_KEYWORDS = {"from", "type", "id", "hash", "filter", "range", "global"}

    def to_snake_case(self, name: str) -> str:
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def parse(self):
        for input_file in self.input_files:
            with open(input_file, "r") as f:
                content = f.read()
            self._parse_content(content)

    def _parse_content(self, content):
        # Remove comments
        content = re.sub(r"//.*", "", content)
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

        # Parse Enums
        enum_pattern = re.compile(r"enum\s+(\w+)\s*\{(.*?)\}", re.DOTALL)
        for match in enum_pattern.finditer(content):
            name = match.group(1)
            body = match.group(2)
            values = {}
            val_pattern = re.compile(r"(\w+)\s*=\s*(-?\d+)")
            for val_match in val_pattern.finditer(body):
                values[val_match.group(1)] = int(val_match.group(2))
            self.enums[name] = {"values": values}

        # Parse Structs and Exceptions
        struct_pattern = re.compile(
            r"(?:struct|exception)\s+(\w+)\s*{([^}]*)}", re.DOTALL
        )
        for match in struct_pattern.finditer(content):
            name = match.group(1)
            body = match.group(2)
            fields = []

            # Parse fields: ID: [optional] Type Name [= Default];
            field_pattern = re.compile(
                r"(\d+):\s+(?:required|optional)?\s*([\w<>, ]+)\s+(\w+)(?:\s*=\s*(.*?))?[,;]?"
            )
            for f_match in field_pattern.finditer(body):
                fid = f_match.group(1)
                ftype = f_match.group(2).strip()
                fname = f_match.group(3)
                fields.append({"id": fid, "type": ftype, "name": fname})

            self.structs[name] = {"fields": fields}

    def _resolve_type(self, thrift_type: str) -> Tuple[str, str]:
        """Returns (Python Type, Default Value Factory/Value)"""
        # Mapping base types
        if thrift_type in ["i16", "i32", "i64", "byte"]:
            return "int", "int"
        if thrift_type in ["double", "float"]:
            return "float", "float"
        if thrift_type == "string":
            return "str", "str"
        if thrift_type == "binary":
            return (
                "bytes",
                "str",
            )  # treating binary as str for simplicity in some cases but bytes is correct
        if thrift_type == "bool":
            return "bool", "bool"
        if thrift_type == "_any":
            return "Any", "object"

        # Mapping collections
        list_match = re.match(r"list<(.+)>", thrift_type)
        if list_match:
            inner, _ = self._resolve_type(list_match.group(1))
            return f"List[{inner}]", "list"

        map_match = re.match(r"map<(.+),\s*(.+)>", thrift_type)
        if map_match:
            k_inner, _ = self._resolve_type(map_match.group(1))
            v_inner, _ = self._resolve_type(map_match.group(2))
            return f"Dict[{k_inner}, {v_inner}]", "dict"

        set_match = re.match(r"set<(.+)>", thrift_type)
        if set_match:
            inner, _ = self._resolve_type(set_match.group(1))
            return f"List[{inner}]", "list"  # Set as list for pydantic

        # Reference to other struct/enum
        if thrift_type in self.structs or thrift_type in self.enums:
            return f'"{thrift_type}"', "object"

        return f"Any", "object"

    def get_dependencies(self, target: str, seen: set):
        if target not in self.structs or target in seen:
            return seen

        seen.add(target)
        for field in self.structs[target]["fields"]:
            ftype = field["type"]
            # Find base types in collections
            types_to_check = re.findall(r"(\w+)", ftype)
            for t in types_to_check:
                if t in self.structs:
                    self.get_dependencies(t, seen)
                elif t in self.enums:
                    seen.add(t)
        return seen

    def generate_code(self) -> str:
        # Identify targets
        targets = set()
        for name in list(self.structs.keys()) + list(self.enums.keys()):
            for pat in self.patterns:
                if re.search(pat, name):
                    targets.add(name)

        # Resolve dependencies
        all_types = set()
        for t in targets:
            if t in self.structs:
                self.get_dependencies(t, all_types)
            else:
                all_types.add(t)

        lines = []
        lines.append("# -*- coding: utf-8 -*-")
        lines.append("# AUTO-GENERATED BY tools/generate_models.py")
        lines.append("from __future__ import annotations")
        lines.append("from typing import List, Optional, Dict, Any, Union")
        lines.append("from pydantic import BaseModel, Field")
        lines.append("from enum import IntEnum")
        lines.append("")

        for name in sorted(list(all_types)):
            if name in self.enums:
                lines.append(f"class {name}(IntEnum):")
                if not self.enums[name]["values"]:
                    lines.append("    pass")
                for k, v in self.enums[name]["values"].items():
                    lines.append(f"    {k} = {v}")
                lines.append("")
                continue

            # It's a struct
            struct_def = self.structs[name]
            lines.append(f"class {name}(BaseModel):")
            if not struct_def["fields"]:
                lines.append("    pass")

            for field in struct_def["fields"]:
                py_type, default_type = self._resolve_type(field["type"])
                fname = field["name"]

                if self.snake_case:
                    fname = self.to_snake_case(fname)

                # Fix numeric names or reserved keywords
                if fname.isdigit() or not fname[0].isalpha():
                    fname = f"arg_{fname}"

                if fname in self.RESERVED_KEYWORDS:
                    fname += "_"

                default_val_code = "default=None"
                if default_type == "list":
                    default_val_code = "default_factory=list"
                elif default_type == "dict":
                    default_val_code = "default_factory=dict"
                elif default_type == "int":
                    default_val_code = "default=0"
                elif default_type == "bool":
                    default_val_code = "default=False"
                elif default_type == "float":
                    default_val_code = "default=0.0"

                if "List" in py_type or "Dict" in py_type:
                    pass
                elif default_val_code == "default=None":
                    py_type = f"Optional[{py_type}]"

                lines.append(
                    f"    {fname}: {py_type} = Field(alias=\"{field['id']}\", {default_val_code})"
                )

            lines.append("")
            lines.append("    class Config:")
            lines.append("        populate_by_name = True")
            lines.append("")

        return "\n".join(lines)

    def generate_service(self, service_name: str, endpoint: str = "/S4") -> str:
        # Get submodule name from service name (e.g., TalkService -> talk)
        model_submodule = service_name.lower().replace("service", "")
        lines = [
            "# -*- coding: utf-8 -*-",
            "# AUTO-GENERATED BY tools/generate_models.py",
            "from typing import List, Optional, Dict, Any",
            "from .services.base import ServiceBase",
            f"from .models.{model_submodule} import *",
            "",
            f"class {service_name}(ServiceBase):",
            f'    ENDPOINT = "{endpoint}"',
            "    PROTOCOL = 4",
            "",
        ]

        methods = []
        seen_methods = set()

        for input_file in self.input_files:
            with open(input_file, "r") as f:
                content = f.read()

            # Try direct service block parsing first (chrline.thrift style)
            service_pattern = re.compile(
                rf"service\s+{service_name}\s*\{{(.*?)\}}", re.DOTALL
            )
            service_matches = service_pattern.findall(content)
            for service_body in service_matches:
                # Match method: returnType name(args) [throws]
                method_pattern = re.compile(r"([\w<>, ]+)\s+(\w+)\s*\((.*?)\)(?:\s+throws\s*\(.*?\))?", re.DOTALL)
                for m_match in method_pattern.finditer(service_body):
                    res_type = m_match.group(1).strip()
                    method_name = m_match.group(2)
                    args_body = m_match.group(3)

                    if method_name in seen_methods:
                        continue
                    seen_methods.add(method_name)

                    # Look for newer/more detailed args in structs
                    lookup_names = [f"{service_name}_{method_name}_args", f"{method_name}_args"]
                    found_struct = None
                    for lname in lookup_names:
                        if lname in self.structs:
                            found_struct = lname
                            break

                    if found_struct:
                        args = []
                        for f in self.structs[found_struct]["fields"]:
                            args.append({
                                "id": int(f["id"]),
                                "type": f["type"],
                                "name": f["name"]
                            })
                    else:
                        args = []
                        # Match arg: id: type name
                        arg_pattern = re.compile(r"(\d+):\s*([\w<>, ]+?)\s+(\w+)")
                        for a_match in arg_pattern.finditer(args_body):
                            args.append(
                                {
                                    "id": int(a_match.group(1)),
                                    "type": a_match.group(2).strip(),
                                    "name": a_match.group(3),
                                }
                            )

                    # Try to refine response type from _result struct
                    result_struct_names = [f"{service_name}_{method_name}_result", f"{method_name}_result"]
                    for rsname in result_struct_names:
                        if rsname in self.structs:
                            # Field 0 is usually the success response
                            for f in self.structs[rsname]["fields"]:
                                if f["id"] == "0":
                                    res_type = f["type"]
                                    break
                            break

                    # AUTO-FLATTEN: If 'request' argument exists and its type is a known struct, expand it
                    new_args = []
                    for arg in args:
                        if arg["name"] == "request" and arg["type"] in self.structs:
                            req_struct_name = arg["type"]
                            for f in self.structs[req_struct_name]["fields"]:
                                new_args.append({
                                    "id": int(f["id"]),
                                    "type": f["type"],
                                    "name": f["name"]
                                })
                        else:
                            new_args.append(arg)
                    args = new_args

                    def convert_type(t):
                        t = t.replace("list<", "List[").replace("map<", "Dict[").replace("set<", "List[").replace(">", "]")
                        t = t.replace("string", "str").replace("i32", "int").replace("i64", "int").replace("void", "None").replace("binary", "bytes").replace("bool", "bool")
                        t = t.replace("_any", "Any")
                        return t

                    res_type = convert_type(res_type)

                    methods.append(
                        {"name": method_name, "response_type": res_type, "args": args}
                    )

        if not methods:
            lines.append("    pass")
            return "\n".join(lines)

        for m in sorted(methods, key=lambda x: x["name"]):
            method_py_name = self.to_snake_case(m["name"])

            # Build method signature with individual arguments
            sig_args = ["self"]
            for arg in m["args"]:
                f_name = self.to_snake_case(arg["name"])

                # Fix numeric names or reserved keywords
                if f_name.isdigit() or not f_name[0].isalpha():
                    f_name = f"arg_{f_name}"
                if f_name in self.RESERVED_KEYWORDS:
                    f_name += "_"

                f_type = self._resolve_type(arg["type"])[0]
                if "Optional" not in f_type:
                    f_type = f"Optional[{f_type}]"
                sig_args.append(f"{f_name}: {f_type} = None")

            lines.append(
                f"    def {method_py_name}({', '.join(sig_args)}) -> {m['response_type']}:"
            )
            lines.append(f"        params = []")

            for arg in m["args"]:
                f_name = self.to_snake_case(arg["name"])

                # Fix numeric names or reserved keywords (MUST MATCH SIGNATURE)
                if f_name.isdigit() or not f_name[0].isalpha():
                    f_name = f"arg_{f_name}"
                if f_name in self.RESERVED_KEYWORDS:
                    f_name += "_"

                ftype_id = self.get_ttype_id(arg["type"])
                lines.append(f"        if {f_name} is not None:")
                lines.append(f"            params.append([{ftype_id}, {arg['id']}, {f_name}])")

            lines.append(
                f'        return self._call("{m["name"]}", [[12, 1, params]], response_model={m["response_type"]})'
            )
            lines.append("")

        return "\n".join(lines)

    def get_ttype_id(self, thrift_type: str) -> int:
        """Map Thrift type name to TType ID"""
        mapping = {
            "bool": 2,
            "byte": 3,
            "double": 4,
            "i16": 6,
            "i32": 8,
            "i64": 10,
            "string": 11,
            "binary": 11,
            "struct": 12,
            "map": 13,
            "set": 14,
            "list": 15,
        }
        if thrift_type in mapping:
            return mapping[thrift_type]
        # Check if it's a known struct/enum
        if thrift_type in self.structs:
            return 12
        if thrift_type in self.enums:
            return 10  # Enums are typically i32, so TType 8 or 10 (i64)
        if thrift_type.startswith("map<"):
            return 13
        if thrift_type.startswith("list<"):
            return 15
        if thrift_type.startswith("set<"):
            return 14
        return 12  # Default to struct


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, nargs="+", help="Path to thrift file(s)")
    parser.add_argument("--output", required=True, help="Output python file path")
    parser.add_argument(
        "--patterns",
        type=str,
        default=".*",
        help="Regex patterns for struct names (comma-separated)",
    )
    parser.add_argument(
        "--snake-case", action="store_true", help="Convert field names to snake_case"
    )
    parser.add_argument(
        "--service", type=str, help="Service name to generate (e.g. SquareService)"
    )
    parser.add_argument(
        "--service-output", type=str, help="Output file for the generated service"
    )
    parser.add_argument("--endpoint", help="Service endpoint (e.g. /S4)")
    args = parser.parse_args()

    patterns = args.patterns.split(",")
    thrift_parser = ThriftParser(
        args.input, args.output, patterns, snake_case=args.snake_case
    )
    thrift_parser.parse()

    if args.output:
        code = thrift_parser.generate_code()
        with open(args.output, "w") as f:
            f.write(code)
        print(f"Generated models to {args.output}")

    if args.service and args.service_output:
        code = thrift_parser.generate_service(args.service, endpoint=args.endpoint or "/S4")
        with open(args.service_output, "w") as f:
            f.write(code)
        print(f"Generated service {args.service} to {args.service_output}")
