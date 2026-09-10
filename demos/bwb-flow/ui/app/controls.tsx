'use client';
import {Input} from '@/components/ui/input';
import {Slider} from '@/components/ui/slider';
import {Select,SelectContent,SelectItem,SelectTrigger,SelectValue} from '@/components/ui/select';
import type {Config,FieldMap} from './types';
const choiceLabels:Record<string,string>={sustained:'持续机动（需要功率维持）',instantaneous:'瞬时机动（保留加速度）'};
export function ControlledFields({values,schema,onChange,prefix,sliders=false}:{values:Config;schema:FieldMap;onChange:(key:string,value:number|string)=>void;prefix:string;sliders?:boolean}) {
 return <>{Object.entries(schema).map(([key,s])=>{
  if(!(key in values))return null;
  const value=values[key],title=s.label??s.title??key,id=`${prefix}-${key}`;
  return <div className="control" key={key}>{s.choices?<><label className="choice-label" htmlFor={id}>{title}</label><Select value={String(value)} onValueChange={v=>{if(v!==null)onChange(key,v);}}><SelectTrigger id={id} aria-label={title}><SelectValue>{choiceLabels[String(value)]??String(value)}</SelectValue></SelectTrigger><SelectContent>{s.choices.map(v=><SelectItem key={v} value={v}>{choiceLabels[v]??v}</SelectItem>)}</SelectContent></Select></>:<><div className="control-label"><label htmlFor={id}>{title}</label><div><Input id={id} type="number" aria-label={title} min={s.min} max={s.max} step={s.step??'any'} value={value} onChange={e=>onChange(key,Number(e.target.value))}/><span>{s.unit==='dimensionless'?'1':s.unit??''}</span></div></div>{sliders&&typeof value==='number'&&s.min!==undefined&&s.max!==undefined&&<Slider aria-label={`${title}滑块`} min={s.min} max={s.max} step={s.step} value={[value]} onValueChange={v=>onChange(key,Array.isArray(v)?v[0]:v)}/>}</>}{s.description&&<p className="field-description">{s.description}</p>}</div>;
 })}</>;
}
