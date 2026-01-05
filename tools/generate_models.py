# -*- coding: utf-8 -*-
import re
from typing import List, Dict, Tuple, Any, Optional

class ThriftParser:
    # Token types
    T_IDENTIFIER = "IDENTIFIER"
    T_INTEGER = "INTEGER"
    T_STRING = "STRING"
    T_LBRACE = "LBRACE"  # {
    T_RBRACE = "RBRACE"  # }
    T_LPAREN = "LPAREN"  # (
    T_RPAREN = "RPAREN"  # )
    T_COLON = "COLON"    # :
    T_EQUALS = "EQUALS"  # =
    T_COMMA = "COMMA"    # ,
    T_SEMICOLON = "SEMICOLON" # ;
    T_LT = "LT"          # <
    T_GT = "GT"          # >
    T_LBRACKET = "LBRACKET" # [
    T_RBRACKET = "RBRACKET" # ]
    T_KEYWORD = "KEYWORD"
    T_EOF = "EOF"

    KEYWORDS = {
        "struct", "exception", "service", "enum", "const", "typedef", "include", "namespace",
        "required", "optional", "extends", "throws", "void", "oneway",
        "map", "list", "set", "bool", "byte", "i16", "i32", "i64", "double", "string", "binary"
    }

    RESERVED_PYTHON_KEYWORDS = {
        "from", "id", "type", "class", "async", "await", "import", "def",
        "lambda", "global", "nonlocal", "del", "pass", "yield", "if", "else", "elif",
        "for", "while", "break", "continue", "return", "try", "except", "finally",
        "raise", "assert", "with", "as", "in", "is", "not", "and", "or", "None", "True", "False"
    }

    def __init__(self, input_files, output_file, patterns=None, snake_case=False, service_source_file: Optional[str] = None):
        if isinstance(input_files, str):
            input_files = [input_files]
        self.input_files = input_files
        self.output_file = output_file
        self.patterns = patterns or [".*"]
        self.snake_case = snake_case
        self.service_source_file = service_source_file

        self.structs = {}
        self.enums = {}
        self.services = {}

        # Internal parser state
        self.tokens = []
        self.pos = 0

    def to_snake_case(self, name: str) -> str:
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def tokenize(self, content: str):
        tokens = []
        # Remove comments first to simplify tokenizing
        content = re.sub(r"//.*", "", content)
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
        content = re.sub(r"#.*", "", content) # Shell style comments

        token_patterns = [
            (self.T_LBRACE, r"\{"),
            (self.T_RBRACE, r"\}"),
            (self.T_LPAREN, r"\("),
            (self.T_RPAREN, r"\)"),
            (self.T_LBRACKET, r"\["),
            (self.T_RBRACKET, r"\]"),
            (self.T_COLON, r":"),
            (self.T_EQUALS, r"="),
            (self.T_COMMA, r","),
            (self.T_SEMICOLON, r";"),
            (self.T_LT, r"<"),
            (self.T_GT, r">"),
            (self.T_STRING, r'"[^"]*"|\'[^\']*\''),
            (self.T_INTEGER, r"-?\d+"),
            (self.T_IDENTIFIER, r"[a-zA-Z_][a-zA-Z0-9_.]*"),
        ]

        # Use a single regex for efficiency
        regex_parts = []
        for type_, pattern in token_patterns:
            regex_parts.append(f"(?P<{type_}>{pattern})")

        # Adding whitespace skipper
        master_regex = re.compile("|".join(regex_parts))

        for match in master_regex.finditer(content):
            kind = match.lastgroup
            value = match.group()

            if kind == self.T_IDENTIFIER and value in self.KEYWORDS:
                kind = self.T_KEYWORD
            elif kind == self.T_STRING:
                value = value[1:-1] # Strip quotes
            elif kind == self.T_INTEGER:
                value = int(value)

            tokens.append((kind, value))

        tokens.append((self.T_EOF, None))
        return tokens

    def parse(self):
        for input_file in self.input_files:
            with open(input_file, "r") as f:
                content = f.read()

            self.tokens = self.tokenize(content)
            self.pos = 0
            self._parse_document()

    # --- Parser Helpers ---

    def current_token(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return (self.T_EOF, None)

    def advance(self):
        self.pos += 1
        return self.tokens[self.pos - 1]

    def consume(self, expected_type, expected_value=None):
        token = self.current_token()
        if token[0] == expected_type:
            if expected_value is None or token[1] == expected_value:
                self.pos += 1
                return token
        return None

    def expect(self, expected_type, expected_value=None):
        token = self.consume(expected_type, expected_value)
        if not token:
            curr = self.current_token()
            raise Exception(f"Syntax Error: Expected {expected_type} ({expected_value}), found {curr} at pos {self.pos}")
        return token

    # --- Recursive Descent Parser Methods ---

    def _parse_document(self):
        while self.current_token()[0] != self.T_EOF:
            token = self.current_token()
            if token[0] == self.T_KEYWORD:
                if token[1] == "enum":
                    self._parse_enum()
                elif token[1] in ("struct", "exception"):
                    self._parse_struct(token[1])
                elif token[1] == "service":
                    self._parse_service()
                elif token[1] == "include":
                    self._skip_include()
                elif token[1] == "namespace":
                    self._skip_namespace()
                elif token[1] == "const":
                    self._skip_const()
                elif token[1] == "typedef":
                    self._skip_typedef()
                else:
                    # Unknown keyword at top level
                    print(f"Warning: Skipping unknown top-level keyword {token[1]}")
                    self.advance()
            else:
                self.advance()

    def _skip_include(self):
        self.expect(self.T_KEYWORD, "include")
        self.expect(self.T_STRING)
        # Optional semicolon
        self.consume(self.T_SEMICOLON)

    def _skip_namespace(self):
        self.expect(self.T_KEYWORD, "namespace")
        self.expect(self.T_IDENTIFIER) # Language
        self.expect(self.T_IDENTIFIER) # Namespace
        # Thrift files might use dots in identifier for namespace
        self.consume(self.T_SEMICOLON)

    def _skip_const(self):
        # const Type Name = Value [;]
        self.expect(self.T_KEYWORD, "const")
        self._parse_type()
        self.expect(self.T_IDENTIFIER)
        self.expect(self.T_EQUALS)
        self._skip_value()
        self.consume(self.T_SEMICOLON)

    def _skip_value(self):
        # Recursively skip a value (literal, list, map, etc)
        token = self.current_token()
        if token[0] in (self.T_INTEGER, self.T_STRING, self.T_IDENTIFIER, self.T_KEYWORD):
            self.advance()
        elif token[0] == self.T_LBRACKET:
            self.advance()
            while self.current_token()[0] != self.T_RBRACKET:
                self._skip_value()
                self.consume(self.T_COMMA)
                self.consume(self.T_SEMICOLON)
            self.expect(self.T_RBRACKET)
        elif token[0] == self.T_LBRACE:
            self.advance()
            while self.current_token()[0] != self.T_RBRACE:
                self._skip_value() # Key
                self.consume(self.T_COLON)
                self._skip_value() # Value
                self.consume(self.T_COMMA)
                self.consume(self.T_SEMICOLON)
            self.expect(self.T_RBRACE)
        else:
             self.advance() # Fallback

    def _skip_typedef(self):
        # typedef Type Alias [;]
        self.expect(self.T_KEYWORD, "typedef")
        self._parse_type()
        self.expect(self.T_IDENTIFIER)
        self.consume(self.T_SEMICOLON)

    def _parse_enum(self):
        self.expect(self.T_KEYWORD, "enum")
        name = self.expect(self.T_IDENTIFIER)[1]
        self.expect(self.T_LBRACE)

        values = {}
        last_val = -1

        while self.current_token()[0] != self.T_RBRACE and self.current_token()[0] != self.T_EOF:
            val_name = self.expect(self.T_IDENTIFIER)[1]
            val = last_val + 1

            if self.consume(self.T_EQUALS):
                val_token = self.expect(self.T_INTEGER)
                val = val_token[1]

            values[val_name] = val
            last_val = val

            self.consume(self.T_COMMA)
            self.consume(self.T_SEMICOLON)

        self.expect(self.T_RBRACE)
        self.enums[name] = {"values": values}

    def _parse_struct(self, kind="struct"):
        self.expect(self.T_KEYWORD, kind)
        name = self.expect(self.T_IDENTIFIER)[1]
        self.expect(self.T_LBRACE)

        fields = []
        while self.current_token()[0] != self.T_RBRACE and self.current_token()[0] != self.T_EOF:
            # Field ID
            fid_token = self.expect(self.T_INTEGER)
            fid = fid_token[1]
            self.expect(self.T_COLON)

            # Optionality
            optionality = None
            if self.current_token()[0] == self.T_KEYWORD and self.current_token()[1] in ("required", "optional"):
                optionality = self.advance()[1]

            # Type
            ftype = self._parse_type()

            # Name
            fname = self.expect(self.T_IDENTIFIER)[1]

            # Default value
            default_val = None
            if self.consume(self.T_EQUALS):
                self._skip_value()
                default_val = "Exists"

            fields.append({
                "id": str(fid),
                "type": ftype,
                "name": fname,
                "required": optionality == "required",
                "optional": optionality == "optional",
                "has_default": default_val is not None
            })

            self.consume(self.T_COMMA)
            self.consume(self.T_SEMICOLON)

        self.expect(self.T_RBRACE)
        self.structs[name] = {"fields": fields, "kind": kind}

    def _parse_type(self):
        # Type can be Identifier, BaseType, or Container
        token = self.current_token()

        if token[0] == self.T_KEYWORD and token[1] in ("map", "list", "set"):
            self.advance()
            container_type = token[1]
            self.expect(self.T_LT)

            if container_type == "map":
                ktype = self._parse_type()
                self.expect(self.T_COMMA)
                vtype = self._parse_type()
                self.expect(self.T_GT)
                return f"map<{ktype},{vtype}>"
            else:
                itype = self._parse_type()
                self.expect(self.T_GT)
                return f"{container_type}<{itype}>"

        elif token[0] in (self.T_IDENTIFIER, self.T_KEYWORD):
            # Base types (string, i32) are keywords in our tokenizer, struct names are identifiers
            self.advance()
            return token[1]

        else:
            raise Exception(f"Expected type, found {token} at pos {self.pos}")

    def _parse_service(self):
        self.expect(self.T_KEYWORD, "service")
        name = self.expect(self.T_IDENTIFIER)[1]

        extends = None
        if self.consume(self.T_KEYWORD, "extends"):
            extends = self.expect(self.T_IDENTIFIER)[1]

        self.expect(self.T_LBRACE)

        methods = []

        while self.current_token()[0] != self.T_RBRACE and self.current_token()[0] != self.T_EOF:
            # Function: ReturnType Name ( Args ) Throws?

            # oneway?
            self.consume(self.T_KEYWORD, "oneway")

            ret_type = self._parse_type()
            func_name = self.expect(self.T_IDENTIFIER)[1]

            self.expect(self.T_LPAREN)
            args = []
            while self.current_token()[0] != self.T_RPAREN:
                fid = self.expect(self.T_INTEGER)[1]
                self.expect(self.T_COLON)

                self.consume(self.T_KEYWORD, "required")
                self.consume(self.T_KEYWORD, "optional")

                atype = self._parse_type()
                aname = self.expect(self.T_IDENTIFIER)[1]

                if self.consume(self.T_EQUALS):
                     self._skip_value()

                args.append({
                    "id": fid,
                    "type": atype,
                    "name": aname
                })
                self.consume(self.T_COMMA)
                self.consume(self.T_SEMICOLON)

            self.expect(self.T_RPAREN)

            # throws?
            if self.consume(self.T_KEYWORD, "throws"):
                self.expect(self.T_LPAREN)
                while self.current_token()[0] != self.T_RPAREN:
                     self.expect(self.T_INTEGER)
                     self.expect(self.T_COLON)
                     self._parse_type()
                     self.expect(self.T_IDENTIFIER)
                     self.consume(self.T_COMMA)
                     self.consume(self.T_SEMICOLON)
                self.expect(self.T_RPAREN)

            self.consume(self.T_COMMA)
            self.consume(self.T_SEMICOLON)

            methods.append({
                "name": func_name,
                "return_type": ret_type,
                "args": args
            })

        self.expect(self.T_RBRACE)
        self.services[name] = {"methods": methods, "extends": extends}

    # --- Generation Logic ---

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
            return "str", "str"
        if thrift_type == "bool":
            return "bool", "bool"
        if thrift_type == "void":
            return "None", "None"
        if thrift_type == "Any":
            return "Any", "object"

        # Mapping collections
        if thrift_type.startswith("list<"):
            inner = thrift_type[5:-1]
            inner_py, _ = self._resolve_type(inner)
            return f"List[{inner_py}]", "list"

        if thrift_type.startswith("map<"):
            content = thrift_type[4:-1]
            depth = 0
            split_idx = -1
            for i, char in enumerate(content):
                if char == '<': depth += 1
                elif char == '>': depth -= 1
                elif char == ',' and depth == 0:
                    split_idx = i
                    break

            if split_idx != -1:
                k_str = content[:split_idx].strip()
                v_str = content[split_idx+1:].strip()
                k_inner, _ = self._resolve_type(k_str)
                v_inner, _ = self._resolve_type(v_str)
                return f"Dict[{k_inner}, {v_inner}]", "dict"
            return "Dict[Any, Any]", "dict"

        if thrift_type.startswith("set<"):
            inner = thrift_type[4:-1]
            inner_py, _ = self._resolve_type(inner)
            return f"List[{inner_py}]", "list"

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
            types_to_check = re.findall(r"([a-zA-Z_][a-zA-Z0-9_.]*)", ftype)
            for t in types_to_check:
                if t in self.structs:
                    self.get_dependencies(t, seen)
                elif t in self.enums:
                    seen.add(t)
        return seen

    def generate_code(self, root_service: Optional[str] = None) -> str:
        # Resolve dependencies
        all_types = set()

        if root_service:
            if root_service in self.services:
                # Collect types from service methods
                initial_types = set()
                service_def = self.services[root_service]
                for m in service_def["methods"]:
                    # Return type
                    rtype = m["return_type"]
                    # Extract potential type names from complex types (e.g. List[Struct])
                    subtypes = re.findall(r"([a-zA-Z_][a-zA-Z0-9_.]*)", rtype)
                    for t in subtypes:
                        if t in self.structs or t in self.enums:
                            initial_types.add(t)

                    # Args
                    for arg in m["args"]:
                        atype = arg["type"]
                        subtypes = re.findall(r"([a-zA-Z_][a-zA-Z0-9_.]*)", atype)
                        for t in subtypes:
                            if t in self.structs or t in self.enums:
                                initial_types.add(t)

                # Resolve dependencies recursively
                for t in initial_types:
                    if t in self.structs:
                        self.get_dependencies(t, all_types)
                    else:
                        all_types.add(t)
            else:
                # Fallback: look for structs starting with the service name (e.g. SquareService_...)
                print(f"Service '{root_service}' not found in definitions. Searching for related structs via prefix '{root_service}_'...")
                found_service_structs = False
                prefix = root_service + "_"
                for struct_name in self.structs:
                    if struct_name.startswith(prefix):
                        found_service_structs = True
                        self.get_dependencies(struct_name, all_types)

                if not found_service_structs and self.service_source_file:
                    # Fallback 2: Extract method names from external source file (e.g. TalkService.py)
                    print(f"Extraction from source file '{self.service_source_file}'...")
                    try:
                        import ast
                        with open(self.service_source_file, "r", encoding="utf-8-sig") as f:
                            tree = ast.parse(f.read())

                        source_methods = [
                            node.name for node in ast.walk(tree)
                            if isinstance(node, ast.FunctionDef) and not node.name.startswith("__")
                        ]

                        found_source_methods = False
                        for method in source_methods:
                            # Try standard patterns: {Method}_args, {Service}_{Method}_args
                            candidates = [
                                f"{method}_args",
                                f"{root_service}_{method}_args"
                            ]
                            for cand in candidates:
                                if cand in self.structs:
                                    found_source_methods = True
                                    self.get_dependencies(cand, all_types)
                                    # Also look for result
                                    res_cand = cand.replace("_args", "_result")
                                    if res_cand in self.structs:
                                        self.get_dependencies(res_cand, all_types)

                        if found_source_methods:
                             print(f"Found related structs via source file analysis.")
                        else:
                             print(f"Warning: No matching structs found even after source file analysis.")

                    except Exception as e:
                        print(f"Error parsing source file: {e}")

                elif not found_service_structs:
                    print(f"Warning: Service '{root_service}' not found and no matching structs found.")

        else:
            # Fallback to pattern matching
            for name in list(self.structs.keys()) + list(self.enums.keys()):
                matched = False
                if self.patterns:
                    for p in self.patterns:
                        if re.search(p, name):
                            matched = True
                            break
                else:
                    matched = True  # If no patterns, include everything

                if matched:
                    if name in self.structs:
                        self.get_dependencies(name, all_types)
                    else:
                        all_types.add(name)

        # Generate code
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

                if fname.isdigit() or not fname[0].isalpha():
                    fname = f"arg_{fname}"

                if fname in self.RESERVED_PYTHON_KEYWORDS:
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

        if service_name not in self.services:
            print(f"Service {service_name} not found in parsed files.")
            lines.append("    pass")
            return "\n".join(lines)

        service_def = self.services[service_name]
        methods = sorted(service_def["methods"], key=lambda x: x["name"])

        if not methods:
            lines.append("    pass")
            return "\n".join(lines)

        for m in methods:
            args = m["args"]

            # Fallback for empty args: look for {Service}_{Method}_args or {Method}_args struct
            if not args:
                lookup_names = [f"{service_name}_{m['name']}_args", f"{m['name']}_args"]
                for lname in lookup_names:
                    if lname in self.structs:
                        struct_def = self.structs[lname]
                        for f in struct_def["fields"]:
                            # Convert struct field to arg format
                            args.append({
                                "id": int(f["id"]),
                                "type": f["type"],
                                "name": f["name"]
                            })
                        break

            # AUTO-FLATTEN check
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

            method_py_name = self.to_snake_case(m["name"])
            res_type_py, _ = self._resolve_type(m["return_type"])

            # Try to refine response type from _result struct logic
            # (If return type is void or implicit, we might find it in {Method}_result struct field 0)
            if m["return_type"] == "void" or not m["return_type"]:
               lookup_names = [f"{service_name}_{m['name']}_result", f"{m['name']}_result"]
               for lname in lookup_names:
                   if lname in self.structs:
                       for f in self.structs[lname]["fields"]:
                           if f["id"] == "0":
                               res_type_py, _ = self._resolve_type(f["type"])
                               break
                       break

            sig_args = ["self"]
            for arg in args:
                f_name = self.to_snake_case(arg["name"])
                if f_name.isdigit() or not f_name[0].isalpha(): f_name = f"arg_{f_name}"
                if f_name in self.RESERVED_PYTHON_KEYWORDS: f_name += "_"

                f_type_py, _ = self._resolve_type(arg["type"])
                if "Optional" not in f_type_py:
                     f_type_py = f"Optional[{f_type_py}]"

                sig_args.append(f"{f_name}: {f_type_py} = None")

            lines.append(
                f"    def {method_py_name}({', '.join(sig_args)}) -> {res_type_py}:"
            )
            lines.append(f"        params = []")

            for arg in args:
                f_name = self.to_snake_case(arg["name"])
                if f_name.isdigit() or not f_name[0].isalpha(): f_name = f"arg_{f_name}"
                if f_name in self.RESERVED_PYTHON_KEYWORDS: f_name += "_"

                ftype_id = self.get_ttype_id(arg["type"])

                lines.append(f"        if {f_name} is not None:")
                lines.append(f"            params.append([{ftype_id}, {arg['id']}, {f_name}])")

            res_model = res_type_py if res_type_py != "None" else "None"

            lines.append(
                f'        return self._call("{m["name"]}", [[12, 1, params]], response_model={res_model})'
            )
            lines.append("")

        return "\n".join(lines)

    def get_ttype_id(self, thrift_type: str) -> int:
        mapping = {
            "bool": 2, "byte": 3, "double": 4, "i16": 6, "i32": 8, "i64": 10,
            "string": 11, "binary": 11, "struct": 12, "map": 13, "set": 14, "list": 15
        }
        if thrift_type in mapping: return mapping[thrift_type]
        if thrift_type.startswith("map<"): return 13
        if thrift_type.startswith("list<"): return 15
        if thrift_type.startswith("set<"): return 14
        if thrift_type in self.enums: return 8
        return 12


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
    parser.add_argument("--service-source", help="Path to Python source file to extract method names from (for fallback)")
    args = parser.parse_args()

    patterns = args.patterns.split(",")
    thrift_parser = ThriftParser(
        args.input, args.output, patterns, snake_case=args.snake_case, service_source_file=args.service_source
    )
    thrift_parser.parse()

    if args.output:
        code = thrift_parser.generate_code(root_service=args.service)
        with open(args.output, "w") as f:
            f.write(code)
        print(f"Generated models to {args.output}")

    if args.service and args.service_output:
        code = thrift_parser.generate_service(args.service, endpoint=args.endpoint or "/S4")
        with open(args.service_output, "w") as f:
            f.write(code)
        print(f"Generated service {args.service} to {args.service_output}")
