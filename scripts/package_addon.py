"""Generate the installable add-on; the ZIP is a build output, not source."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from blender_pipeline.adapters.addon_package import build_addon

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'Pipeline_Companion.zip')
    args = parser.parse_args()
    print(build_addon(args.output))
