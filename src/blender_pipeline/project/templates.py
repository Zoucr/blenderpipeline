"""Portable project startup files; capture saved bytes without changing the source."""
import json, shutil, tempfile
from pathlib import Path
from blender_pipeline.project.model import META, uid, stamp, digest, name, atomic_json

class Templates:
    def save_app_startup(self,source,title='Startup'):
        source=Path(source).resolve();title=name(title)
        if not source.is_file() or source.suffix.lower()!='.blend':raise ValueError('Choose a saved .blend file.')
        if self.companion and any(s['dirty'] for s in self.companion.opened(source)):raise ValueError('Save Blender before capturing the startup file.')
        before=digest(source)
        with tempfile.TemporaryDirectory() as temp:
            scan_path=Path(temp)/'scan.json';self.run('scan_blend.py',[scan_path],source)
            if json.loads(scan_path.read_text(encoding='utf-8')).get('refs'):raise ValueError('Startup files must be self-contained. Pack external resources first.')
        folder=self.global_template_config.parent/'startup-templates';folder.mkdir(exist_ok=True)
        target=folder/(uid()+'.blend')
        try:
            shutil.copy2(source,target)
            if digest(source)!=before or digest(target)!=before:raise ValueError('Source changed during capture; save and retry.')
            atomic_json(self.global_template_config,{'name':title,'path':target.relative_to(self.global_template_config.parent).as_posix(),'hash':before,'created':stamp()})
        except Exception:target.unlink(missing_ok=True);raise
        return self.state()
    def capture_app_startup(self):
        try:entry=json.loads(self.global_template_config.read_text(encoding='utf-8'))
        except FileNotFoundError:return ''
        path=(self.global_template_config.parent/entry['path']).resolve()
        if not path.is_relative_to((self.global_template_config.parent/'startup-templates').resolve()) or not path.is_file() or digest(path)!=entry['hash']:raise ValueError('App startup file is missing or changed. Capture it again in Startup templates.')
        existing=next((t for t in self.data.get('templates',[]) if t.get('app_hash')==entry['hash']),None)
        if existing:self.template_entry(existing['id']);return existing['id']
        title=entry['name'];count=1
        while any(t['name'].casefold()==title.casefold() for t in self.data.get('templates',[])):
            title=entry['name']+' '+str(count);count+=1
        self.save_template(title,str(path));new=self.data['templates'][-1];new['app_hash']=entry['hash'];self.save();return new['id']
    def template_entry(self,template_id):
        entry=next((t for t in self.data.get('templates',[]) if t['id']==template_id),None)
        if not entry:raise ValueError('Template not found. Choose another template or Factory empty.')
        path=(self.root/entry['path']).resolve()
        if not path.is_relative_to(self.root/META/'templates') or not path.is_file() or digest(path)!=entry['hash']:
            raise ValueError('Template is missing or changed. Import it again before creating files.')
        return entry,path
    def save_template(self,title,source=None,node_id=None,make_default=False):
        title=name(title)
        if any(t['name'].casefold()==title.casefold() for t in self.data.get('templates',[])):raise ValueError('A template with this name already exists. Choose a new name.')
        if node_id:
            node=self.node(node_id)
            if node['type']!='blend':raise ValueError('Choose a Blend File.')
            if self.companion and any(s['dirty'] for s in self.companion.opened(self.path(node))):raise ValueError('Save your Blender edits before capturing a template.')
            source=self.path(node)
        source=Path(source or '').resolve()
        if not source.is_file() or source.suffix.lower()!='.blend':raise ValueError('Choose a saved .blend file.')
        if self.companion and any(s['dirty'] for s in self.companion.opened(source)):raise ValueError('Save your Blender edits before capturing a template.')
        before=digest(source)
        with tempfile.TemporaryDirectory() as temp:
            scan_path=Path(temp)/'scan.json';self.run('scan_blend.py',[scan_path],source)
            scan=json.loads(scan_path.read_text(encoding='utf-8'))
        if scan.get('refs'):raise ValueError('Templates must be self-contained. Pack external resources and remove linked libraries in Blender, then save and retry.')
        folder=self.root/META/'templates';folder.mkdir(exist_ok=True)
        identifier=uid();target=folder/(identifier+'.blend')
        old_default=self.data.get('default_template','')
        try:
            shutil.copy2(source,target)
            if digest(source)!=before or digest(target)!=before:raise ValueError('The file changed while capturing. Save and retry.')
            entry={'id':identifier,'name':title,'path':target.relative_to(self.root).as_posix(),'hash':before,'created':stamp()}
            self.data.setdefault('templates',[]).append(entry)
            if make_default:self.data['default_template']=identifier
            self.save()
        except Exception:
            self.data['templates']=[t for t in self.data.get('templates',[]) if t['id']!=identifier]
            if self.data.get('default_template')==identifier:self.data['default_template']=old_default
            target.unlink(missing_ok=True);raise
        return self.state()
    def template_default(self,template_id=''):
        if template_id and template_id!='__factory__':self.template_entry(template_id)
        self.data['default_template']=template_id;self.save();return self.state()
