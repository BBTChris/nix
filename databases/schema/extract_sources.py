#!/usr/bin/env python3
"""Extract every filename=-tagged fenced block from the spec into files."""

import os
import re
import sys

spec_path = sys.argv[1] if len(sys.argv) > 1 else "nix_db_schema_spec.md"
spec = open(spec_path).read()
for m in re.finditer(
    r"^``[`]\w+ filename=(\S+)\n(.*?)\n``[`]$", spec, re.DOTALL | re.MULTILINE
):
    name, body = m.group(1), m.group(2) + "\n"
    open(name, "w").write(body)
    if name.endswith(".sh"):
        os.chmod(name, 0o755)
    print("extracted", name)
