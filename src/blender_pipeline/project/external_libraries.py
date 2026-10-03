"""Visible external libraries and deliberate localization of library dependencies."""
import copy,json,os,shutil
from pathlib import Path
from blender_pipeline.project.model import META,uid,digest,stamp,name

class ExternalLibraries:
    def path(self,node):
        return super().path(node)
    def ensure_closed(self,node,acknowledged):
        if node.get('external'):raise ValueError('External library nodes are read-only in this tool. Copy the library into the project first.')
        return super().ensure_closed(node,acknowledged)
    def transaction(self,node,*args,**kwargs):
        if node.get('external'):raise ValueError('External libraries cannot be modified by background operations.')
        return super().transaction(node,*args,**kwargs)
    def discover_external(self):
        known=set()
        for n in self.data['nodes']:
            if n['type']=='blend':
                try:known.add(os.path.normcase(str(self.path(n))))
                except ValueError:pass
        pending=list(self.data['nodes']);added=0
        while pending:
            node=pending.pop(0)
            for ref in node.get('scan',{}).get('refs',[]):
                path=Path(ref['path']).resolve();key=os.path.normcase(str(path))
                if ref['kind']!='Library' or path.is_relative_to(self.root) or key in known:continue
                if added>=100:raise ValueError('More than 100 external libraries found. Register additional sources deliberately.')
                known.add(key);added+=1
                library={'id':uid(),'type':'blend','external':True,'name':path.stem,'path':str(path),'x':-320,'y':70+added*290,'snapshots':[],'color':'purple'}
                self.data['nodes'].append(library);self.inspect(library);pending.append(library)
    def refresh(self,node_id=None):
        for node in list(self.data['nodes']):
            if node['type']=='blend' and (node_id is None or node['id']==node_id):self.inspect(node)
        self.discover_external();self.save();return self.state()
    def external_register(self,source):
        path=Path(source).resolve()
        if path.is_relative_to(self.root):return self.import_blend(str(path))
        if not path.is_file() or path.suffix.lower()!='.blend':raise ValueError('Choose an existing .blend library.')
        if any(n['type']=='blend' and self.path(n)==path for n in self.data['nodes']):raise ValueError('Library is already registered.')
        node={'id':uid(),'type':'blend','external':True,'name':path.stem,'path':str(path),'x':-320,'y':70,'snapshots':[],'color':'purple'}
        self.data['nodes'].append(node);return self.refresh(node['id'])
    def localize_external(self,node_id,closed,title='Imported Libraries'):
        source=self.node(node_id)
        if not source.get('external'):raise ValueError('Select an external library.')
        if self.render_busy():raise ValueError('Finish or cancel renders before collecting libraries.')
        self.refresh();closure={};pending=[source]
        while pending:
            node=pending.pop();path=self.path(node);key=str(path)
            if key in closure:continue
            if node.get('scan',{}).get('error'):raise ValueError('Resolve missing library: '+key)
            if not node.get('external'):continue
            closure[key]=node
            for ref in node['scan'].get('refs',[]):
                if ref['kind']!='Library':raise ValueError('Pack external textures, caches and other resources in '+node['name']+' before collecting. This operation collects Blender libraries only.')
                linked=next((n for n in self.data['nodes'] if n['type']=='blend' and self.path(n)==Path(ref['path']).resolve()),None)
                if not linked:raise ValueError('Register this library dependency first: '+ref['path'])
                pending.append(linked)
        destination=self.root/name(title)
        if destination.exists():raise ValueError('Choose a new destination folder name.')
        aliases={old:str(destination/(str(i+1).zfill(3)+'_'+Path(old).name)) for i,old in enumerate(closure)}
        affected=[n for n in self.data['nodes'] if n['type']=='blend' and not n.get('external') and any(r['kind']=='Library' and str(Path(r['path']).resolve()) in aliases for r in n.get('scan',{}).get('refs',[]))]
        for node in affected:self.ensure_closed(node,closed)
        originals={str(self.path(n)):digest(self.path(n)) for n in affected};source_hashes={old:digest(old) for old in aliases}
        for n in affected:self.snapshot(n['id'],'Before collecting external libraries')
        recovery={n['id']:self.root/n['snapshots'][-1]['path'] for n in affected};committed={};destination.mkdir()
        previous=copy.deepcopy(self.data)
        try:
            for old,new in aliases.items():
                staged=dict(closure[old],external=False,path=Path(new).relative_to(self.root).as_posix())
                self.transaction(staged,{'action':'create','template':old},new=True)
            for old,new in aliases.items():
                node=dict(closure[old],external=False,path=Path(new).relative_to(self.root).as_posix())
                self.transaction(node,{'action':'repair_paths','aliases':aliases,'reload':True})
            if any(digest(old)!=h for old,h in source_hashes.items()):raise ValueError('An external source changed during collection. Save and retry.')
            for n in affected:
                if digest(self.path(n))!=originals[str(self.path(n))]:raise ValueError('A destination changed during collection. Save and retry.')
                self.transaction(n,{'action':'repair_paths','aliases':aliases,'reload':True});committed[n['id']]=digest(self.path(n))
            for old,new in aliases.items():closure[old].update(external=False,path=Path(new).relative_to(self.root).as_posix())
            self.data.setdefault('path_aliases',{}).update(aliases)
            self.refresh();self.save()
        except Exception:
            self.data=previous
            for n in affected:
                if n['id'] in committed and digest(self.path(n))==committed[n['id']]:shutil.copy2(recovery[n['id']],self.path(n))
            # Keep copied files for recovery rather than deleting potentially edited data.
            self.save();raise
        return self.state()
