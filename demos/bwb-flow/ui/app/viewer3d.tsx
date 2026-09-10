'use client';
import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import {RotateCcw,Maximize2,Box,Layers,Grid2X2} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {fmt,type Result} from './types';
import {buildSurface,buildSkeleton,surfacePoint} from './geometry3d';

type Mode='surface'|'inside'|'frame';
export function Viewer3D({r}:{r:Result}) {
  const host=useRef<HTMLDivElement>(null), frame=useRef<HTMLDivElement>(null);
  const actions=useRef<{mode:(v:Mode)=>void;reset:()=>void;top:()=>void}|null>(null);
  const [mode,setMode]=useState<Mode>('surface'),[error,setError]=useState('');
  const selected=useRef(mode); selected.current=mode;
  useEffect(()=>{
    const el=host.current;if(!el)return;
    let renderer:THREE.WebGLRenderer;
    try {renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});}
    catch {setError('浏览器无法启动三维显示，请开启硬件加速后重新打开。');return;}
    setError('');
    renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
    renderer.setClearColor(0xf0f5fa);renderer.outputColorSpace=THREE.SRGBColorSpace;
    renderer.domElement.setAttribute('aria-label','可交互的 BWB 三维模型，拖动旋转，滚轮缩放');
    renderer.domElement.tabIndex=0;el.appendChild(renderer.domElement);
    const scene=new THREE.Scene(), span=r.inputs.span_m, g=r.geometry;
    const reference=g.geometric_quarter_chord_x_m??g.xac_m;
    const tc=g.section_layout?.thickness_ratio??Number(r.configuration?.model.thickness_ratio??.14);
    const camera=new THREE.PerspectiveCamera(36,1,.02,span*30);
    const controls=new OrbitControls(camera,renderer.domElement);
    controls.enableDamping=true;controls.dampingFactor=.08;
    controls.minDistance=span*.3;controls.maxDistance=span*4;
    controls.target.set(0,0,reference);
    const reset=()=>{camera.up.set(0,1,0);camera.position.set(span*.62,span*.57,reference-span*.9);controls.target.set(0,0,reference);controls.update();};
    reset();
    scene.add(new THREE.HemisphereLight(0xeaf5ff,0x637382,2.3));
    const key=new THREE.DirectionalLight(0xffffff,3.2);key.position.set(-span,span, -span*.5);scene.add(key);
    const fill=new THREE.DirectionalLight(0xb0d8ff,1.6);fill.position.set(span,span*.3,span);scene.add(fill);
    const surfaceMaterial=new THREE.MeshStandardMaterial({color:0x779ebb,metalness:.32,roughness:.32,side:THREE.DoubleSide});
    const surface=new THREE.Mesh(buildSurface(g.stations,16,60,tc),surfaceMaterial);scene.add(surface);
    const skeleton=buildSkeleton(g.sections??[]);scene.add(skeleton);
    const lineMat=new THREE.LineBasicMaterial({color:0x375c78,transparent:true,opacity:.58});
    const contours=new THREE.Group();
    for(const u of [0,1]) {
      const ys=[...g.stations.slice(1).reverse().map(s=>-s.y),...g.stations.map(s=>s.y)];
      contours.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(ys.map(y=>surfacePoint(g.stations,y,u,1,tc))),lineMat));
    }
    scene.add(contours);
    const grid=new THREE.GridHelper(span*2.4,24,0xc5d4e1,0xdce6ef);grid.position.set(0,-r.inputs.root_chord_m*.16,g.xac_m);scene.add(grid);
    const markers=new THREE.Group();scene.add(markers);
    const marker=(x:number,color:number,radius:number)=>{
      const ball=new THREE.Mesh(new THREE.SphereGeometry(radius,20,12),new THREE.MeshStandardMaterial({color,roughness:.3}));
      ball.position.set(0,r.inputs.root_chord_m*.10,x);markers.add(ball);
      const stem=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,x),ball.position]),new THREE.LineBasicMaterial({color}));markers.add(stem);
    };
    marker(reference,0x266ca2,span*.009);
    if(r.mass) marker(r.mass.cg_x_m,0xc17624,span*.009);
    const setDisplay=(v:Mode)=>{
      surface.visible=true;surfaceMaterial.transparent=v!=='surface';
      surfaceMaterial.opacity=v==='inside'?.13:v==='frame'?.035:1;surfaceMaterial.depthWrite=v==='surface';surfaceMaterial.needsUpdate=true;
      skeleton.visible=v!=='surface';markers.visible=v!=='surface';
    };
    setDisplay(selected.current);
    actions.current={mode:setDisplay,reset,top:()=>{camera.up.set(0,0,-1);camera.position.set(0,span*1.65,reference);controls.target.set(0,0,reference);controls.update();}};
    const resize=()=>{const {width,height}=el.getBoundingClientRect();if(width<=0||height<=0)return;camera.aspect=width/height;camera.updateProjectionMatrix();renderer.setSize(width,height);};
    const observer=new ResizeObserver(resize);observer.observe(el);resize();
    let animation=0;const draw=()=>{animation=requestAnimationFrame(draw);controls.update();renderer.render(scene,camera);};draw();
    const lost=(event:Event)=>{event.preventDefault();setError('三维显示连接中断，请刷新页面恢复。');};
    renderer.domElement.addEventListener('webglcontextlost',lost);
    return ()=>{
      cancelAnimationFrame(animation);observer.disconnect();controls.dispose();actions.current=null;
      renderer.domElement.removeEventListener('webglcontextlost',lost);
      const materials=new Set<THREE.Material>();scene.traverse(obj=>{
        const item=obj as THREE.Mesh;if(item.geometry)item.geometry.dispose();
        if(item.material)for(const material of Array.isArray(item.material)?item.material:[item.material])materials.add(material);
      });materials.forEach(m=>m.dispose());renderer.dispose();renderer.domElement.remove();
    };
  },[r]);
  const change=(value:Mode)=>{setMode(value);actions.current?.mode(value);};
  return <article className="panel geometry-panel">
    <div className="panel-title"><div><h3>M04 · BWB 三维几何</h3><span className="muted">翼展 {r.inputs.span_m.toFixed(1)} m · 根弦 {r.inputs.root_chord_m.toFixed(1)} m · 翼面积 {r.geometry.area_m2.toFixed(2)} m²</span></div><span className="model-label">本次计算候选</span></div>
    <div className="viewer-frame" ref={frame}>
      <div className="viewer-toolbar"><div className="viewer-modes" role="group" aria-label="三维显示方式">
        {([['surface','外形',Box],['inside','透明与翼盒',Layers],['frame','实际承力截面',Grid2X2]] as const).map(([v,label,Icon])=><Button key={v} variant={mode===v?'default':'outline'} aria-pressed={mode===v} onClick={()=>change(v)}><Icon/>{label}</Button>)}
      </div><div className="viewer-tools"><Button variant="outline" onClick={()=>actions.current?.top()}>俯视</Button><Button variant="outline" aria-label="复位三维视角" title="复位视角" onClick={()=>actions.current?.reset()}><RotateCcw/></Button><Button variant="outline" aria-label="放大三维视图" title="全屏" onClick={()=>{if(document.fullscreenElement)void document.exitFullscreen();else void frame.current?.requestFullscreen();}}><Maximize2/></Button></div></div>
      <div className="three-host" ref={host}/>
      {error&&<div className="viewer-error" role="alert">{error}</div>}
      <div className="viewer-hint">拖动旋转 · 滚轮缩放 · 右键平移</div>
      {mode!=='surface'&&<div className="viewer-legend"><span><i className="dot cg"/>起始重心</span><span><i className="dot ac"/>几何四分之一弦参考点</span><span><i className="dot rib"/>固支外翼根</span></div>}
    </div>
    <p className="muted">外形、截面、质量与 EI 读取本次同一几何记录。蓝色翼盒仅为实际计算的外翼；中央舱没有结构结果，也没有全机 FE 应力云图。</p>
    {mode!=='surface'&&r.geometry.sections?.[0]&&<div className="section-inspection"><div><h4>外翼根 · 实际薄壁截面</h4><SectionProfile r={r}/></div><dl><div><dt>展向位置</dt><dd>{fmt(r.geometry.sections[0].y_m,3)} m</dd></div><div><dt>壁截面积</dt><dd>{r.geometry.sections[0].area_m2.toExponential(3)} m²</dd></div><div><dt>弯曲惯性矩 I</dt><dd>{r.geometry.sections[0].I_m4.toExponential(3)} m⁴</dd></div><div><dt>弯曲刚度 EI</dt><dd>{r.geometry.sections[0].EI_Nm2.toExponential(3)} N·m²</dd></div></dl></div>}
  </article>;
}

function SectionProfile({r}:{r:Result}) {
 const s=r.geometry.sections![0],points=s.corners;
 const x0=Math.min(...points.map(p=>p.x_m)),x1=Math.max(...points.map(p=>p.x_m)),zmax=Math.max(...points.map(p=>Math.abs(p.z_m)));
 const scale=Math.min(300/(x1-x0),110/(2*zmax));
 return <svg viewBox="0 0 340 150" role="img" aria-label="结构求解使用的外翼根薄壁截面，横纵同比例"><polygon points={points.map(p=>`${20+(p.x_m-x0)*scale},${70-p.z_m*scale}`).join(' ')} fill="#dcecf4" stroke="#2d789e" strokeWidth="2.4"/><text x="20" y="143" fontSize="14" fill="#627889">真实截面比例 · 沿 x 向后 · 以线积分计算 I</text></svg>;
}
