"""Run against the actual server: python tests/smoke.py"""
import json, os, urllib.request, urllib.error, tempfile
from pathlib import Path
import cadquery as cq
BASE=os.environ.get('FORMLAB_URL','http://127.0.0.1:8000')
def post(path,body):
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req) as r:return json.load(r)
design=dict(mode='mechanical',kind='enclosure',width=80,depth=55,height=25,wall=2,holes=True,components=4)
checks=0
for kind in ['enclosure','plate','bracket']:
    data=post('/api/generate',dict(design,kind=kind))
    assert data['volume']>0
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'shape.step'; p.write_bytes(urllib.request.urlopen(BASE+data['files']['model.step']).read())
        shape=cq.importers.importStep(str(p))
        assert shape.val().isValid() and shape.val().Volume()>0
        assert abs(shape.val().BoundingBox().xlen-80)<.01
        assert urllib.request.urlopen(BASE+data['files']['model.stl']).read(80)
    checks+=1
pcb=post('/api/generate',dict(design,mode='pcb'))
board=urllib.request.urlopen(BASE+pcb['files']['board.kicad_pcb']).read().decode()
assert board.count('(footprint ')==4 and board.count('(segment ')==3
assert '(net 5 "N5")' in board and '(layer "Edge.Cuts")' in board
checks+=1
chat=post('/api/chat',{'message':'生成 100×70×30 的外壳，壁厚 2，添加安装孔','design':design})
assert chat['design']['width']==100 and chat['design']['depth']==70 and chat['design']['height']==30
checks+=1
for body in [dict(design,width=-1),dict(design,wall=8,height=4),dict(design,mode='pcb',width=30,components=12)]:
    try:post('/api/generate',body);raise AssertionError('invalid dimensions accepted')
    except urllib.error.HTTPError as e:assert e.code==422
    checks+=1
assert b'FormLab' in urllib.request.urlopen(BASE+'/').read()
checks+=1
print(f'{checks} functional checks passed; STEP solids reimported with OpenCascade. KiCad DRC not run.')
