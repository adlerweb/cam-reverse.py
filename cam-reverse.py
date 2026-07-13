#!/usr/bin/env python3
"""Launcher for the Python cam-reverse client.

Run directly from a checkout (no install needed):

    python cam-reverse.py http_server --config_file config.yml

or, once installed, as the ``cam-reverse.py`` command / ``python -m cam_reverse``.
"""
from cam_reverse.cli import main

if __name__ == "__main__":
    main()
