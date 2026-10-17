from pathlib import Path
import json, os, re, uuid, shutil
import urllib.request, urllib.error
import cadquery as cq
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from imports import board_preview
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
OUT = ROOT / 'artifacts'
OUT.mkdir(exist_ok=True)
app = FastAPI(title='FormLab')

class Design(BaseModel):
    mode: str = 'mechanical'
    kind: str = 'enclosure'
    width: float = Field(80, ge=15, le=300)
    depth: float = Field(55, ge=15, le=300)
    height: float = Field(25, ge=4, le=150)
    wall: float = Field(2, ge=1, le=8)
    holes: bool = True
    components: int = Field(4, ge=2, le=12)

class Chat(BaseModel):
    message: str = Field(max_length=2000)
    design: Design

@app.get('/api/health')
def health(): return {'ok': True, 'kernel':'OpenCascade / CadQuery', 'assistant': 'ai' if os.getenv('DESIGN_AI_KEY') and os.getenv('DESIGN_AI_URL') and os.getenv('DESIGN_AI_MODEL') else 'local'}

@app.post('/api/chat')
def chat(req: Chat):
    d = req.design.model_dump()
    s = req.message.lower()
    if os.getenv('DESIGN_AI_KEY') and os.getenv('DESIGN_AI_URL') and os.getenv('DESIGN_AI_MODEL'):
        endpoint = os.environ['DESIGN_AI_URL'].rstrip('/') + '/chat/completions'
        if not endpoint.startswith('https://'): raise HTTPException(503, 'AI 接口必须使用 HTTPS。')
        prompt = ('You are a CAD parameter assistant. Return only JSON with design and reply. '
                  'design must have mode mechanical or pcb, kind enclosure or plate or bracket, width/depth 15..300, '
                  'height 4..150, wall 1..8, holes boolean, components integer 2..12. Units mm. '
                  'Only these templates are supported. Never claim arbitrary CAD, schematic synthesis, fabrication readiness, '
                  'or electrical verification. For unsupported requests preserve design and explain limitations in Chinese. '
                  'Current design: ' + json.dumps(d))
        payload = {'model':os.environ['DESIGN_AI_MODEL'], 'messages':[{'role':'system','content':prompt},{'role':'user','content':req.message}], 'response_format':{'type':'json_object'},'temperature':0.2}
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['DESIGN_AI_KEY']})
        try:
            with urllib.request.urlopen(request, timeout=45) as response: ai=json.load(response)
            answer=json.loads(ai['choices'][0]['message']['content'])
            validated=Design(**answer['design'])
            if validated.mode not in ['mechanical','pcb'] or validated.kind not in ['enclosure','plate','bracket']: raise ValueError('invalid template')
            return {'design':validated.model_dump(),'reply':str(answer['reply'])[:2000]}
        except (urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError):
            raise HTTPException(502,'大模型接口调用失败，请检查服务地址、模型名称和凭证；可清除 AI 配置使用本地指令。')
    recognized = False
    for words, kind in [(['外壳','盒子','enclosure'],'enclosure'),(['板件','平板','plate'],'plate'),(['支架','bracket'],'bracket')]:
        if any(w in s for w in words): d.update(mode='mechanical',kind=kind); recognized=True
    if any(w in s for w in ['pcb','电路板']): d['mode']='pcb'; recognized=True
    dims = re.search(r'(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)(?:\s*[x×*]\s*(\d+(?:\.\d+)?))?', s)
    if dims:
        d['width'],d['depth']=float(dims[1]),float(dims[2])
        if dims[3]: d['height']=float(dims[3])
        recognized=True
    for label, key in [('宽','width'),('深','depth'),('长','depth'),('高','height'),('壁厚','wall'),('元件','components')]:
        match=re.search(label+r'\s*[:：=]?\s*(\d+(?:\.\d+)?)',s)
        if match: d[key]=float(match[1]); recognized=True
    if '不要孔' in s or '无孔' in s: d['holes']=False; recognized=True
    elif '安装孔' in s or '加孔' in s: d['holes']=True; recognized=True
    if not recognized:
        return {'design':d,'reply':'当前使用本地参数指令解析器，尚未接入大模型。请尝试“生成 100×70×30 的外壳，壁厚 2，添加安装孔”，或“电路板 80×55，元件 6”。不支持的自由描述不会自动修改设计。'}
    try: validated=Design(**d)
    except ValueError as e: raise HTTPException(422,'尺寸超出范围：宽/深 15–300，高 4–150，壁厚 1–8，元件 2–12。') from e
    return {'design':validated.model_dump(),'reply':'已更新设计参数。点击“生成设计”可重新构建并导出。单位为 mm。PCB 为串联演示布局，尚未进行电气规则与制造检查。' if d['mode']=='pcb' else '已更新结构参数。点击“生成设计”将使用 CAD 内核重新构建实体。单位为 mm。'}

def model(d):
    w,l,h,t=d.width,d.depth,d.height,d.wall
    if 2*t>=min(w,l) or t>=h: raise HTTPException(422,'壁厚必须小于高度，且小于宽、深的一半。')
    if d.kind=='enclosure':
        obj=cq.Workplane('XY').box(w,l,h,centered=(True,True,False))
        obj=obj.cut(cq.Workplane('XY').workplane(offset=t).box(w-2*t,l-2*t,h,centered=(True,True,False)))
    elif d.kind=='plate': obj=cq.Workplane('XY').box(w,l,t,centered=(True,True,False))
    elif d.kind=='bracket':
        obj=cq.Workplane('XY').box(w,l,t,centered=(True,True,False)).union(cq.Workplane('XY').center(0,-l/2+t/2).box(w,t,h,centered=(True,True,False)))
    else: raise HTTPException(422,'不支持的结构类型')
    if d.holes:
        for x in [-w/2+6,w/2-6]:
            for y in [-l/2+6,l/2-6]: obj=obj.cut(cq.Workplane('XY').center(x,y).circle(1.6).extrude(h+1))
    return obj

def pcb(d,folder):
    w,h=d.width,d.depth
    # Demonstration two-pin footprints, connected as a single series chain.
    pts=[(10+i*(w-20)/max(1,d.components-1),h/2) for i in range(d.components)]
    lines=['(kicad_pcb (version 20240108) (generator "formlab") (general (thickness 1.6)) (paper "A4")',
           '(layers (0 "F.Cu" signal) (31 "B.Cu" signal) (37 "F.SilkS" user "f.silkscreen") (44 "Edge.Cuts" user) (49 "F.Fab" user))',
           '(setup (pad_to_mask_clearance 0))','(net 0 "")']
    for i in range(d.components+1): lines.append(f'(net {i+1} "N{i+1}")')
    for i,(x,y) in enumerate(pts):
        lines.append(f'''(footprint "FormLab:Demo_2Pin" (layer "F.Cu") (at {x} {y})
          (fp_text reference "R{i+1}" (at 0 -3) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
          (fp_text value "DEMO" (at 0 3) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
          (pad "1" thru_hole circle (at -2.54 0) (size 1.8 1.8) (drill 0.8) (layers "*.Cu" "*.Mask") (net {i+1} "N{i+1}"))
          (pad "2" thru_hole circle (at 2.54 0) (size 1.8 1.8) (drill 0.8) (layers "*.Cu" "*.Mask") (net {i+2} "N{i+2}")))''')
    for i in range(len(pts)-1): lines.append(f'(segment (start {pts[i][0]+2.54} {h/2}) (end {pts[i+1][0]-2.54} {h/2}) (width 0.3) (layer "F.Cu") (net {i+2}))')
    for a,b in [((0,0),(w,0)),((w,0),(w,h)),((w,h),(0,h)),((0,h),(0,0))]: lines.append(f'(gr_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))')
    lines.append(')')
    (folder/'board.kicad_pcb').write_text('\n'.join(lines))
    return pts

@app.post('/api/generate')
def generate(d: Design):
    if d.mode not in ['pcb','mechanical']: raise HTTPException(422,'不支持的模式')
    if d.mode=='pcb' and (d.width<30 or (d.width-20)/(d.components-1)<8): raise HTTPException(422,'元件间距不足，请增大板宽或减少元件（间距至少 8 mm）。')
    ident=uuid.uuid4().hex
    folder=OUT/ident; folder.mkdir()
    try:
        pts=None
        if d.mode=='pcb':
            obj=cq.Workplane('XY').box(d.width,d.depth,1.6,centered=(True,True,False))
            pts=pcb(d,folder)
        else: obj=model(d)
        cq.exporters.export(obj,str(folder/'model.step'))
        cq.exporters.export(obj,str(folder/'model.stl'),tolerance=0.08,angularTolerance=0.15)
        files=['model.step','model.stl']+(['board.kicad_pcb'] if d.mode=='pcb' else [])
        return {'id':ident,'files':{f:f'/api/files/{ident}/{f}' for f in files},'volume':round(obj.val().Volume(),2),'components':pts,'design':d.model_dump()}
    except HTTPException: raise
    except Exception as e: raise HTTPException(422,'几何构建失败，请调整尺寸。') from e

def process_import(folder, ext):
    if ext in ('.step', '.stp'):
        shape = cq.importers.importStep(str(folder/'source.step'))
        if not shape.val().isValid(): raise ValueError('invalid STEP')
        box = shape.val().BoundingBox()
        cq.exporters.export(shape, str(folder/'model.stl'), tolerance=0.1, angularTolerance=0.2)
        return {'mode':'mechanical','preview':f'/api/files/{folder.name}/model.stl',
                'files':{'原始 STEP':f'/api/files/{folder.name}/source.step','STL':f'/api/files/{folder.name}/model.stl'},
                'dimensions':[round(box.xlen,3),round(box.ylen,3),round(box.zlen,3)],
                'warnings':['保留导入几何；暂不支持恢复原建模历史或通过模板参数编辑。']}
    svg, counts, omitted = board_preview((folder/'board.kicad_pcb').read_text(encoding='utf-8-sig'))
    (folder/'preview.svg').write_text(svg)
    return {'mode':'pcb','preview':f'/api/files/{folder.name}/preview.svg','counts':counts,
            'files':{'原始 KiCad PCB':f'/api/files/{folder.name}/board.kicad_pcb'},
            'warnings':['二维几何预览；不执行电气或制造校验。'] + (['未完整显示：'+', '.join(omitted)] if omitted else [])}

@app.post('/api/import')
async def import_file(request: Request, filename: str):
    ext=Path(filename).suffix.lower()
    if ext not in ('.step','.stp','.kicad_pcb'):raise HTTPException(415,'服务端支持 STEP/STP 和 KiCad PCB；STL/OBJ/GLB 请通过网页本地导入。')
    folder=OUT/uuid.uuid4().hex;folder.mkdir()
    source=folder/('board.kicad_pcb' if ext=='.kicad_pcb' else 'source.step')
    total=0
    try:
        with source.open('wb') as target:
            async for chunk in request.stream():
                total+=len(chunk)
                if total>20*1024*1024:raise HTTPException(413,'文件不得超过 20 MB。')
                target.write(chunk)
        if total==0:raise HTTPException(422,'文件为空。')
        data=await run_in_threadpool(process_import,folder,ext)
        return dict(data,id=folder.name,name=Path(filename).name)
    except HTTPException:
        shutil.rmtree(folder,ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(folder,ignore_errors=True)
        raise HTTPException(422,'无法读取文件：格式无效、版本不支持或没有可预览几何。') from error

@app.get('/api/files/{ident}/{name}')
def download(ident:str,name:str):
    if not re.fullmatch('[a-f0-9]{32}',ident) or name not in ['model.step','model.stl','board.kicad_pcb','source.step','preview.svg']: raise HTTPException(404)
    path=OUT/ident/name
    if not path.is_file(): raise HTTPException(404)
    return FileResponse(path,filename=name)

if (ROOT/'dist').exists(): app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='web')
