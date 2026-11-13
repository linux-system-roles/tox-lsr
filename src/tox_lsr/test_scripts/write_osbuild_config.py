#!/usr/bin/env python
"""Convert role osbuild customizations into json or toml blueprint format."""

import argparse
import datetime
import json
import math
import os
import re
import sys

import yaml

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_SIMPLE_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def dict_to_toml(data: dict) -> str:
    """Return *data* serialized as a TOML 1.0 string."""
    if not isinstance(data, dict):
        raise TypeError(f"expected a dict, got {type(data).__name__}")
    lines: list[str] = []
    _emit_table(data, [], lines)
    return "\n".join(lines)


def _emit_table(table: dict, path: list, lines: list[str]) -> None:
    """Emit one table's plain key/values first, then its sub-tables."""
    scalars, subtables = [], []
    for key, value in table.items():
        if isinstance(value, tuple):
            value = list(value)
        if isinstance(value, dict):
            subtables.append((key, value, False))
        elif _is_table_array(value):
            subtables.append((key, value, True))
        else:
            scalars.append((key, value))

    # Plain values must appear before any [table] header.
    for key, value in scalars:
        lines.append(f"{_key(key)} = {_value(value)}")

    for key, value, is_array in subtables:
        child = [*path, key]
        header = ".".join(_key(k) for k in child)
        for item in value if is_array else (value,):
            if lines:  # blank line between blocks keeps output readable
                lines.append("")
            lines.append(f"[[{header}]]" if is_array else f"[{header}]")
            _emit_table(item, child, lines)


def _is_table_array(value) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) for item in value)
    )


def _value(value) -> str:
    """Format a value in inline (single-line) form."""
    if isinstance(value, tuple):
        value = list(value)
    if value is None:
        raise TypeError("TOML has no null value; drop None before serializing")
    if isinstance(value, bool):  # before int: bool subclasses int
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)  # always keeps a '.' or exponent
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()  # valid TOML date/time
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, dict):  # dict inside a list -> inline table
        if not value:
            return "{}"
        items = ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items())
        return "{ " + items + " }"
    raise TypeError(f"cannot serialize {type(value).__name__} to TOML")


def _key(key) -> str:
    """Format a key: bare when possible, quoted otherwise."""
    if isinstance(key, bool):
        raise TypeError(f"bool is not a valid TOML key: {key!r}")
    if isinstance(key, int):  # TOML allows all-digit bare keys
        return str(key)
    if not isinstance(key, str):
        raise TypeError(
            f"TOML keys must be str or int, got {type(key).__name__}"
        )
    return key if _BARE_KEY.fullmatch(key) else _basic_string(key)


def _string(s: str) -> str:
    """Pick a single-line or multi-line basic string."""
    return _multiline_string(s) if "\n" in s else _basic_string(s)


def _basic_string(s: str) -> str:
    out = []
    for ch in s:
        if ch in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:  # other control chars
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return f'"{"".join(out)}"'


def _multiline_string(s: str) -> str:
    out = []
    for ch in s:
        if ch in ("\\", '"'):
            out.append("\\" + ch)
        elif ch in "\t\n":  # kept literally in multi-line strings
            out.append(ch)
        elif ch in "\r\b\f":
            out.append(_SIMPLE_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    # Every parser trims the newline right after the opening """, so emit
    # one separator newline; the body then survives verbatim.
    return f'"""\n{"".join(out)}"""'


def main():
    """Parse CLI arguments and install any missing requirements."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=str, help="Input file")
    parser.add_argument(
        "--pubkey", type=str, required=True, help="Root ssh pubkey"
    )
    parser.add_argument(
        "--output", type=str, required=True, help="Output file"
    )
    parser.add_argument(
        "--format",
        choices=["json", "toml"],
        required=True,
        help="Output format",
    )
    args = parser.parse_args()

    # add root user password and ssh pubkey
    cfg = {
        "blueprint": {
            "customizations": {
                "user": [
                    {
                        "name": "root",
                        "password": "foobar",
                        "key": args.pubkey,
                    }  # nosec B105
                ]
            }
        }
    }
    # add any role user customizations
    if args.input and os.path.exists(args.input):
        with open(args.input, "r") as f:
            user_cfg = yaml.safe_load(f)
        if "blueprint" in user_cfg:
            users = (
                user_cfg["blueprint"].get("customizations", {}).get("user", [])
            )
        elif "customizations" in user_cfg:
            users = user_cfg["customizations"].get("user", [])
        rootuser = [u for u in users if u["name"] == "root"]
        if rootuser:
            print("ERROR: cannot override root user in osbuild_config.yml")
            sys.exit(1)
        cfg["blueprint"]["customizations"]["user"].extend(users)

    if args.format == "toml":
        # add fields required by blueprint
        cfg["blueprint"]["name"] = "lsr-bootc"
        cfg["blueprint"]["description"] = "lsr bootc blueprint"
        cfg["blueprint"]["version"] = "0.0.1"
        out_string = dict_to_toml(cfg["blueprint"])
    else:
        out_string = json.dumps(cfg)

    with open(args.output, "w") as of:
        of.write(out_string)


if __name__ == "__main__":
    main()
