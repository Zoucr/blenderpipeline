"""Local project model and transaction-safe Blender operations; standard library only."""
import copy, hashlib, json, math, os, shutil, subprocess, tempfile, uuid
from datetime import datetime, timezone
from pathlib import Path
from blender_pipeline.storage.projects import CURRENT_SCHEMA, JsonProjectRepository, atomic_json
from blender_pipeline.adapters.blender_runtime import BlenderRuntime
from blender_pipeline.adapters.desktop import DesktopIntegration
from blender_pipeline.storage.file_references import FileResolver

from blender_pipeline.paths import DATA_DIR, BLENDER_SCRIPTS_DIR, DEFAULT_BLENDER
META = '.pipeline'

def uid(): return uuid.uuid4().hex
def stamp(): return datetime.now(timezone.utc).isoformat()
def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
def name(value):
    value = str(value).strip()
    if not value or value in {'.','..'} or any(c in value for c in '<>:"/\\|?*') or value.endswith(('.', ' ')):
        raise ValueError('Use a simple file name without path separators or reserved characters.')
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        raise ValueError('Reserved Windows name.')
    return value

class Pipeline:
    def __init__(self, repository=None, runtime=None, desktop=None, resolver=None, data_directory=None):
        self.settings_directory = Path(data_directory) if data_directory is not None else DATA_DIR
        self.repository = repository if repository is not None else JsonProjectRepository()
        self.runtime = runtime if runtime is not None else BlenderRuntime(BLENDER_SCRIPTS_DIR)
        self.desktop = desktop if desktop is not None else DesktopIntegration()
        self.resolver = resolver if resolver is not None else FileResolver(self.settings_directory)
        self.local_view = None
        self.root = None
        self.data = None
        self.processes = {}
        self.blender = DEFAULT_BLENDER
        self.registry = self.settings_directory/'recent-projects.json'
        try:
            self.blender=json.loads((self.settings_directory/'settings.json').read_text(encoding='utf-8'))['blender']
        except (OSError,ValueError,KeyError): pass
    def recent(self):
        try: return json.loads(self.registry.read_text(encoding='utf-8'))
        except (OSError, ValueError): return []
    def save(self):
        for node in self.data['nodes']:
            self.resolver.normalize(self.data['id'], node)
        self.repository.save(self.root, self.data)
    def reload_metadata(self):
        loaded=self.repository.load(self.root)
        if self.data and loaded['id']!=self.data['id']:raise ValueError('Project identity changed on disk. Reload stopped.')
        # Running threads own these record objects. Preserve identity when discarding
        # a rejected speculative edit, otherwise completion updates would be orphaned.
        for field in ('renders','render_queue'):
            current={entry['id']:entry for entry in (self.data or {}).get(field,[])}
            entries=[]
            for fresh in loaded.get(field,[]):
                existing=current.get(fresh['id'])
                if existing is not None:existing.clear();existing.update(fresh);entries.append(existing)
                else:entries.append(fresh)
            if field in loaded:loaded[field]=entries
        self.data=loaded
    def remember(self):
        key=os.path.normcase(str(self.root))
        previous=next((r for r in self.recent() if os.path.normcase(r['path'])==key),{})
        recent = [r for r in self.recent() if os.path.normcase(r['path']) != key]
        recent.insert(0, {**previous,'id':self.data['id'],'name': self.data['name'], 'path': str(self.root),'opened_at':stamp()})
        atomic_json(self.registry, recent)
    def create(self, parent, title):
        root = Path(parent).resolve()/name(title)
        if root.exists(): raise ValueError('Choose a new project name; that folder already exists.')
        root.mkdir(parents=True)
        (root/META).mkdir()
        self.root = root
        self.local_view = None
        self.data = {'schema':CURRENT_SCHEMA, 'revision':0, 'name':title, 'id':uid(), 'nodes':[], 'view':{'x':0,'y':0,'zoom':1}}
        self.save(); self.remember()
        return self.state()
    def load(self, path):
        root = Path(path).resolve()
        data = self.repository.load(root)
        self.root, self.data = root, data
        self.local_view = None
        self.remember()
        return self.state()
    def state(self):
        desktop = self.desktop_available()
        warning = '' if desktop else 'This server runs under the Codex sandbox account. Double-click Launch.cmd in File Explorer and use its NEW browser tab to open Blender and folders on your desktop.'
        if not self.data: return {'project':None, 'recent':self.recent(), 'blender':self.blender, 'build':'1.1',
                                 'desktop_available':desktop, 'desktop_warning':warning}
        runtime={}
        for node in self.data['nodes']:
            if node['type']!='blend': continue
            try:
                stat=self.path(node).stat()
                runtime[node['id']]={'mtime':stat.st_mtime_ns,'size':stat.st_size,
                    'resolved_path':str(self.path(node)),
                    'changed':node.get('scan',{}).get('signature')!=[stat.st_mtime_ns,stat.st_size]}
            except (OSError, ValueError) as exc:runtime[node['id']]={'missing':True,'changed':True,'error':str(exc)}
        project=copy.deepcopy(self.data)
        project['view']=copy.deepcopy(self.local_view or self.data['view'])
        for node in project['nodes']:node['file_ref']=self.resolver.reference(node)
        return {'project':project, 'root':str(self.root), 'recent':self.recent(), 'blender':self.blender, 'build':'1.1',
                'files':runtime,
                'desktop_available':desktop, 'desktop_warning':warning,
                'open':[key for key,p in self.processes.items() if p.poll() is None]}
    def desktop_available(self):
        return self.desktop.available()
    def require_desktop(self):
        self.desktop.require(self.desktop_available())
    def start_blender(self, path):
        return self.desktop.start_blender(self.blender, path, self.root/META/'logs', self.desktop_available())
    def node(self, node_id):
        if not self.data: raise ValueError('Create or open a project first.')
        return next(n for n in self.data['nodes'] if n['id']==node_id)
    def path(self, node):
        return self.resolver.resolve(self.root, self.data['id'], node)
    def ensure_closed(self, node, acknowledged):
        process = self.processes.get(node['id'])
        if process and process.poll() is None: raise ValueError('Close this file’s launched Blender window before changing it.')
        if not acknowledged: raise ValueError('Confirm the destination file is closed in Blender.')
    def run(self, script, args, opened=None):
        return self.runtime.run(self.blender, script, args, opened)
    def inspect(self, node):
        try:path = self.path(node)
        except ValueError as exc:
            node['scan']={'error':str(exc),'refs':[],'collections':[],'instances':[]};return
        if not path.exists():
            node['scan']={'error':'File missing','refs':[],'collections':[],'instances':[]}; return
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'scan.json'
            try:
                before=path.stat()
                signature=[before.st_mtime_ns,before.st_size]
                self.run('scan_blend.py',[output],path)
                scan = json.loads(output.read_text(encoding='utf-8'))
                scan['error']=''
                for ref in scan['refs']: ref['inside']=Path(ref['path']).resolve().is_relative_to(self.root)
                scan['hash']=digest(path)
                stat=path.stat()
                scan['signature']=signature
                if signature!=[stat.st_mtime_ns,stat.st_size]:
                    scan['error']='File changed while scanning. Refresh again after Blender finishes saving.'
                scan['scanned_at']=stamp()
                node['scan']=scan
            except Exception as exc:
                node['scan']={'error':str(exc),'refs':[],'collections':[],'instances':[]}
    def refresh(self,node_id=None):
        for node in self.data['nodes']:
            if node['type']=='blend' and (node_id is None or node['id']==node_id): self.inspect(node)
        self.save(); return self.state()
    def organize(self,node_id,closed):
        node=self.node(node_id)
        self.ensure_closed(node,closed)
        self.inspect(node)
        if node['scan'].get('error'): raise ValueError(node['scan']['error'])
        if not node['scan'].get('root_objects'): raise ValueError('There are no loose scene-root objects to collect.')
        self.snapshot(node_id,'Before collecting scene-root objects')
        self.transaction(node,{'action':'organize','collection':'Scene Contents'})
        self.inspect(node);self.save();return self.state()
    def label(self,node_id,title):
        node=self.node(node_id)
        title=str(title).strip()
        if not title or len(title)>120: raise ValueError('Use a label between 1 and 120 characters.')
        node['name']=title
        self.save();return self.state()
    def folder(self, title, folder_id=None, x=None, y=None):
        parent = self.path(self.node(folder_id)) if folder_id else self.root
        if folder_id and self.node(folder_id)['type']!='folder': raise ValueError('Choose a folder node.')
        target = parent/name(title)
        if target.exists(): raise ValueError('Folder already exists.')
        target.mkdir()
        node={'id':uid(),'type':'folder','name':title,'path':target.relative_to(self.root).as_posix(),'x':70+len(self.data['nodes'])*270,'y':70}
        if x is not None:node['x']=float(x)
        if y is not None:node['y']=float(y)
        self.data['nodes'].append(node); self.save(); return self.state()
    def create_blend(self, title=None, folder_id=None, template=None, x=None, y=None):
        parent=self.path(self.node(folder_id)) if folder_id else self.root
        if folder_id and self.node(folder_id)['type']!='folder': raise ValueError('Choose a folder node.')
        if not title:
            number=1
            while (parent/f'Untitled {number:03}.blend').exists():number+=1
            title=f'Untitled {number:03}'
        title=name(title)
        target=parent/(title if title.lower().endswith('.blend') else title+'.blend')
        if target.exists(): raise ValueError('File already exists.')
        node={'id':uid(),'type':'blend','name':target.stem,'path':target.relative_to(self.root).as_posix(),'x':70+(len(self.data['nodes'])%3)*300,'y':200+(len(self.data['nodes'])//3)*260,'snapshots':[]}
        if x is not None:node['x']=float(x)
        if y is not None:node['y']=float(y)
        self.transaction(node,{'action':'create','template':str(Path(template).resolve()) if template else None},new=True)
        self.data['nodes'].append(node); self.inspect(node); self.save(); return self.state()
    def import_blend(self, source, folder_id=None, x=None, y=None):
        source=Path(source).resolve()
        if source.suffix.lower()!='.blend' or not source.is_file(): raise ValueError('Choose an existing .blend file.')
        if source.is_relative_to(self.root/META): raise ValueError('Snapshots must be restored or opened as copies.')
        if source.is_relative_to(self.root): target=source
        else:
            parent=self.path(self.node(folder_id)) if folder_id else self.root
            target=parent/source.name
            if target.exists(): raise ValueError('Destination already exists.')
            shutil.copy2(source,target)
        if any(self.path(n)==target for n in self.data['nodes']): raise ValueError('File is already in this graph.')
        node={'id':uid(),'type':'blend','name':target.stem,'path':target.relative_to(self.root).as_posix(),'x':70+(len(self.data['nodes'])%3)*300,'y':200+(len(self.data['nodes'])//3)*260,'snapshots':[]}
        if x is not None:node['x']=float(x)
        if y is not None:node['y']=float(y)
        self.data['nodes'].append(node); self.inspect(node); self.save(); return self.state()
    def snapshot(self, node_id, note=''):
        node=self.node(node_id)
        if node['type']!='blend': raise ValueError('Select a Blend File node.')
        source=self.path(node)
        history=self.root/META/'history'/node_id; history.mkdir(parents=True,exist_ok=True)
        sid=uid(); target=history/(sid+'.blend')
        before=digest(source); shutil.copy2(source,target)
        if before!=digest(source) or before!=digest(target):
            target.unlink(); raise ValueError('File changed during snapshot; finish saving and retry.')
        node['snapshots'].append({'id':sid,'created':stamp(),'note':note,'hash':before,
                                'path':target.relative_to(self.root).as_posix(),'number':len(node['snapshots'])+1})
        self.save(); return self.state()
    def transaction(self,node,job,new=False):
        target=self.path(node)
        expected=digest(target) if not new else None
        with tempfile.TemporaryDirectory(dir=target.parent,prefix='.pipeline-operation-') as temp:
            # Saved beside the real target so Blender relative paths have the same base.
            output=target.parent/('.pipeline-'+uid()+'.blend')
            job.update(target=str(target),output=str(output))
            config=Path(temp)/'job.json'; config.write_text(json.dumps(job),encoding='utf-8')
            try:
                self.run('blender_ops.py',[config])
                if not output.exists(): raise ValueError('Blender did not produce a file.')
                if new and target.exists(): raise ValueError('Destination appeared during operation.')
                if not new and digest(target)!=expected: raise ValueError('Destination changed during operation; refresh and retry.')
                if job.get('source_hash') and digest(Path(job['source']))!=job['source_hash']:raise ValueError('Source changed during operation; refresh and retry.')
                os.replace(output,target)
            finally:
                if output.exists(): output.unlink()
    def link(self,source_id,target_id,collection,closed,unlink=False,mode='instance',camera='',scene=''):
        source,target=self.node(source_id),self.node(target_id)
        if source['type']!='blend' or target['type']!='blend': raise ValueError('Link between two Blend File nodes.')
        if source_id==target_id: raise ValueError('A file cannot link itself.')
        self.ensure_closed(target,closed)
        # Rescan graph to check real dependencies rather than UI-only edges.
        self.refresh()
        if any(n.get('scan',{}).get('error') for n in self.data['nodes'] if n['type']=='blend'):
            raise ValueError('Resolve failed scans before modifying links.')
        source_path,target_path=str(self.path(source)),str(self.path(target))
        if not unlink:
            detail=next((c for c in source['scan'].get('collection_details',[]) if c['name']==collection),None)
            if detail is None:raise ValueError('Collection no longer exists; refresh the source node.')
            if detail['objects']==0:
                raise ValueError('That collection is empty. Use Collect root objects on the source node if your objects are under Scene Collection, then link Scene Contents.')
            pending=[source_path]; seen=set()
            lookup={str(self.path(n)):n for n in self.data['nodes'] if n['type']=='blend'}
            while pending:
                key=pending.pop()
                if key==target_path: raise ValueError('That link would create a dependency cycle.')
                if key in seen: continue
                seen.add(key)
                if key not in lookup: raise ValueError('Import external linked files into this project before adding links.')
                pending += [str(Path(r['path']).resolve()) for r in lookup[key]['scan']['refs'] if r['kind']=='Library']
            if any(i['source']==source_path and i['collection']==collection for i in target['scan'].get('instances',[])):
                raise ValueError('This collection already has an instance in the destination.')
        self.snapshot(target_id,('Before unlink: ' if unlink else 'Before link: ')+collection)
        self.transaction(target,{'action':'unlink' if unlink else 'link','source':source_path,'collection':collection,'mode':mode,'camera':camera,'scene':scene})
        self.inspect(target); self.save(); return self.state()
    def restore(self,node_id,snapshot_id,closed):
        node=self.node(node_id); self.ensure_closed(node,closed)
        item=next(s for s in node['snapshots'] if s['id']==snapshot_id)
        backup=(self.root/item['path']).resolve()
        if not backup.is_relative_to(self.root/META/'history') or digest(backup)!=item['hash']:
            raise ValueError('Snapshot integrity check failed.')
        self.snapshot(node_id,'Before restoring snapshot '+str(item['number']))
        target=self.path(node); expected=digest(target)
        temp=target.with_name('.pipeline-restore-'+uid()+'.blend')
        try:
            shutil.copy2(backup,temp)
            if digest(target)!=expected: raise ValueError('Working file changed during restore.')
            os.replace(temp,target)
        finally:
            if temp.exists(): temp.unlink()
        self.inspect(node); self.save(); return self.state()
    def launch(self,node_id):
        self.require_desktop()
        node=self.node(node_id)
        if node['type'] not in {'blend','folder'}:raise ValueError('Choose a Blend file or folder to open.')
        if node['type']=='folder':
            self.desktop.open_folder(self.path(node),self.desktop_available())
            return self.state()
        if node_id in self.processes and self.processes[node_id].poll() is None:
            raise ValueError('This file is already open in a launched Blender session.')
        self.processes[node_id]=self.start_blender(self.path(node))
        return self.state()
    def inspect_snapshot(self,node_id,snapshot_id):
        self.require_desktop()
        node=self.node(node_id)
        item=next(s for s in node['snapshots'] if s['id']==snapshot_id)
        source=(self.root/item['path']).resolve()
        if not source.is_relative_to(self.root/META/'history') or digest(source)!=item['hash']:
            raise ValueError('Snapshot integrity check failed.')
        # Same directory as current file keeps its relative library paths valid.
        copy=self.path(node).with_name('.inspection-'+uid()+'.blend')
        shutil.copy2(source,copy)
        try: self.start_blender(copy)
        except Exception:
            copy.unlink(missing_ok=True)
            raise
        return self.state()
    def layout(self,nodes,view):
        if not isinstance(view,dict) or any(type(view.get(k)) not in {int,float} or not math.isfinite(view[k]) for k in ('x','y','zoom')) or view['zoom']<=0:
            raise ValueError('Invalid graph view.')
        positions=[]
        for position in nodes:
            node=self.node(position['id'])
            x,y=float(position['x']),float(position['y'])
            if not math.isfinite(x) or not math.isfinite(y):raise ValueError('Invalid node position.')
            positions.append((node,x,y))
        changed=any(node.get('x')!=x or node.get('y')!=y for node,x,y in positions)
        for node,x,y in positions:node.update(x=x,y=y)
        self.local_view=copy.deepcopy(view)
        if changed:self.save()
        return self.state()
