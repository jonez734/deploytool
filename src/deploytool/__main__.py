#!/usr/bin/env python3
import sys

from . import lib


def main():
    parser = lib.buildargs()
    args = parser.parse_args()
    lib.runmodule(args, "main", argv=sys.argv[1:])


if __name__ == "__main__":
    main()
