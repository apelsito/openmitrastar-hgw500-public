#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--min", type=int, default=5)
    args = ap.parse_args()
    data = args.path.read_bytes()
    pat = rb"[\x20-\x7e]{" + str(args.min).encode() + rb",}"
    try:
        for m in re.finditer(pat, data):
            print(m.group().decode("ascii", "replace"))
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
