'use client';
import {fmt} from './types';
export type Point={x:number;y:number|null;phase?:string};
const phaseNames:Record<string,string>={climb:'爬升',cruise:'巡航',descent:'下降'};
/** Physical x coordinates and null gaps are preserved; failed evaluations are never interpolated. */
export function TraceChart({points,xLabel,yLabel,log=false,tolerance}:{points:Point[];xLabel:string;yLabel:string;log?:boolean;tolerance?:number}) {
 const valid=points.filter(p=>Number.isFinite(p.x)&&p.y!==null&&Number.isFinite(p.y));
 if(!valid.length)return <p className="muted">没有可绘制的有效评价；失败记录保留在求解诊断中。</p>;
 const transform=(n:number)=>log?Math.log10(Math.max(Math.abs(n),1e-12)):n;
 const xs=points.map(p=>p.x), ys=valid.map(p=>transform(p.y!));
 if(tolerance!==undefined&&tolerance>0)ys.push(transform(tolerance));
 const x0=Math.min(...xs,0),x1=Math.max(...xs,x0+1),raw0=Math.min(...ys),raw1=Math.max(...ys);
 const pad=Math.max((raw1-raw0)*.1,log?.3:Math.max(Math.abs(raw1)*.04,.001));
 const y0=raw0-pad,y1=raw1+pad;
 const X=(x:number)=>64+(x-x0)/(x1-x0)*486,Y=(y:number)=>170-(y-y0)/(y1-y0)*128;
 const paths:string[]=[];let current='';for(const p of points){if(p.y===null||!Number.isFinite(p.y)){if(current)paths.push(current);current='';}else current+=`${current?' L':'M'}${X(p.x)},${Y(transform(p.y))}`;}if(current)paths.push(current);
 const phases:{name:string;start:number;end:number}[]=[];for(const p of points){if(!p.phase)continue;const last=phases.at(-1);if(last?.name===p.phase)last.end=p.x;else phases.push({name:p.phase,start:last?.end??p.x,end:p.x});}
 return <svg viewBox="0 0 580 220" role="img" aria-label={`${yLabel}随${xLabel}变化${log?'，对数纵轴':''}`} className="trace-chart">
  <text x="12" y="18" className="chart-label">{log?`log₁₀ |${yLabel}|`:yLabel}</text>
  {Array.from({length:4},(_,i)=>{const value=y0+(y1-y0)*i/3;return <g key={i}><line x1="64" x2="550" y1={Y(value)} y2={Y(value)} stroke="#e2e9ef"/><text x="56" y={Y(value)+5} textAnchor="end" className="chart-tick">{fmt(value,log?1:2)}</text></g>;})}
  {phases.map((p,i)=><g key={`${p.name}-${i}`}><rect x={X(p.start)} y="29" width={Math.max(0,X(p.end)-X(p.start))} height="10" fill={i%2?'#e1ecf5':'#d0dfe9'}/><text x={(X(p.start)+X(p.end))/2} y="28" textAnchor="middle" className="chart-phase">{phaseNames[p.name]??p.name}</text>{i>0&&<line x1={X(p.start)} x2={X(p.start)} y1="40" y2="172" stroke="#a9bccb" strokeDasharray="3 5"/>}</g>)}
  <line x1="64" x2="550" y1="170" y2="170" stroke="#9cb1c0"/>
  {Array.from({length:5},(_,i)=>{const value=x0+(x1-x0)*i/4;return <g key={i}><line x1={X(value)} x2={X(value)} y1="170" y2="175" stroke="#9cb1c0"/><text x={X(value)} y="192" textAnchor="middle" className="chart-tick">{fmt(value,Number.isInteger(x1)&&xLabel.includes('编号')?0:1)}</text></g>;})}
  {tolerance!==undefined&&tolerance>0&&<g><line x1="64" x2="550" y1={Y(transform(tolerance))} y2={Y(transform(tolerance))} stroke="#b87026" strokeDasharray="6 4"/><text x="547" y={Y(transform(tolerance))-5} textAnchor="end" className="chart-tick" fill="#9d621f">容差 {tolerance.toExponential(1)}</text></g>}
  {paths.map((d,i)=><path key={i} d={d} fill="none" stroke="#286a99" strokeWidth="2.4"/>)}
  {valid.length<4&&valid.map((p,i)=><circle key={i} cx={X(p.x)} cy={Y(transform(p.y!))} r="3" fill="#286a99"/>)}
  <text x="550" y="215" textAnchor="end" className="chart-label">{xLabel}</text>
 </svg>;
}
