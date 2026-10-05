"""Worker markers report stages; elapsed time is useful before the first frame."""
import json


def read_markers(lines, run):
    fields = {'PIPELINE_SETTINGS ': 'actual_settings', 'PIPELINE_DEVICE ': 'render_device',
              'PIPELINE_COMPOSITOR_OUTPUTS ': 'compositor_outputs', 'PIPELINE_TIMING ': 'timing'}
    for line in lines:
        for prefix, field in fields.items():
            if line.startswith(prefix):
                try: run[field] = json.loads(line[len(prefix):])
                except ValueError: pass
        if line.startswith('PIPELINE_STAGE '):
            try:
                marker = json.loads(line[len('PIPELINE_STAGE '):])
                run['phase'] = marker['phase']
                if 'frame' in marker: run['current_frame'] = marker['frame']
            except (ValueError, KeyError, TypeError): pass
        if line.startswith('PIPELINE_FRAME '):
            try:
                frame = json.loads(line[len('PIPELINE_FRAME '):])['frame']
                written = set(run.get('written_frames', [])); written.add(frame)
                run['written_frames'] = sorted(written); run['frame'] = frame
                config = run['config']; count = len(range(config['start'], config['end'] + 1, config.get('step', 1)))
                run['progress'] = max(0, min(99, int(100 * len(written) / max(1, count))))
            except (ValueError, KeyError, TypeError): pass
