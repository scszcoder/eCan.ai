#!/usr/bin/env python3
"""
eCan.ai CLI Entry Point

Run with:
    python ecan_cli.py [COMMAND] [OPTIONS]
    
Or after installation:
    ecan [COMMAND] [OPTIONS]
"""

import sys
import os

# Force UTF-8 encoding for all file operations (Windows compatibility)
os.environ['PYTHONUTF8'] = '1'

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set ECAN_MODE before importing anything else
os.environ.setdefault('ECAN_MODE', 'web')

from cli.main import main

if __name__ == "__main__":
    main()
