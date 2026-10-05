"""Read sequential jobs while retaining Blender's process/device initialization."""
import json
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).parent))
from render_job import execute

for line in sys.stdin:
    request = json.loads(line)
    ok = False
    try:
        execute(json.loads(Path(request['path']).read_text(encoding='utf-8')))
        ok = True
    except Exception:
        traceback.print_exc(file=sys.stdout)
    print('PIPELINE_JOB_END ' + json.dumps({'run_id': request['run_id'], 'ok': ok, 'pid': os.getpid()}), flush=True)
