"""Two editable diagrams of the executed BWB analysis/search, with layout checks.

Regular-weight body text and short labels follow the user's TPAMI-style example.
Run --font 'DejaVu Serif' --output ... to check a fallback font independently.
"""
from pathlib import Path
import argparse
import json
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon

ROOT=Path(__file__).resolve().parents[1]
BLUE='#496e9d'; INK='#203247'; PURPLE='#8b7ca5'; MUTED='#657486'
ARTISTS=[]; NODES=[]; EDGES=[]


def canvas(font):
    ARTISTS.clear(); NODES.clear(); EDGES.clear()
    plt.rcParams.update({'font.family':'serif','font.serif':[font,'DejaVu Serif'],
                         'font.weight':'normal','svg.fonttype':'none','font.size':22,
                         'pdf.fonttype':42})
    fig=plt.figure(figsize=(16,9),dpi=100,facecolor='white')
    ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,1600),ylim=(900,0));ax.axis('off')
    return fig,ax


def text(ax,x,y,label,size=22,color=INK,weight='normal',bounds=None):
    artist=ax.text(x,y,label,ha='center',va='center',fontsize=size,color=color,
                   weight=weight,linespacing=1.25)
    ARTISTS.append((artist,bounds or (3,3,1594,894)))
    return artist


def panel(ax,x,y,w,h,title):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=13',
                 linewidth=1.5,edgecolor='#a7a0b6',facecolor='#faf9fc',linestyle=(0,(6,4))))
    text(ax,x+w/2,y+38,title,24,weight='bold',bounds=(x+15,y+10,w-30,58))


def node(ax,x,y,w,h,label,kind='run',small=None):
    fill,edge,style=('#eaf0f8',BLUE,'-') if kind=='run' else ('#f4f3f5','#9b9ba4',(0,(5,4)))
    if kind=='reference': fill,edge,style='#f1ecf8',PURPLE,(0,(2,3))
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=10',
                 linewidth=1.8,edgecolor=edge,facecolor=fill,linestyle=style))
    text(ax,x+w/2,y+h*.43 if small else y+h/2,label,23,bounds=(x+12,y+10,w-24,h-20 if not small else h*.65))
    if small: text(ax,x+w/2,y+h*.82,small,18,MUTED,bounds=(x+10,y+h*.66,w-20,h*.33))
    NODES.append((x,y,w,h))


def arrow(ax,points,kind='data',label=None,label_at=None):
    color=BLUE if kind=='iterate' else '#9b9ba4' if kind=='future' else '#6d88ab'
    dash=(0,(5,4)) if kind!='data' else '-'
    for a,b in zip(points[:-2],points[1:-1]):
        ax.plot([a[0],b[0]],[a[1],b[1]],color=color,lw=2.1,linestyle=dash)
    ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',mutation_scale=20,
                                 lw=2.1,color=color,linestyle=dash,shrinkA=0,shrinkB=4))
    EDGES.append((points,kind))
    if label: text(ax,*label_at,label,18,color)


def save(fig,name,out,font):
    out.mkdir(parents=True,exist_ok=True);fig.canvas.draw();renderer=fig.canvas.get_renderer()
    problems=[]
    for artist,(x,y,w,h) in ARTISTS:
        bb=artist.get_window_extent(renderer)
        actual=(bb.x0,900-bb.y1,bb.width,bb.height)
        if actual[0]<x-1 or actual[1]<y-1 or actual[0]+actual[2]>x+w+1 or actual[1]+actual[3]>y+h+1:
            problems.append({'text':artist.get_text(),'actual':actual,'container':[x,y,w,h]})
    crossings=[]; text_crossings=[]
    for points,kind in EDGES:
        for a,b in zip(points,points[1:]):
            for x,y,w,h in NODES:
                # Interior samples exclude legal start/end ports on node boundaries.
                for i in range(1,100):
                    p=(a[0]+(b[0]-a[0])*i/100,a[1]+(b[1]-a[1])*i/100)
                    if x+3<p[0]<x+w-3 and y+3<p[1]<y+h-3:
                        crossings.append({'edge':[a,b],'node':[x,y,w,h]});break
            for artist,_ in ARTISTS:
                bb=artist.get_window_extent(renderer)
                x,y,w,h=bb.x0,900-bb.y1,bb.width,bb.height
                for i in range(1,100):
                    p=(a[0]+(b[0]-a[0])*i/100,a[1]+(b[1]-a[1])*i/100)
                    if x<p[0]<x+w and y<p[1]<y+h:
                        text_crossings.append({'edge':[a,b],'text':artist.get_text()});break
    report={'font':font,'canvas':[1600,900],'bounded_text_count':len(ARTISTS),
            'text_overflow':problems,'edge_through_node':crossings,'edge_through_text':text_crossings,'minimum_body_pt':18,
            'status':'passed' if not problems and not crossings and not text_crossings else 'failed'}
    (out/(name+'-layout.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    fig.savefig(out/(name+'.png'),dpi=100)
    fig.savefig(out/(name+'.svg'))
    svg=out/(name+'.svg');svg.write_text('\n'.join(s.rstrip() for s in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
    plt.close(fig)
    if problems or crossings or text_crossings: raise RuntimeError(f'{name}: layout failed, see JSON')


def overview(out,font):
    fig,ax=canvas(font)
    panel(ax,55,55,1490,425,'A. Fixed-task design search')
    node(ax,95,175,260,165,'Task + seed',small='M03 skipped')
    node(ax,440,175,320,165,'Decode geometry\n& hardware',small='M04 / M09')
    node(ax,845,175,290,165,'Analyze\nfixed design',small='C01 / M05–M10')
    node(ax,1220,175,285,165,'Search\n& compare',small='O01 / M11')
    for a,b in [(355,440),(760,845),(1135,1220)]: arrow(ax,[(a,258),(b,258)])
    arrow(ax,[(1360,340),(1360,422),(600,422),(600,340)],'iterate','update design x',(965,392))
    panel(ax,55,535,1490,260,'B. Candidate and evidence')
    node(ax,95,625,370,125,'Model support\n+ tightest constraint')
    node(ax,575,625,365,125,'Selected candidate\n+ search limits')
    node(ax,1050,625,455,125,'Independent check','future',small='No CFD / FEA evidence yet')
    arrow(ax,[(1450,340),(1450,505),(500,505),(500,648),(575,648)])
    arrow(ax,[(575,688),(465,688)])
    arrow(ax,[(940,688),(1050,688)],'future')
    arrow(ax,[(1280,750),(1280,840),(25,840),(25,258),(95,258)],'future','if evidence disagrees: revise models / problem',(700,813))
    text(ax,800,880,'Solid: executed low-order chain    Dashed blue: numerical update    Dashed gray: required evidence',17,MUTED)
    save(fig,'bwb-engineering-pipeline',out,font)


def detail(out,font):
    fig,ax=canvas(font)
    panel(ax,55,55,455,430,'A. Fixed hardware')
    node(ax,95,150,375,150,'Geometry + sections\nMaterial + layout',small='M04')
    node(ax,95,350,375,95,'Mass / CG ledger',small='M09 · hardware cached')
    arrow(ax,[(282,300),(282,350)])
    panel(ax,590,55,955,470,'B. Fuel closure at fixed design')
    node(ax,635,155,350,120,'Fuel trial',small='validity kept per attempt')
    node(ax,1145,155,350,120,'March mission',small='mass / CG → trim → burn')
    node(ax,635,360,350,120,'Bracket / bisect',small='C01 · valid branch only')
    node(ax,1145,360,350,120,'Residual + validity',small='M05 / M06 / M10')
    arrow(ax,[(985,215),(1145,215)])
    arrow(ax,[(1320,275),(1320,360)])
    arrow(ax,[(1145,420),(985,420)],'iterate')
    arrow(ax,[(810,360),(810,275)],'iterate')
    arrow(ax,[(470,397),(550,397),(550,120),(1320,120),(1320,155)])
    panel(ax,55,570,1490,260,'C. Loads and response')
    node(ax,1050,660,445,120,'Midpoint LoadCase',small='M07 · force / case hash')
    node(ax,580,660,350,120,'Outer-wing beam',small='M08 · same load hash')
    node(ax,95,660,360,120,'Signed constraints',small='M11 → outer search')
    arrow(ax,[(1320,480),(1320,660)],label='fuel root',label_at=(1420,550))
    arrow(ax,[(1050,720),(930,720)])
    arrow(ax,[(580,720),(455,720)])
    arrow(ax,[(282,445),(282,545),(1015,545),(1015,690),(930,690)],label='sections / EI',label_at=(410,519))
    arrow(ax,[(1015,630),(1200,630),(1200,660)],label='mass relief',label_at=(1130,601))
    text(ax,800,880,'MIT: separate CL / CD analysis only · No implicit trim or load fallback · Independent validation absent',17,MUTED)
    save(fig,'bwb-analysis-coupling',out,font)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/figures')
    parser.add_argument('--font',default='Times New Roman')
    args=parser.parse_args();overview(args.output,args.font);detail(args.output,args.font)
    print(f'Two diagrams and text/edge checks written to {args.output}')
