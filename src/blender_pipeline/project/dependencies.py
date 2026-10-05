"""Read-only dependency impact and output freshness derived from saved observations."""
import os
from pathlib import Path
from blender_pipeline.rendering.images import inspect_image


def file_signature(path):
    try:
        info = Path(path).stat()
        return [info.st_mtime_ns, info.st_size]
    except OSError:
        return None


def dependency_health(pipeline, runtime):
    nodes = {n['id']: n for n in pipeline.data['nodes']}
    blends = {i: n for i, n in nodes.items() if n['type'] == 'blend'}
    paths, resolved = {}, {}
    for identity, node in blends.items():
        try:
            path = pipeline.path(node)
            paths[os.path.normcase(str(path))] = identity
            resolved[identity] = path
        except ValueError:
            pass
    upstream = {i: set() for i in blends}
    downstream = {i: set() for i in blends}
    for identity, node in blends.items():
        for ref in node.get('scan', {}).get('refs', []):
            if ref.get('kind') != 'Library':
                continue
            source = paths.get(os.path.normcase(str(Path(ref['path']).resolve())))
            if source and source != identity:
                upstream[identity].add(source); downstream[source].add(identity)

    def closure(start, edges):
        visited, pending = {start}, list(edges.get(start, []))
        while pending:
            identity = pending.pop()
            if identity in visited:
                continue
            visited.add(identity); pending.extend(edges.get(identity, []))
        return sorted(visited - {start})

    dirty = {i for i, path in resolved.items() if pipeline.companion and any(s['dirty'] for s in pipeline.companion.opened(path))}
    health = {}
    for identity, node in blends.items():
        own = runtime.get(identity, {})
        reasons = []
        if own.get('missing') or node.get('scan', {}).get('error'):
            reasons.append({'kind': 'missing', 'source_id': identity, 'message': own.get('error') or node.get('scan',{}).get('error','File missing')})
        if identity in dirty:
            reasons.append({'kind': 'unsaved', 'source_id': identity})
        if own.get('changed') and not own.get('missing'):
            reasons.append({'kind': 'saved_change', 'source_id': identity})
        images = []
        for ref in node.get('scan', {}).get('refs', []):
            if ref.get('kind') != 'Image': continue
            try: issue = inspect_image(pipeline, node, ref)
            except (ValueError, OSError): issue = dict(ref, severity='warning')
            if issue: images.append(issue)
        for severity, kind in [('warning', 'image_dependency'), ('notice', 'image_notice')]:
            entries = [image for image in images if image['severity'] == severity]
            if entries:
                reasons.append({'kind': kind, 'source_id': identity,
                                'assets': [{'kind': 'Image', 'name': r.get('name') or r['path']} for r in entries],
                                'message': '\n'.join(r['path'] for r in entries)})
        for source in closure(identity, upstream):
            if source in dirty:
                reasons.append({'kind': 'unsaved_upstream', 'source_id': source})
            if runtime.get(source, {}).get('missing') or blends[source].get('scan', {}).get('error'):
                reasons.append({'kind': 'missing_upstream', 'source_id': source})
            if runtime.get(source, {}).get('changed'):
                reasons.append({'kind': 'source_updated', 'source_id': source})
        for source in sorted(upstream[identity]):
            saved_hash = blends[source].get('scan', {}).get('hash')
            previous = node.get('dependency_hashes', {}).get(source)
            if previous and saved_hash and previous != saved_hash:
                reasons.append({'kind': 'source_updated', 'source_id': source})
                catalog = {(d['kind'], d['name']) for d in blends[source].get('scan', {}).get('datablocks', [])}
                source_path = os.path.normcase(str(resolved.get(source, '')))
                linked = [(d.get('kind', 'collections'), d.get('name', d.get('collection'))) for d in
                          [*node.get('scan', {}).get('instances', []), *node.get('scan', {}).get('data_links', [])]
                          if os.path.normcase(str(Path(d.get('source', '')).resolve())) == source_path]
                missing = [{'kind': kind, 'name': name} for kind, name in linked
                           if 'datablocks' in blends[source].get('scan', {}) and (kind, name) not in catalog]
                if missing:
                    reasons.append({'kind': 'asset_missing', 'source_id': source, 'assets': missing[:20]})
        health[identity] = {'reasons': reasons, 'upstream': closure(identity, upstream),
                            'affected': closure(identity, downstream), 'dirty': identity in dirty}
    # Propagate a source's pending library update through intermediate scene files.
    for identity in blends:
        known = {r['source_id'] for r in health[identity]['reasons'] if r['kind'] == 'source_updated'}
        for dependency in health[identity]['upstream']:
            for reason in health[dependency]['reasons']:
                if reason['kind'] == 'source_updated' and reason['source_id'] not in known:
                    known.add(reason['source_id']); health[identity]['reasons'].append(reason)

    outputs = {'renders': {}, 'exports': {}}
    signatures = {}
    for field, hash_key in [('renders', 'input_hashes'), ('exports', 'inputs')]:
        for run in pipeline.data.get(field, []):
            if run['status'] != 'Complete':
                continue
            changed, unsaved, unknown = [], [], [w['path'] for w in run.get('dependency_warnings', [])]
            for relative, expected in run.get(hash_key, {}).items():
                path = (pipeline.root / relative).resolve()
                if not path.is_relative_to(pipeline.root):
                    changed.append(relative); continue
                key = str(path)
                if key not in signatures:
                    signatures[key] = file_signature(path)
                signature = signatures[key]
                source = paths.get(os.path.normcase(str(path)))
                captured = run.get('input_signatures', {}).get(relative)
                if signature is None or captured and signature != captured or source and runtime.get(source, {}).get('changed'):
                    changed.append(relative)
                elif source and blends[source].get('scan', {}).get('hash') not in {None, expected}:
                    changed.append(relative)
                elif not source and not captured:
                    unknown.append(relative)
                if source in dirty:
                    unsaved.append(relative)
            for image in run.get('image_inputs', []):
                path = (pipeline.root / image['source_relative']).resolve() if image.get('source_relative') else Path(image['source_path'])
                key = str(path)
                if key not in signatures: signatures[key] = file_signature(path)
                replacement = pipeline.data.get('image_replacements', {}).get(image.get('image_id'))
                replacement_changed = image.get('replacement') and (not replacement or replacement['path'] != image.get('source_relative'))
                if signatures[key] != image['signature'] or replacement_changed:
                    changed.append(image['original_path'])
            outputs[field][run['id']] = {'outdated': bool(changed), 'changed_inputs': changed,
                                        'unsaved_inputs': unsaved, 'unverified_inputs': unknown}
    for node in nodes.values():
        if node['type'] not in {'render', 'export'}:
            continue
        inputs = [t['source_id'] for t in node['render_plan']['targets'] if t['enabled']] if node['type'] == 'render' else [node.get('export_config', {}).get('source_id')]
        health[node['id']] = {'reasons': [r for i in dict.fromkeys(inputs) for r in health.get(i, {}).get('reasons', [])],
                              'upstream': [i for i in dict.fromkeys(inputs) if i], 'affected': []}
        if any(i and i not in blends for i in inputs):
            health[node['id']]['reasons'].append({'kind': 'missing_upstream', 'source_id': next(i for i in inputs if i and i not in blends)})
        if node['type']=='render':
            for target in node['render_plan']['targets']:
                source=blends.get(target['source_id'])
                if target['enabled'] and source and not any(s['name']==target['scene'] and not s.get('linked') for s in source.get('scan',{}).get('scenes',[])):
                    health[node['id']]['reasons'].append({'kind':'missing_scene','source_id':source['id']})
                elif target['enabled'] and source:
                    scene=next(s for s in source['scan']['scenes'] if s['name']==target['scene'] and not s.get('linked'))
                    if target.get('view_layer') and not any(l['name']==target['view_layer'] for l in scene.get('view_layers',[])):
                        health[node['id']]['reasons'].append({'kind':'missing_layer','source_id':source['id']})
                    if (target.get('camera') or scene.get('camera')) not in scene.get('cameras',[]):
                        health[node['id']]['reasons'].append({'kind':'missing_camera','source_id':source['id']})
    return {'nodes': health, 'outputs': outputs}
