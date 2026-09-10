'use client';
import {useEffect,useState} from 'react';
import {Button} from '@/components/ui/button';
import {Table,TableBody,TableCell,TableHead,TableHeader,TableRow} from '@/components/ui/table';
import {TraceChart} from './charts';
import {activeConstraint,checksOf,comparisonDifferences,fmt,textValue,type Defaults,type Result,type MissionPoint} from './types';

export function RecordDetails({title,value,open=false}:{title:string;value:unknown;open?:boolean}) {
 return <details className="record-details" open={open||undefined}><summary>{title}</summary><pre>{textValue(value)}</pre></details>;
}
const statusLabels:Record<string,string>={executed:'已执行',computed:'已计算',implemented:'已执行简化模型',executed_simplified:'已执行简化模型',configured_demo:'演示问题已配置',available_simplified:'简化模型可调用',hardware_precomputed:'硬件已预计算',attempted_with_failures:'已尝试，含失败',not_evaluated:'未评价',evaluated:'已评价',converged:'已收敛',skipped:'已跳过',not_performed:'未执行',not_implemented:'未实现',failed:'失败',unknown:'证据不足',feasible:'演示约束满足',infeasible:'演示约束违约',demo_converged:'数值已收敛',partial:'部分完成',not_executed:'未执行',unavailable:'不可用'};
export const statusText=(status:string)=>statusLabels[status]??status;

export function ConstraintPanel({r}:{r:Result}) {
 const checks=checksOf(r),[selected,setSelected]=useState<string|null>(null);
 const constraint=checks.find((c,i)=>(c.id??String(i))===selected);
 const condition=constraint?.source?.condition_id,state=constraint?.source?.state_id;
 const node=constraint?.source?.state??(condition||state?r.mission?.trace.find(p=>(condition&&p.condition_id===condition)||(state&&p.state_id===state)):undefined);
 const tightest=activeConstraint(r);
 return <article className="panel" id="constraints"><div className="panel-title"><div><span className="eyebrow">约束评价</span><h3>哪项最接近边界</h3></div><span className="muted">g ≤ 0 满足；余量为正表示尚有空间</span></div>
 {tightest&&<p className="constraint-summary">当前最紧：<strong>{tightest.name}</strong> · 归一化余量 {fmt(tightest.normalized_margin,4)}</p>}
 {!checks.length?<p className="muted">尚无完整约束评价。上游失败不能替代“全域无解”的证明。</p>:<Table><TableHeader><TableRow><TableHead>约束 / 追溯</TableHead><TableHead>计算值</TableHead><TableHead>限制</TableHead><TableHead>有符号 g</TableHead><TableHead>归一化余量</TableHead><TableHead>状态</TableHead></TableRow></TableHeader><TableBody>{checks.map((c,i)=><TableRow key={c.id??i} data-selected={(c.id??String(i))===selected}><TableCell><button className="text-button" onClick={()=>setSelected(c.id??String(i))}>{c.name}</button></TableCell><TableCell>{fmt(c.value,4)} {c.unit}</TableCell><TableCell>{c.sense==='>='?'≥':'≤'} {fmt(c.limit,4)} {c.unit}</TableCell><TableCell>{fmt(c.g,5)}</TableCell><TableCell>{fmt(c.normalized_margin,4)}</TableCell><TableCell><span className={`status ${c.pass_?'limited':'bad'}`}>{c.pass_?'满足':'违约'}</span></TableCell></TableRow>)}</TableBody></Table>}
 {constraint&&<div className="constraint-source"><div className="panel-title"><h3>{constraint.name} · 证据路径</h3><Button variant="ghost" onClick={()=>setSelected(null)}>收起</Button></div><dl><div><dt>来源模块</dt><dd>{constraint.source?.module??'未记录'}</dd></div><div><dt>工况 / 状态</dt><dd className="mono">{condition??'—'} / {state??'—'}</dd></div><div><dt>本次分析</dt><dd className="mono">{r.analysis_id??r.analysis_hash??'未记录'}</dd></div><div><dt>载荷对象</dt><dd className="mono">{constraint.source?.load_case_hash??'见工况来源'}</dd></div></dl>{node&&<RecordDetails title="对应任务节点：时间、质量、配平与功率" value={node} open/>}{constraint.source?.module==='M08'&&<RecordDetails title="结构求解实际消费的载荷对象" value={{load_case:r.structure?.load_case,consumed_load_case_hash:r.structure?.consumed_load_case_hash,sections:r.structure?.sections}}/>}<RecordDetails title="约束原始记录" value={constraint}/></div>}
 </article>;
}

export function ModulePanel({r}:{r:Result}) {
 const records=r.module_records??[],[active,setActive]=useState('M06');
 const current=records.find(m=>m.id===active)??records[0];
 const taskPoints=r.mission?[...(r.mission.initial_state?[r.mission.initial_state as MissionPoint]:[]),...r.mission.trace]:[];
 return <article className="panel"><div className="panel-title"><div><span className="eyebrow">本次实际执行链</span><h3>输入 → 方程与方法 → 输出 → 证据</h3></div></div>
 {!records.length?<p className="muted">本次结果未提供模块执行记录，不能据编号推断已完成。</p>:<><div className="module-grid">{records.map(m=><button aria-pressed={current?.id===m.id} className={current?.id===m.id?'active':''} key={m.id} onClick={()=>setActive(m.id)}><small>{m.id} · {statusText(m.status)}</small>{m.name??m.title??m.id}</button>)}</div>{current&&<div className="module-detail"><div><span className="eyebrow">{current.id} · {statusText(current.status)}</span><h3>{current.name??current.title??current.id}</h3><code>{Array.isArray(current.formula)?current.formula.join('\n'):current.formula}</code><p>{current.method}</p><p className="muted">覆盖边界：{Array.isArray(current.limitation)?current.limitation.join('；'):current.limitation}</p></div><div><RecordDetails title="本次输入" value={current.inputs}/><RecordDetails title="本次输出" value={current.outputs} open/><RecordDetails title="证据与验证状态" value={current.evidence}/></div></div>}</>}
 {current?.id==='M09'&&r.mass&&<Table><TableHeader><TableRow><TableHead>部件</TableHead><TableHead>质量 / kg</TableHead><TableHead>位置 x / m（向后）</TableHead></TableRow></TableHeader><TableBody>{r.mass.components.map(c=><TableRow key={c.name}><TableCell>{c.name}</TableCell><TableCell>{fmt(c.mass_kg)}</TableCell><TableCell>{fmt(c.x_m,3)}</TableCell></TableRow>)}</TableBody></Table>}
 {current?.id==='M10'&&r.mission&&<div className="trace-grid"><div><h3>任务剩余燃油</h3><TraceChart points={taskPoints.map(a=>({x:a.time_s/60,y:a.fuel_kg,phase:a.phase}))} xLabel="真实任务时间 / min" yLabel="燃油 / kg"/></div><div><h3>任务重心</h3><TraceChart points={taskPoints.map(a=>({x:a.time_s/60,y:100*a.cg_mac,phase:a.phase}))} xLabel="真实任务时间 / min" yLabel="重心 / %MAC"/></div></div>}
 {current?.id==='M08'&&r.structure&&<><div className="trace-grid"><div><h3>外翼弯曲应力</h3><TraceChart points={r.structure.trace.map(a=>({x:a.y_m,y:a.stress_MPa}))} xLabel="半翼展向位置 y / m" yLabel="应力 / MPa"/></div><div><h3>外翼弯曲挠度</h3><TraceChart points={r.structure.trace.map(a=>({x:a.y_m,y:a.deflection_m*1000}))} xLabel="半翼展向位置 y / m" yLabel="挠度 / mm"/></div></div><RecordDetails title="实际载荷、根反力及截面 EI" value={{load_case:r.structure.load_case,consumed_load_case_hash:r.structure.consumed_load_case_hash,root_reaction_N:r.structure.root_reaction_N,root_bending_Nm:r.structure.root_bending_Nm,sections:r.structure.sections}}/></>}
 </article>;
}

export function Evidence({r,defaults}:{r:Result;defaults:Defaults|null}) {
 const model=r.model_metadata;
 const [uq,setUq]=useState<unknown>({status:'loading'});
 useEffect(()=>{fetch('http://127.0.0.1:8842/uq/status').then(response=>response.json()).then(setUq).catch(()=>setUq({status:'unavailable',reason:'无法读取离线评估入口状态'}));},[]);
 return <><article className="panel"><div className="panel-title"><h3>模型支持哪些结论</h3><span className="status warning">独立物理复核未完成</span></div><dl><div><dt>实际模型</dt><dd>{model?.id??'未记录'} · {model?.version??'版本未记录'}</dd></div><div><dt>几何解码器</dt><dd>{model?.geometry_decoder_id??'未记录'}</dd></div><div><dt>可提供的量</dt><dd>{model?.supported_quantities?.join('、')??'未记录'}</dd></div><div><dt>适用域检查</dt><dd>{model?.domain_check_status??'见本次记录'}</dd></div></dl><RecordDetails title="坐标、参考量、模型域及资源版本" value={model}/><RecordDetails title="各模块覆盖范围" value={r.coverage}/><RecordDetails title="独立复核状态" value={r.independent_review??{status:'not_performed',reason:'本次未提供独立 CFD / FEA 或试验记录'}}/><p className="muted">求解残差衡量数值一致性；演示约束衡量当前模型内的候选。两者都不能代替真实飞机的证据。</p></article>
 <article className="panel"><h3>本次冻结配置</h3><p className="muted">参数由计算服务的受控配置和 schema 提供。是否用于本次结果以模块执行记录为准；未执行模块的配置不构成计算证据。修改左栏不会改写历史记录。</p>{(['model','solver'] as const).map(group=><div key={group}><h4>{group==='model'?'模型参数':'数值设置'}</h4><Table><TableHeader><TableRow><TableHead>参数</TableHead><TableHead>值</TableHead><TableHead>单位</TableHead></TableRow></TableHeader><TableBody>{Object.entries(r.configuration?.[group]??{}).map(([key,value])=>{const s=(group==='model'?defaults?.schema.model_config:defaults?.schema.solver_config)?.[key];return <TableRow key={key}><TableCell>{s?.label??s?.title??key}</TableCell><TableCell>{textValue(value)}</TableCell><TableCell>{s?.unit??'—'}</TableCell></TableRow>;})}</TableBody></Table></div>)}<RecordDetails title="设计、任务、模型和分析标识" value={{analysis_id:r.analysis_id,analysis_hash:r.analysis_hash,design_hash:r.design_hash,mission_hash:r.mission_hash,load_case_hash:r.load_case_hash,config_hash:r.config_hash,configuration_hashes:r.configuration?.hashes}}/></article>
 <article className="panel"><h3>不确定性与独立证据</h3><p>目前没有经过独立校准的预测区间。窄区间、重复计算零方差或很小的求解残差，都不能表示这架飞机的安全概率。</p><p className="muted">离线评估入口保留参考数据、保真度、划分与校准信息；没有独立数据时维持“未评估”。优化选出的候选仍需要独立复核。</p><RecordDetails title="离线评估入口的实际状态与数据要求" value={uq}/></article></>;
}

export function Comparison({r,baseline,onPin}:{r:Result;baseline:Result|null;onPin:()=>void}) {
 const differences=baseline?comparisonDifferences(baseline,r):['尚未保留基线'];
 const comparable=baseline&&differences.length===0;
 return <article className="panel"><div className="panel-title"><div><h3>与保留基线比较</h3><span className="muted mono">{baseline?.analysis_id??'尚无基线'}</span></div><Button variant="outline" disabled={r.status!=='demo_converged'} onClick={onPin}>保留本次为基线</Button></div>
 {!comparable&&<div className="changed">比较已禁用：{differences.join('、')}不一致或缺少记录。仅并列显示数值，不计算优劣差值。</div>}
 <Table><TableHeader><TableRow><TableHead>比较量</TableHead><TableHead>基线</TableHead><TableHead>本次</TableHead><TableHead>同条件变化</TableHead></TableRow></TableHeader><TableBody>{[['起始质量 / kg',baseline?.mass?.mass_kg,r.mass?.mass_kg],['装油质量 / kg',baseline?.fuel_loaded_kg,r.fuel_loaded_kg],['外翼应力 / MPa',baseline?.structure?.max_stress_MPa,r.structure?.max_stress_MPa]].map(([name,b,c])=><TableRow key={String(name)}><TableCell>{name}</TableCell><TableCell>{fmt(b as number)}</TableCell><TableCell>{fmt(c as number)}</TableCell><TableCell>{comparable&&typeof b==='number'&&typeof c==='number'?`${c-b>=0?'+':''}${fmt(c-b)}`:'—'}</TableCell></TableRow>)}</TableBody></Table></article>;
}
