"""Functional imports against a running server; FORMLAB_URL selects its address."""
import json, os, struct, urllib.request, urllib.error
from pathlib import Path
import tempfile
import cadquery as cq
BASE=os.environ.get('FORMLAB_URL','http://127.0.0.1:8000')
def upload(name,data):
    req=urllib.request.Request(BASE+'/api/import?filename='+name,data=data,headers={'Content-Type':'application/octet-stream'})
    with urllib.request.urlopen(req) as r:return json.load(r)
checks=0
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'test.step'
    obj=cq.Workplane('XY').box(40,30,10).translate((100,-50,20))
    cq.exporters.export(obj,str(p))
    for ext in ['step','stp']:
        result=upload('part.'+ext,p.read_bytes())
        assert result['dimensions']==[40,30,10]
        mesh=urllib.request.urlopen(BASE+result['preview']).read()
        triangles=struct.unpack_from('<I',mesh,80)[0]
        assert triangles>0 and len(mesh)==84+50*triangles
        downloaded=urllib.request.urlopen(BASE+result['files']['原始 STEP']).read()
        assert downloaded==p.read_bytes()
        checks+=1
board='''(kicad_pcb (version 20240108) (general (thickness 1.6))
(gr_rect (start 0 0) (end 60 40) (layer "Edge.Cuts") (stroke (width 0.05) (type default)))
(footprint "Demo" (at 20 20 90)
(pad "1" thru_hole circle (at 2 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask")))
(segment (start 10 10) (end 20 18) (width 0.3) (layer "F.Cu") (net 1))
(gr_arc (start 0 10) (mid 5 5) (end 10 10) (layer "Edge.Cuts") (stroke (width 0.1)))
(gr_text "<script>alert(1)</script>" (at 0 0) (layer "F.SilkS")))'''
result=upload('test.kicad_pcb',board.encode())
assert result['counts']=={'footprints':1,'pads':1,'tracks':1}
svg=urllib.request.urlopen(BASE+result['preview']).read().decode()
assert '<script>' not in svg and 'rotate(-90.0 20.0 18.0)' in svg
assert urllib.request.urlopen(BASE+result['files']['原始 KiCad PCB']).read()==board.encode()
checks+=1
for name,body,status in [('bad.step',b'not step',422),('bad.kicad_pcb',b'(invalid)',422),('bad.kicad_pcb',b'(',422),('empty.stp',b'',422),('bad.exe',b'x',415),('large.step',b'x'*(20*1024*1024+1),413)]:
    try:upload(name,body);raise AssertionError('invalid upload accepted')
    except urllib.error.HTTPError as error:assert error.code==status,(name,error.code)
    checks+=1
print(f'{checks} import checks passed: STEP/STP geometry, KiCad rotation/arcs, original preservation, malformed/empty/oversized uploads, unsupported formats.')
