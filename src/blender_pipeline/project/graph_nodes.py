"""Graph-only containers; these operations never create or relocate directories."""
import copy
import math
from blender_pipeline.project.model import uid, stamp


class GraphNodes:
    def physical_folder(self, group_id):
        """Resolve visual placement separately from the nearest disk folder."""
        seen = set()
        while group_id:
            if group_id in seen:
                raise ValueError('Invalid container hierarchy.')
            seen.add(group_id)
            node = self.node(group_id)
            if node['type'] == 'folder':
                return node['id']
            if node['type'] != 'frame':
                raise ValueError('Choose a frame or folder.')
            group_id = node.get('group')
        return None

    def graph_position(self, x, y):
        values = [float(70 if x is None else x), float(70 if y is None else y)]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Use finite graph coordinates.')
        return dict(zip(('x', 'y'), values))

    def frame(self, title=None, node_ids=None, group=None, x=None, y=None, width=650, height=420):
        members = [self.node(i) for i in dict.fromkeys(node_ids or [])]
        if group and any(n['id'] == group for n in members):
            raise ValueError('A selected node cannot also be the parent frame.')
        title = str(title or 'Frame').strip()
        if not title or len(title) > 120:
            raise ValueError('Use a frame name between 1 and 120 characters.')
        width, height = max(300, float(width)), max(150, float(height))
        if not all(math.isfinite(v) for v in (width, height)):
            raise ValueError('Use finite frame dimensions.')
        frame = {'id': uid(), 'type': 'frame', 'name': title, 'group': group,
                 'width': width, 'height': height, 'collapsed': False,
                 **self.graph_position(x, y)}
        before = copy.deepcopy(self.data)
        try:
            self.data['nodes'].append(frame)
            for node in members:
                node['group'] = frame['id']
            self.validate_groups(self.data['nodes'])
            self.fit_frames()
            self.save()
        except Exception:
            self.data = before
            raise
        return self.state()

    def remove_graph_node(self, node_id, confirmed=False):
        if not confirmed:
            raise ValueError('Confirm removal first.')
        node = self.node(node_id)
        if node['type'] not in {'frame', 'export', 'render'}:
            raise ValueError('Use the file or folder archive action for this node.')
        if node['type']=='render' and any(q.get('operation_id')==node_id and q['status'] in {'Queued','Preparing','Rendering'} for q in self.data.get('render_queue',[])):
            raise ValueError('Finish or cancel this Render node’s jobs before removing it.')
        before = copy.deepcopy(self.data)
        record = {'id': uid(), 'node': copy.deepcopy(node), 'archived_at': stamp(), 'children': []}
        try:
            for child in self.data['nodes']:
                if child.get('group') == node_id:
                    record['children'].append(child['id'])
                    child['group'] = node.get('group')
            self.data['nodes'] = [n for n in self.data['nodes'] if n['id'] != node_id]
            self.data.setdefault('archived_graph_nodes', []).append(record)
            self.save()
        except Exception:
            self.data = before
            raise
        return self.state()

    def restore_graph_node(self, archive_id):
        record = next((r for r in self.data.get('archived_graph_nodes', []) if r['id'] == archive_id), None)
        if not record:
            raise ValueError('Archived graph node not found.')
        node = copy.deepcopy(record['node'])
        if any(n['id'] == node['id'] for n in self.data['nodes']):
            raise ValueError('This node is already registered.')
        before = copy.deepcopy(self.data)
        try:
            if not any(n['id'] == node.get('group') and n['type'] in {'frame', 'folder'} for n in self.data['nodes']):
                node['group'] = None
            node['hidden'] = False
            self.data['nodes'].append(node)
            for child in self.data['nodes']:
                if child['id'] in record['children'] and child.get('group') == node.get('group'):
                    child['group'] = node['id']
            self.validate_groups(self.data['nodes'])
            self.data['archived_graph_nodes'].remove(record)
            self.save()
        except Exception:
            self.data = before
            raise
        return self.state()
