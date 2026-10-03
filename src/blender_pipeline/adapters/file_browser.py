"""Read-only local directory browser for choosing paths in the interface."""
import os
import string
from pathlib import Path


def choose_system_path(mode='file',initial='',extension='.blend'):
    if mode not in {'file','folder','save'} or extension not in {'','.blend','.exe','.zip'}:raise ValueError('Unknown file picker mode.')
    import tkinter as tk
    from tkinter import filedialog
    path=Path(initial).expanduser() if initial else Path.home()
    directory=path if path.is_dir() else path.parent
    if not directory.is_dir():directory=Path.home()
    root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
    try:
        options={'parent':root,'initialdir':str(directory)}
        if mode=='folder':result=filedialog.askdirectory(title='Choose folder',mustexist=True,**options)
        else:
            label={'.blend':'Blender files','.exe':'Applications','.zip':'ZIP archives','':'All files'}[extension]
            options['filetypes']=[(label,'*'+extension if extension else '*')]
            if mode=='save':
                result=filedialog.asksaveasfilename(title='Choose backup location',initialfile=path.name if initial else 'project-backup.zip',defaultextension=extension,**options)
            else:result=filedialog.askopenfilename(title='Choose file',**options)
        return {'path':str(result) if result else ''}
    finally:root.destroy()


def browse_directory(path='', extension='', query=''):
    if extension not in {'', '.blend', '.exe', '.zip'}:raise ValueError('Unsupported file filter')
    directory=Path(path).expanduser() if path else Path.home()
    if not directory.is_absolute():raise ValueError('Choose an absolute folder path')
    if directory.is_file():directory=directory.parent
    directory=directory.resolve()
    if not directory.is_dir():raise ValueError('Folder not found: '+str(directory))
    entries=[];count=0;query=str(query).casefold()
    try:
        with os.scandir(directory) as scan:
            for item in scan:
                try:
                    folder=item.is_dir()
                    if not folder and extension and not item.name.lower().endswith(extension):continue
                    if query and query not in item.name.casefold():continue
                    count+=1
                    entries.append({'name':item.name,'path':str(directory/item.name),'folder':folder})
                except OSError:continue
    except PermissionError:raise ValueError('Windows does not allow access to this folder. Choose another location.') from None
    entries.sort(key=lambda e:(not e['folder'],e['name'].casefold()))
    homes=[{'name':'Home','path':str(Path.home())}]
    for name in ('Desktop','Documents','Downloads'):
        target=Path.home()/name
        if target.is_dir():homes.append({'name':name,'path':str(target)})
    if os.name=='nt':homes.extend({'name':letter+':','path':letter+':\\'} for letter in string.ascii_uppercase if Path(letter+':\\').is_dir())
    else:homes.append({'name':'Filesystem','path':'/'})
    return {'path':str(directory),'parent':str(directory.parent),'entries':entries[:250], 'total':count,'places':homes}
