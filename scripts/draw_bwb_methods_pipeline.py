"""Single Chinese reading diagram: execution order, methods, outputs and loops.

For on-screen review, not a reduced journal-column figure. The previous diagrams
and demo stay unchanged. SVG text remains editable; bounds are checked at render.
"""
from pathlib import Path
import argparse
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
W, H = 1600, 1900
INK, MUTED, BLUE, PURPLE = '#21354c', '#62758a', '#4877a6', '#86659c'
ROWS = [
    ('任务与种子', 'M01–M03',
     '校验输入域；冻结任务、模型和范围\n给定尺寸起步（M03：跳过自动尺寸反求）',
     '任务 r：装载 / 距离 / 工况\n设计 x：翼展 / 壁厚 / 功率'),
    ('几何与硬件', 'M04 / M09',
     '三段梯形解析积分；薄壁截面线积分\n部件质量求和；硬件在内层保持固定',
     '面积 / MAC / 容积 / 截面 EI\n硬件质量与空间位置'),
    ('一次任务分析', 'M05 / M06 / M09 / M10',
     '装油 $f_0$ → 质量求和 / 质量矩加权 CG\nISA + 2×2 配平 + 阻力极曲线 / 功率\n显式中点法积分燃耗：爬升 → 巡航 → 下降',
     '迎角 α / 舵偏 δ / 升阻 / 功率\n任务耗油、质量与 CG 轨迹'),
    ('燃油闭合', 'C01',
     'R = 装油 − 总需油\n总需油：耗油 + 储备油 + 不可用油\n相邻有效点括区 → 二分 → 残差复核',
     '有效根：|R| ≤ $10^{-5}$ kg\n无括区 / 失败：未知 + 原因'),
    ('机动载荷', 'M07',
     '按指定 n / 高度 / 速度重新配平\n椭圆升力 − 结构质量的惯性卸载',
     '中点集中力 $F_i$ 与位置 $y_i$\n同一 LoadCase → 06'),
    ('外翼结构', 'M08',
     '根部固支的 Euler–Bernoulli 梁\nκ = M / (EI)；梯形积分求转角与挠度',
     '应力 σ / 挠度 w / 根反力\n覆盖范围：外翼弯曲'),
    ('目标与约束', 'M11',
     '汇总任务、容量与结构结果\n真实目标 f(x)；有符号约束 $g_i$ ≤ 0',
     '可行 / 违约 / 未知\n各项余量及对应工况'),
    ('有限范围搜索', 'O01',
     '小网格对照 + 坐标模式搜索\n可行点比目标；违约点比违反程度\n无改善减半步长；按步长 / 预算停止',
     '未结束：更新设计 x → 02\n结束：从已评价候选中选择'),
    ('候选与依据', 'M12：独立证据待补',
     '已评估可行点中选最小目标\n无可行点：报告搜索范围与失败原因\n记录最紧约束、模型依据和边界命中',
     '当前模型下的候选\n独立 CFD / FEA / 试验待做'),
]


def draw(out, font_path):
    prop = font_manager.FontProperties(fname=str(font_path))
    font_manager.fontManager.addfont(str(font_path))
    family = prop.get_name()
    plt.rcParams.update({'font.family': family, 'font.weight': 'normal',
                         'svg.fonttype': 'none', 'pdf.fonttype': 42})
    fig = plt.figure(figsize=(W/100, H/100), dpi=100, facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1]); ax.set(xlim=(0, W), ylim=(H, 0)); ax.axis('off')
    artists, boxes, edges = [], [], []

    def text(x, y, s, size=17, color=INK, ha='center', bounds=None, rotation=0, bold=False):
        a = ax.text(x, y, s, fontsize=size, color=color, ha=ha, va='center',
                    linespacing=1.36, rotation=rotation, weight='bold' if bold else 'normal')
        artists.append((a, bounds or (4, 4, W-8, H-8)))
        return a

    def edge(points, color=BLUE, dashed=False):
        for a, b in zip(points[:-2], points[1:-1]):
            ax.plot([a[0],b[0]], [a[1],b[1]], color=color, lw=2.2,
                    linestyle=(0,(5,4)) if dashed else '-')
        ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',
                                    mutation_scale=20,lw=2.2,color=color,shrinkA=0,shrinkB=3,
                                    linestyle=(0,(5,4)) if dashed else '-'))
        edges.append(points)

    x, w, h, gap = 210, 1150, 153, 34
    col1, col2 = 500, 1015
    text(351, 51, '计算步骤', 21, bold=True)
    text(757, 51, '采用的方法', 21, bold=True)
    text(1187, 51, '输出 / 传递的结果', 21, bold=True)
    for i, (name, modules, method, output) in enumerate(ROWS):
        y = 90+i*(h+gap)
        fill = '#f3eff7' if i==7 else '#f3f5f7' if i==8 else '#eef4fa'
        border = PURPLE if i==7 else '#8096ad'
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=12',
                                   fc=fill,ec=border,lw=1.7))
        boxes.append((x,y,w,h))
        for cx in [col1,col2]: ax.plot([cx,cx],[y+18,y+h-18],color='#cbd6e1',lw=1)
        text(246,y+34,f'{i+1:02}',15,BLUE,bounds=(x+12,y+14,50,36),bold=True)
        text(355,y+69,name,21,bounds=(x+22,y+42,246,53),bold=True)
        text(355,y+118,modules,13,MUTED,bounds=(x+12,y+96,268,42))
        text(757,y+h/2,method,17,bounds=(col1+17,y+13,col2-col1-34,h-26))
        text(1187,y+h/2,output,16.5,bounds=(col2+16,y+15,x+w-col2-32,h-30))
        if i<8:
            edge([(785,y+h),(785,y+h+gap)])
            if i==3: text(937,y+h+gap/2,'仅有效根继续',13,BLUE,bounds=(822,y+h+1,240,gap-2))

    # Direct physical dependencies from cached geometry/hardware.
    cy2=90+(h+gap)+h/2; cy5=90+4*(h+gap)+h/2; cy6=90+5*(h+gap)+h/2
    edge([(210,cy2),(112,cy2),(112,cy6),(210,cy6)],'#6f8d9d')
    edge([(112,cy5),(210,cy5)],'#6f8d9d')
    ax.plot(112,cy5,'o',ms=5,color='#6f8d9d')
    text(69,(cy2+cy6)/2,'固定几何 / 硬件直接供给',16,'#6f8d9d',rotation=90,
         bounds=(47,cy2+28,42,cy6-cy2-56))
    text(154,cy5-27,'质量分布',13,'#6f8d9d',bounds=(115,cy5-49,93,40))
    text(154,cy6-27,'截面 EI',13,'#6f8d9d',bounds=(115,cy6-49,93,40))

    # Distinct state-solve and design-update loops.
    cy3=90+2*(h+gap)+h/2; cy4=90+3*(h+gap)+h/2; cy8=90+7*(h+gap)+h/2
    edge([(1360,cy4),(1420,cy4),(1420,cy3),(1360,cy3)],BLUE,True)
    text(1392,(cy3+cy4)/2,'内层：只改装油',15,BLUE,rotation=90,
         bounds=(1369,cy3+10,39,cy4-cy3-20))
    edge([(1360,cy8),(1530,cy8),(1530,cy2),(1360,cy2)],PURPLE,True)
    text(1498,(cy2+cy8)/2,'外层：更新设计 x（几何 / 厚度 / 安装功率）',17,PURPLE,rotation=90,
         bounds=(1474,cy2+70,45,cy8-cy2-140))

    text(795,1783,'任一步缺模型或求解失败 → 07「未知 + 原因」；不虚构目标值。',16,'#956b33')
    text(795,1831,'当前主链：低阶工程模型；MIT 资源目前仅支持独立 CL / CD 系数分析。',16,MUTED)
    text(795,1871,'独立复核若否定结果：修订模型 / 任务并重跑；当前候选不等于已验证飞机。',15,MUTED)

    fig.canvas.draw(); renderer=fig.canvas.get_renderer(); overflows=[]; crossed=[]
    for a,(bx,by,bw,bh) in artists:
        b=a.get_window_extent(renderer); actual=(b.x0,H-b.y1,b.width,b.height)
        if actual[0]<bx-1 or actual[1]<by-1 or actual[0]+actual[2]>bx+bw+1 or actual[1]+actual[3]>by+bh+1:
            overflows.append({'text':a.get_text(),'actual':actual,'bounds':[bx,by,bw,bh]})
    for points in edges:
        for a,b in zip(points,points[1:]):
            for tx,ty,tw,th in boxes:
                if any(tx+3<a[0]+(b[0]-a[0])*i/100<tx+tw-3 and ty+3<a[1]+(b[1]-a[1])*i/100<ty+th-3 for i in range(1,100)):
                    crossed.append({'edge':[a,b],'node':[tx,ty,tw,th]})
            for art,_ in artists:
                bb=art.get_window_extent(renderer);tx,ty,tw,th=bb.x0,H-bb.y1,bb.width,bb.height
                if any(tx<a[0]+(b[0]-a[0])*i/100<tx+tw and ty<a[1]+(b[1]-a[1])*i/100<ty+th for i in range(1,100)):
                    crossed.append({'edge':[a,b],'text':art.get_text()})
    out.mkdir(parents=True,exist_ok=True); name='bwb-methods-pipeline-cn'
    for ext in ['png','svg','pdf']: fig.savefig(out/f'{name}.{ext}',dpi=100)
    svg = out/f'{name}.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n', encoding='utf-8')
    report={'canvas':[W,H],'font':family,'font_path':str(font_path),'body_size_pt':17,
            'text_overflow':overflows,'edge_obstructions':crossed,
            'status':'passed' if not overflows and not crossed else 'failed'}
    (out/f'{name}-layout.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    plt.close(fig)
    if overflows or crossed: raise RuntimeError('Layout needs revision; inspect rendered PNG and layout JSON')
    print(f'Wrote single editable methods diagram to {out}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/figures')
    parser.add_argument('--font-path',type=Path,default=Path('C:/Windows/Fonts/msyh.ttc'))
    args=parser.parse_args();draw(args.output,args.font_path)
