"""Run from a source checkout without installation or a build system."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from blender_pipeline.__main__ import main

if __name__ == '__main__':
    main()
