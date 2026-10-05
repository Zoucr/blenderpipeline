"""Run material-assistant operations in Blender using the generated installable package."""
import subprocess,tempfile,zipfile
from pathlib import Path
from blender_pipeline.adapters.addon_package import build_addon
from blender_pipeline.project.workspace import Pipeline
from support import FIXTURES
with tempfile.TemporaryDirectory(prefix='material-assistant-') as directory:
    root=Path(directory);client=root/'client'
    archive=build_addon(root/'Companion.zip')
    with zipfile.ZipFile(archive) as package:package.extractall(client)
    result=subprocess.run([Pipeline().blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(FIXTURES/'material_assistant_fixture.py'),'--',str(client),str(root)],capture_output=True,text=True,errors='replace',timeout=90)
    assert result.returncode==0,result.stdout[-4000:]+'\n'+result.stderr[-2500:]
    print(next(line for line in result.stdout.splitlines() if line.startswith('PASS:')))
