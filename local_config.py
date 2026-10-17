"""Read private device configuration without executing shell code."""
import os
from pathlib import Path


def get_port(name):
    values = {}
    config = Path(__file__).resolve().parent / "robot_ports.env"
    if config.exists():
        for line in config.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip(chr(34) + chr(39))
    value = os.environ.get(name) or values.get(name)
    if not value or "REPLACE_" in value:
        raise RuntimeError(f"Configure {name} in robot_ports.env (see robot_ports.env.example)")
    return value
