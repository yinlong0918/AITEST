"""Bounded STEP and KiCad import; never execute uploaded content."""
import math
import sexpdata


def board_preview(text):
    root = sexpdata.loads(text)
    def tag(node): return str(node[0]) if isinstance(node, list) and node else ''
    def children(node, name): return [x for x in node[1:] if tag(x) == name]
    def child(node, name, default=None): return next(iter(children(node, name)), default or [])
    def nums(node, name, default=(0, 0)):
        value = child(node, name)
        return [float(x) for x in value[1:]] if value else list(default)
    if tag(root) != 'kicad_pcb': raise ValueError('not a KiCad PCB')
    primitives, points, unsupported = [], [], set()
    counts = {'footprints':0, 'pads':0, 'tracks':0}
    def add_point(x,y):
        if not math.isfinite(x+y) or max(abs(x),abs(y)) > 100000: raise ValueError('coordinate out of range')
        points.append((x,y))
    def render(node, origin=(0,0), angle=0):
        kind=tag(node)
        def transform(x,y):
            a=math.radians(angle)
            p=(origin[0]+x*math.cos(a)+y*math.sin(a),origin[1]-x*math.sin(a)+y*math.cos(a))
            add_point(*p)
            return p
        def p(name): return transform(*nums(node,name)[:2])
        def pair(v): return f'{v[0]:.5f},{v[1]:.5f}'
        layer=child(node,'layer'); layer=str(layer[1]) if len(layer)>1 else ''
        color='#d7e4dc' if layer=='Edge.Cuts' else '#d9af62' if layer.endswith('Cu') else '#88b9a2'
        width=nums(node,'width',(.15,))[0]
        stroke=child(node,'stroke')
        if stroke: width=nums(stroke,'width',(.15,))[0]
        width=max(.08,min(width,10))
        style=f'fill="none" stroke="{color}" stroke-width="{width}"'
        if kind in ('footprint','module'):
            counts['footprints']+=1
            at=nums(node,'at'); xy=transform(*at[:2]); rotation=angle+(at[2] if len(at)>2 else 0)
            for item in node[1:]:
                if isinstance(item,list):render(item,xy,rotation)
        elif kind in ('segment','gr_line','fp_line'):
            primitives.append(f'<polyline points="{pair(p("start"))} {pair(p("end"))}" {style}/>')
            if kind=='segment':counts['tracks']+=1
        elif kind in ('gr_rect','fp_rect'):
            a,b=nums(node,'start'),nums(node,'end')
            pts=[transform(a[0],a[1]),transform(b[0],a[1]),transform(b[0],b[1]),transform(a[0],b[1])]
            primitives.append(f'<polygon points="{" ".join(map(pair,pts))}" {style}/>')
        elif kind in ('gr_circle','fp_circle'):
            c,e=p('center'),p('end');r=math.dist(c,e)
            add_point(c[0]-r,c[1]-r);add_point(c[0]+r,c[1]+r)
            primitives.append(f'<circle cx="{c[0]}" cy="{c[1]}" r="{r}" {style}/>')
        elif kind in ('gr_poly','fp_poly','filled_polygon'):
            pts=[transform(*[float(v) for v in n[1:3]]) for n in children(child(node,'pts'),'xy')]
            primitives.append(f'<polygon points="{" ".join(map(pair,pts))}" {style}/>')
        elif kind=='zone':
            for item in children(node,'filled_polygon'):render(item,origin,angle)
            if not children(node,'filled_polygon'):unsupported.add('未填充铜区')
        elif kind in ('arc','gr_arc','fp_arc'):
            a,m,b=p('start'),p('mid'),p('end')
            # Circle through the three KiCad arc points.
            ax,ay=a;mx,my=m;bx,by=b
            det=2*(ax*(my-by)+mx*(by-ay)+bx*(ay-my))
            if abs(det)<1e-10:raise ValueError('degenerate arc')
            aa=ax*ax+ay*ay;mm=mx*mx+my*my;bb=bx*bx+by*by
            cx=(aa*(my-by)+mm*(by-ay)+bb*(ay-my))/det
            cy=(aa*(bx-mx)+mm*(ax-bx)+bb*(mx-ax))/det
            r=math.hypot(ax-cx,ay-cy)
            angles=[math.atan2(y-cy,x-cx) for x,y in (a,m,b)]
            ccw=(angles[2]-angles[0])%(2*math.pi)
            sweep=1 if (angles[1]-angles[0])%(2*math.pi)<=ccw else 0
            travel=ccw if sweep else 2*math.pi-ccw
            for j in range(33):
                theta=angles[0]+(1 if sweep else -1)*travel*j/32
                add_point(cx+r*math.cos(theta),cy+r*math.sin(theta))
            primitives.append(f'<path d="M {pair(a)} A {r} {r} 0 {int(travel>math.pi)} {sweep} {pair(b)}" {style}/>')
            if kind=='arc':counts['tracks']+=1
        elif kind in ('pad','via'):
            counts['pads']+=1
            at=nums(node,'at');x,y=transform(*at[:2]);size=nums(node,'size',(1,1));w=size[0];h=size[1] if len(size)>1 else w
            if min(w,h)<=0 or max(w,h)>10000:raise ValueError('invalid pad')
            add_point(x-w,y-h);add_point(x+w,y+h)
            rotation=angle+(at[2] if len(at)>2 else 0)
            shape=str(node[3]) if kind=='pad' and len(node)>3 else 'circle'
            if shape=='custom':unsupported.add('自定义焊盘（按外接矩形预览）')
            rx=min(w,h)/2 if shape in ('circle','oval') else min(w,h)*.2 if shape=='roundrect' else 0
            primitives.append(f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="{rx}" transform="rotate({-rotation} {x} {y})" fill="#d9af62"/>')
            drill=child(node,'drill')
            if len(drill)>1 and isinstance(drill[1],(float,int)):
                primitives.append(f'<circle cx="{x}" cy="{y}" r="{float(drill[1])/2}" fill="#133e33"/>')
        elif kind in ('gr_text','fp_text','gr_text_box','dimension','gr_curve','fp_curve','image'):
            unsupported.add(kind)
    for node in root[1:]:
        if isinstance(node,list):render(node)
    if not points:raise ValueError('no supported geometry')
    xmin,ymin=map(min,zip(*points));xmax,ymax=map(max,zip(*points))
    if xmax-xmin<=0 or ymax-ymin<=0:raise ValueError('empty bounds')
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{xmin-3} {ymin-3} {xmax-xmin+6} {ymax-ymin+6}"><rect x="{xmin-3}" y="{ymin-3}" width="{xmax-xmin+6}" height="{ymax-ymin+6}" fill="#133e33"/>'+''.join(primitives)+'</svg>'
    return svg, counts, sorted(unsupported)
