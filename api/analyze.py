import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from darkspot.api import make_handler, do_analyze

handler = make_handler(do_analyze)
