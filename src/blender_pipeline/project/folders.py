"""Nested graph frames, recoverable folder removal and bounded disk inventories."""
import copy,os,time,re
from datetime import datetime
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from blender_pipeline.project.model import META,uid,stamp

def dated_prefix(scene):
    try:today=datetime.now(ZoneInfo('Europe/Berlin'))
    except ZoneInfoNotFoundError:today=datetime.now().astimezone()
    safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',str(scene)).strip(' .') or 'Scene'
    return today.strftime('%y%m%d')+'_'+safe+'_'

class FolderWorkflow:
    def fit_frames(self):
        lookup={n['id']:n for n in self.data['nodes']}
        def depth(n):
            count=0
            while n.get('group'):count+=1;n=lookup[n['group']]
            return count
        for frame in sorted((n for n in lookup.values() if n['type']=='folder'),key=depth,reverse=True):
            children=[n for n in lookup.values() if n.get('group')==frame['id'] and not n.get('hidden')]
            if not children:continue
            right=max(n['x']+n.get('width',260)+28 for n in children)
            bottom=max(n['y']+n.get('height',260)+28 for n in children)
            frame['width']=max(frame.get('width',650),right-frame['x'])
            frame['height']=max(frame.get('height',420),bottom-frame['y'])
    def validate_groups(self,nodes):
        lookup={n['id']:n for n in nodes}
        for node in nodes:
            seen={node['id']};parent=node.get('group')
            while parent:
                if parent in seen:raise ValueError('A folder cannot contain itself or an ancestor.')
                seen.add(parent);frame=lookup.get(parent)
                if not frame or frame['type']!='folder':raise ValueError('Choose an existing folder frame.')
                parent=frame.get('group')
    def group_nodes(self,groups):
        if not isinstance(groups,dict) or len(groups)>1000:raise ValueError('Invalid grouping request.')
        updated=copy.deepcopy(self.data['nodes']);lookup={n['id']:n for n in updated}
        for key,parent in groups.items():
            if key not in lookup:raise ValueError('Node no longer exists.')
            lookup[key]['group']=parent or None
        self.validate_groups(updated)
        old=self.data['nodes'];self.data['nodes']=updated
        try:self.fit_frames();self.save()
        except Exception:self.data['nodes']=old;raise
        return self.state()
    def folder_inventory(self,node):
        path=self.path(node);now=time.monotonic()
        cache=getattr(self,'_folder_cache',{});self._folder_cache=cache
        key=(str(self.root),node['id'])
        if key in cache and now-cache[key][0]<2:return cache[key][1]
        info={'files':0,'images':0,'directories':0,'entries':[],'truncated':False,'missing':not path.is_dir(),'error':''}
        visited=0
        try:
            def failed(error):info['error']=str(error)
            for parent,dirs,files in os.walk(path,followlinks=False,onerror=failed):
                if visited+len(dirs)>2000:info['truncated']=True;break
                dirs[:]=[d for d in sorted(dirs) if d!=META and not (self.root.__class__(parent)/d).is_symlink() and not (self.root.__class__(parent)/d).is_junction()]
                visited+=len(dirs)
                info['directories']+=len(dirs)
                for filename in sorted(files):
                    visited+=1
                    if visited>2000:info['truncated']=True;break
                    file=self.root.__class__(parent)/filename
                    if file.is_symlink():continue
                    info['files']+=1
                    is_image=file.suffix.lower() in {'.png','.jpg','.jpeg','.exr','.tif','.tiff','.webp','.bmp'}
                    if is_image:info['images']+=1
                    if len(info['entries'])<80:info['entries'].append({'name':file.relative_to(path).as_posix(),'image':is_image})
                if info['truncated']:break
        except OSError as exc:info['error']=str(exc)
        cache[key]=(now,info);return info
    def archive_folder(self,node_id,confirmed=False):
        if not confirmed:raise ValueError('Confirm folder deletion first.')
        node=self.node(node_id)
        if node['type']!='folder':raise ValueError('Choose a folder frame.')
        if self.render_busy():raise ValueError('Finish or cancel renders before deleting output folders.')
        source=self.path(node)
        original=self.root/node['path']
        if original.is_symlink() or original.is_junction():raise ValueError('Remove symbolic links or junctions outside the folder archive workflow.')
        if not source.is_dir() or source.is_symlink():raise ValueError('Folder is missing or is a symbolic link.')
        aid=uid();destination=self.root/META/'archive-folders'/aid
        record={'id':aid,'node':copy.deepcopy(node),'archived_at':stamp(),'moved':False,'children':[], 'configs':{}}
        before=copy.deepcopy(self.data)
        # Never move populated folders: this could break unregistered Blender dependencies.
        if not any(source.iterdir()):
            destination.parent.mkdir(parents=True,exist_ok=True);os.replace(source,destination)
            if any(destination.iterdir()):
                os.replace(destination,source);raise ValueError('Folder contents changed; refresh before deleting.')
            record.update(moved=True,path=destination.relative_to(self.root).as_posix())
        try:
            for child in self.data['nodes']:
                if child.get('group')==node_id:record['children'].append(child['id']);child['group']=node.get('group')
                if child.get('render_config',{}).get('folder_id')==node_id:record['configs'][child['id']]=child.pop('render_config')
            self.data['nodes']=[n for n in self.data['nodes'] if n['id']!=node_id]
            self.data.setdefault('archived_folders',[]).append(record);self.save()
        except Exception:
            self.data=before
            if record['moved']:os.replace(destination,source)
            raise
        self._folder_cache={};return self.state()
    def restore_folder(self,archive_id):
        if self.render_busy():raise ValueError('Finish or cancel renders before restoring folders.')
        record=next((r for r in self.data.get('archived_folders',[]) if r['id']==archive_id),None)
        if not record:raise ValueError('Archived folder not found.')
        node=copy.deepcopy(record['node']);target=self.path(node)
        if any(n['id']==node['id'] or (n['type']=='folder' and self.path(n)==target) for n in self.data['nodes']):raise ValueError('This folder frame or path is already registered.')
        moved=False
        if record['moved']:
            source=(self.root/record['path']).resolve()
            if not source.is_relative_to((self.root/META/'archive-folders').resolve()) or not source.is_dir():raise ValueError('Archive folder is missing.')
            if target.exists():raise ValueError('Original folder path is occupied.')
            target.parent.mkdir(parents=True,exist_ok=True);os.replace(source,target);moved=True
        elif not target.is_dir():raise ValueError('Original folder no longer exists.')
        before=copy.deepcopy(self.data)
        try:
            if not any(n['id']==node.get('group') and n['type']=='folder' for n in self.data['nodes']):node['group']=None
            node['hidden']=False;self.data['nodes'].append(node)
            for child in self.data['nodes']:
                if child['id'] in record['children'] and child.get('group')==node.get('group'):child['group']=node['id']
                if child['id'] in record['configs'] and not child.get('render_config'):child['render_config']=record['configs'][child['id']]
            self.validate_groups(self.data['nodes']);self.fit_frames();self.data['archived_folders'].remove(record);self.save()
        except Exception:
            self.data=before
            if moved:os.replace(target,source)
            raise
        self._folder_cache={};return self.state()
