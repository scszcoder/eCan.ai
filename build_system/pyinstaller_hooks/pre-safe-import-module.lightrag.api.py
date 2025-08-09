# Prevent argparse from evaluating sys.argv during Analysis isolation child
import sys

# Some lightrag.api modules import config at import time; clear extraneous args
if hasattr(sys, 'argv') and len(sys.argv) > 1:
    sys.argv = [sys.argv[0]]

