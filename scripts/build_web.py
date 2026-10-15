"""Build a self-contained Pages artifact: pinned Pyodide plus hashed local wheels."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent.parent
DIST=ROOT/'dist'
CACHE=ROOT/'.web-cache'
RUNTIME=ROOT/'node_modules/pyodide'
VERSION=json.loads((RUNTIME/'package.json').read_text())['version']
LOCK=json.loads((RUNTIME/'pyodide-lock.json').read_text())
DIST.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
shutil.copytree(ROOT/'web',DIST,dirs_exist_ok=True)
(DIST/'runtime').mkdir(exist_ok=True)
for name in ['pyodide.mjs','pyodide.js','pyodide.asm.mjs','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json']:
    shutil.copy2(RUNTIME/name,DIST/'runtime'/name)
for name in ['numpy','scipy']:
    package=LOCK['packages'][name]
    path=CACHE/package['file_name']
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=package['sha256']:
        url=f'https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/{path.name}'
        for attempt in range(3):
            try:
                print(f'Downloading {name} (attempt {attempt+1})',flush=True)
                with urllib.request.urlopen(url,timeout=60) as response: content=response.read()
                if hashlib.sha256(content).hexdigest()!=package['sha256']: raise ValueError('wheel checksum mismatch')
                path.write_bytes(content); break
            except Exception:
                if attempt==2: raise
                time.sleep(1)
    print(f'{name}: {path.stat().st_size/1e6:.1f} MB, SHA256 verified',flush=True)
    if path.stat().st_size>25*1024*1024: raise ValueError('Package exceeds Pages per-asset limit')
    shutil.copy2(path,DIST/'runtime'/path.name)
modules=['__init__','model','adapters','engine','evaluation','insights','scenario','webbridge']
(DIST/'python/freshroute').mkdir(parents=True,exist_ok=True)
for module in modules: shutil.copy2(ROOT/'freshroute'/f'{module}.py',DIST/'python/freshroute'/f'{module}.py')
(DIST/'python/manifest.json').write_text(json.dumps([f'freshroute/{name}.py' for name in modules]))
demo={'config':json.loads((ROOT/'examples/demo/config.json').read_text())}
for table in ['inventory','demand','routes','resources']:
    with (ROOT/'examples/demo'/f'{table}.csv').open() as stream: demo[table]=list(csv.DictReader(stream))
(DIST/'demo.json').write_text(json.dumps(demo,indent=2))
# Spreadsheet parsing is optional and entirely local. Bundle installed pure-Python modules.
with zipfile.ZipFile(DIST/'xlsx-support.zip','w',zipfile.ZIP_DEFLATED) as bundle:
    for name in ['openpyxl','et_xmlfile']:
        source=Path(importlib.util.find_spec(name).origin).parent
        for path in source.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                bundle.write(path,Path(name)/path.relative_to(source))
print(f'Pages artifact ready at {DIST}',flush=True)
