"""Traceable low-order BWB demonstrator, deliberately not aircraft validation.

Coordinates: x aft, y right, z up; positive pitch coefficient nose-up.
The geometric quarter-chord reference is NOT an identified aerodynamic centre.
"""
from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
import time
import uuid
from collections import Counter
from types import MappingProxyType

from configuration import (DEFAULTS, BOUNDS, INPUT_FIELDS, MODULE_METADATA,
                           ModelConfig, SolverConfig, config_schema, digest, validate_inputs)

G = 9.80665
VERSION = 'illustrative-bwb-v2'
IMPLEMENTATION_HASH = hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('configuration.py').read_bytes()).hexdigest()
ASSUMPTIONS = MappingProxyType(ModelConfig().snapshot())  # Compatibility, immutable.


class Unsupported(Exception):
    def __init__(self, code, details=None):
        self.code, self.details = code, details or {}
        super().__init__(code)


def trapezoid(y, x):
    return sum((y[i]+y[i+1])*.5*(x[i+1]-x[i]) for i in range(len(x)-1))


def thickness_profile(u):
    """Total depth / (maximum thickness ratio * chord); integral is exactly .6."""
    return 4*u*(1-u)*(1-.5*(2*u-1)**2)


def thinwall_section(points, thickness):
    """Exact line integrals for straight thin-wall segments, closed polygon.

    The model neglects local t³/12 terms and corner overlap, explicitly a
    centre-line thin-wall model. Coordinates are chordwise x and vertical z.
    """
    if thickness <= 0 or len(points) < 3:
        raise ValueError('Invalid thin-wall section')
    area = sx = sz = ixx = izz = 0.
    for a, b in zip(points, points[1:] + points[:1]):
        length = math.hypot(b[0]-a[0], b[1]-a[1])
        weight = thickness*length
        area += weight
        sx += weight*(a[0]+b[0])/2
        sz += weight*(a[1]+b[1])/2
        ixx += weight*(a[1]**2+a[1]*b[1]+b[1]**2)/3
        izz += weight*(a[0]**2+a[0]*b[0]+b[0]**2)/3
    if area <= 0:
        raise ValueError('Zero section area')
    cx, cz = sx/area, sz/area
    return dict(area_m2=area, I_m4=ixx-area*cz*cz, I_vertical_m4=izz-area*cx*cx,
                centroid_x_m=cx, centroid_z_m=cz,
                extreme_z_m=max(abs(p[1]-cz) for p in points), perimeter_m=area/thickness)


def station_at(g, y):
    for a, b in zip(g['stations'], g['stations'][1:]):
        if y <= b['y']+1e-10:
            f=(y-a['y'])/(b['y']-a['y'])
            return dict(y=y, c=a['c']+f*(b['c']-a['c']), x=a['x']+f*(b['x']-a['x']))
    return {**g['stations'][-1], 'y':y}


def profile_points(chord, tc, front=0., rear=1., count=32):
    u=[front+(rear-front)*i/count for i in range(count+1)]
    upper=[(v*chord,.5*tc*chord*thickness_profile(v)) for v in u]
    lower=[(v*chord,-.5*tc*chord*thickness_profile(v)) for v in reversed(u)]
    return upper+lower


def section_at(g, y):
    st=station_at(g,y); layout=g['section_layout']
    points=profile_points(st['c'],layout['thickness_ratio'],layout['front_spar_u'],layout['rear_spar_u'],8)
    sec=thinwall_section(points,layout['wall_thickness_m'])
    sec.update(y_m=y, chord_m=st['c'], leading_edge_x_m=st['x'],
               corners=[dict(x_m=x+st['x'],z_m=z) for x,z in points],
               EI_Nm2=layout['material_E_Pa']*sec['I_m4'],
               mass_per_length_kg_m=layout['material_density_kg_m3']*sec['area_m2'],
               model='thin_wall_polygon_line_integrals', computed_scope='outer_wing_bending')
    sec['centroid_x_m']+=st['x']
    return sec


def geometry(p, model_config=None):
    cfg=ModelConfig.from_dict(model_config)
    h,c=p['span_m']/2,p['root_chord_m']
    ys=[0.,.2*h,.55*h,h]; chords=[c,.75*c,.35*c,.12*c]; le=[0.]
    for i,sweep in enumerate([40.,32.,25.]):
        le.append(le[-1]+(ys[i+1]-ys[i])*math.tan(math.radians(sweep)))
    area=2*trapezoid(chords,ys)
    c2int=sum((ys[i+1]-ys[i])*(chords[i]**2+chords[i]*chords[i+1]+chords[i+1]**2)/3 for i in range(3))
    mac=2*c2int/area
    reference_integral=0.
    for i in range(3):
        xa,xb=le[i]+chords[i]/4,le[i+1]+chords[i+1]/4
        reference_integral+=(ys[i+1]-ys[i])/6*(chords[i]*xa+(chords[i]+chords[i+1])*(xa+xb)+chords[i+1]*xb)
    ref=2*reference_integral/area
    t=p['thickness_mm']/1000
    skin_unit=thinwall_section(profile_points(1.,cfg.thickness_ratio),t)
    box_unit=thinwall_section(profile_points(1.,cfg.thickness_ratio,.2,.55,8),t)
    skin_mass=2*cfg.material_density_kg_m3*skin_unit['area_m2']*trapezoid(chords,ys)
    box_mass=2*cfg.material_density_kg_m3*box_unit['area_m2']*trapezoid(chords[1:],ys[1:])
    structure_mass=skin_mass+box_mass+cfg.connection_mass_kg
    gross_volume=2*.6*cfg.thickness_ratio*c2int
    free_volume=cfg.usable_volume_fraction*gross_volume-structure_mass/cfg.material_density_kg_m3
    tank=p['tank_fraction']*free_volume
    g=dict(stations=[dict(y=y,c=cc,x=xx) for y,cc,xx in zip(ys,chords,le)],
        area_m2=area, mac_m=mac, geometric_quarter_chord_x_m=ref, xac_m=ref,
        reference_description='geometric area-weighted quarter-chord; not a proven aerodynamic centre',
        aspect_ratio=p['span_m']**2/area,gross_volume_m3=gross_volume,free_volume_m3=free_volume,
        payload_volume_m3=cfg.payload_space_fraction*free_volume,tank_volume_m3=tank,
        fuel_capacity_kg=tank*cfg.usable_tank_fraction*cfg.fuel_density_kg_m3,
        structural_mass_kg=structure_mass,skin_mass_kg=skin_mass,wingbox_mass_kg=box_mass,
        section_layout=dict(id='airfoil-following-thinwall-box-v2',front_spar_u=.2,rear_spar_u=.55,
            thickness_ratio=cfg.thickness_ratio,wall_thickness_m=t,root_y_m=ys[1],
            material_E_Pa=cfg.material_E_Pa,material_density_kg_m3=cfg.material_density_kg_m3,
            root_boundary='clamped outer-wing root; central body is not analyzed',
            description='Skin and box caps are separate physical layers. Box reinforcement follows the outer profile; only box EI carries bending in this reduced model.'),
        structural_components=[
            dict(id='skin',mass_kg=skin_mass,distribution='chord-proportional',y_min_m=0.,y_max_m=h,
                 mass_per_chord_length=cfg.material_density_kg_m3*skin_unit['area_m2'],
                 contributes_to_outer_box_EI=False),
            dict(id='box_reinforcement',mass_kg=box_mass,distribution='chord-proportional',y_min_m=ys[1],y_max_m=h,
                 mass_per_chord_length=cfg.material_density_kg_m3*box_unit['area_m2'],
                 contributes_to_outer_box_EI=True),
            dict(id='central_connections',mass_kg=cfg.connection_mass_kg,distribution='two_symmetric_point_masses',
                 y_m=.1*h,contributes_to_outer_box_EI=False)])
    g['sections']=[section_at(g,y) for y in ys[1:]]
    g['geometry_hash']=digest(g)
    return g


def atmosphere(h):
    T=288.15-.0065*h
    pressure=101325*(T/288.15)**(G/(287.05287*.0065))
    rho=pressure/(287.05287*T)
    mu=1.716e-5*(T/273.15)**1.5*(273.15+110.4)/(T+110.4)
    return dict(temperature_K=T,pressure_Pa=pressure,rho=rho,mu=mu,a=math.sqrt(1.4*287.05287*T))


def ledger(p,g,fuel,model_config=None):
    cfg=ModelConfig.from_dict(model_config)
    ref,mac=g['geometric_quarter_chord_x_m'],g['mac_m']
    components=[dict(id='structure',name='结构（蒙皮/贴合翼型翼盒/中央连接项）',mass_kg=g['structural_mass_kg'],x_m=ref+.03*mac),
        dict(id='propulsion',name='推进安装',mass_kg=cfg.propulsion_base_mass_kg+p['power_kw']/cfg.propulsion_specific_power_kw_kg,x_m=ref+.40*mac),
        dict(id='systems',name='按设计额定载荷固定的系统',mass_kg=cfg.systems_base_mass_kg+cfg.systems_rated_payload_fraction*p.get('rated_payload_kg',DEFAULTS['rated_payload_kg']),x_m=ref-.05*mac),
        dict(id='payload',name='本次任务装载',mass_kg=p['payload_kg'],x_m=ref-.12*mac),
        dict(id='landing_gear',name='固定起落架示例项',mass_kg=cfg.landing_gear_mass_kg,x_m=ref),
        dict(id='fuel',name='当前燃油',mass_kg=fuel,x_m=ref+p['tank_offset_mac']*mac)]
    mass=sum(a['mass_kg'] for a in components)
    cg=sum(a['mass_kg']*a['x_m'] for a in components)/mass
    return dict(mass_kg=mass,hardware_mass_kg=mass-fuel-p['payload_kg'],cg_x_m=cg,
        cg_mac=.25+(cg-ref)/mac,components=components,
        position_assumption='Fixed installation offsets relative to geometric quarter-chord; demonstrator mass ledger, not measured hardware')


def trim(p,g,fuel,h,V,vz=0.,load_factor=1.,model_config=None,enforce_power=True):
    cfg=ModelConfig.from_dict(model_config)
    lm=ledger(p,g,fuel,cfg);at=atmosphere(h);q=.5*at['rho']*V*V;gamma=math.asin(vz/V)
    lift=load_factor*lm['mass_kg']*G*math.cos(gamma);cl=lift/(q*g['area_m2'])
    cosine=math.cos(math.radians(cfg.aerodynamic_sweep_deg))
    a=2*math.pi*cosine/(1+2*cosine/(cfg.oswald_e*g['aspect_ratio']))
    b,c,d=cfg.cl_delta_per_rad,cfg.cm_alpha_per_rad,cfg.cm_delta_per_rad
    rhs1=cl-cfg.cl0;rhs2=-cfg.cm0-(lm['cg_mac']-.25)*cl;det=a*d-b*c
    if abs(det)<1e-12:
        raise Unsupported('singular_trim_matrix')
    alpha=(rhs1*d-b*rhs2)/det;delta=(a*rhs2-rhs1*c)/det
    CL=cfg.cl0+a*alpha+b*delta
    CM=cfg.cm0+c*alpha+d*delta+(lm['cg_mac']-.25)*CL
    cd=cfg.cd0+CL*CL/(math.pi*cfg.oswald_e*g['aspect_ratio'])+cfg.elevon_drag_factor*delta*delta
    drag=q*g['area_m2']*cd;thrust=drag+lm['mass_kg']*G*math.sin(gamma)
    required=thrust*V/(cfg.propeller_efficiency*1000)
    available=p['power_kw']*cfg.installed_power_fraction*at['rho']/1.225
    vals=dict(alpha_deg=math.degrees(alpha),elevon_deg=math.degrees(delta),CL=CL,CD=cd,Cm_CG=CM,
        lift_N=lift,drag_N=drag,thrust_N=thrust,ld=CL/cd,power_required_kw=required,power_available_kw=available,
        fuel_flow_kg_s=cfg.bsfc_kg_kwh*required/3600,lift_residual_N=q*g['area_m2']*CL-lift,
        moment_residual_Nm=q*g['area_m2']*g['mac_m']*CM,cm_alpha_per_rad=c+(lm['cg_mac']-.25)*a,
        mass_kg=lm['mass_kg'],cg_mac=lm['cg_mac'],cg_x_m=lm['cg_x_m'],q_Pa=q,
        Re=at['rho']*V*g['mac_m']/at['mu'],Mach=V/at['a'],fixed_control=True,
        moment_reference_x_m=g['geometric_quarter_chord_x_m'],power_enforced=enforce_power)
    if not (cfg.alpha_min_deg<=vals['alpha_deg']<=cfg.alpha_max_deg and cfg.elevon_min_deg<=vals['elevon_deg']<=cfg.elevon_max_deg):
        raise Unsupported('trim_outside_demo_bounds',vals)
    if required<0: raise Unsupported('descent_needs_extra_drag',vals)
    if enforce_power and required>available: raise Unsupported('insufficient_power',vals)
    if vals['cm_alpha_per_rad']>=0: raise Unsupported('static_stability_not_supported',vals)
    if not enforce_power:
        # Instantaneous pull-up allows longitudinal deceleration: m Vdot = Tavailable-D.
        vals['longitudinal_acceleration_ms2']=(available*1000*cfg.propeller_efficiency/V-drag)/lm['mass_kg']
        vals['maneuver_interpretation']='instantaneous normal equilibrium; permits longitudinal acceleration/deceleration, not sustained constant speed'
    return vals


def mission(p,g,fuel0,steps=None,model_config=None,solver_config=None):
    cfg=ModelConfig.from_dict(model_config);sc=SolverConfig.from_dict(solver_config)
    steps=sc.mission_steps if steps is None else steps
    if isinstance(steps,bool) or not isinstance(steps,int) or steps<1: raise ValueError('Invalid mission steps')
    phases=[('climb',p['altitude_m']/cfg.climb_rate_ms,min(cfg.climb_speed_cap_ms,p['cruise_speed_ms']),cfg.climb_rate_ms),
        ('cruise',p['cruise_km']*1000/p['cruise_speed_ms'],p['cruise_speed_ms'],0.),
        ('descent',p['altitude_m']/abs(cfg.descent_rate_ms),min(cfg.descent_speed_cap_ms,p['cruise_speed_ms']),cfg.descent_rate_ms)]
    fuel=fuel0;t=distance=h=0.;trace=[];stages=[];critical=[];initial_state=None
    domain_states={}
    max_force=max_moment=0.;min_margin=float('inf');max_cma=-float('inf')
    for phase,duration,V,vz in phases:
        phase_start=t
        if duration==0: continue
        dt=duration/steps
        def state(at_fuel,at_h,at_time,node):
            if at_fuel<0:
                raise Unsupported('fuel_exhausted',dict(module='M10',phase=phase,time_s=at_time,node=node,fuel_kg=at_fuel))
            try:
                answer=trim(p,g,at_fuel,at_h,V,vz,model_config=cfg)
            except Unsupported as exc:
                raise Unsupported(exc.code,{**exc.details,'module':'M06','phase':phase,'time_s':at_time,'node':node}) from exc
            return dict(phase=phase,time_s=at_time,altitude_m=at_h,fuel_kg=at_fuel,
                        condition_id=f'{phase}:{at_time:.9f}',state_id=digest([at_time,at_fuel,at_h,V])[:16],**answer)
        for i in range(steps):
            start=state(fuel,h,t,'start')
            if initial_state is None: initial_state=start
            mid=state(fuel-.5*dt*start['fuel_flow_kg_s'],h+.5*dt*vz,t+.5*dt,'midpoint')
            fuel-=dt*mid['fuel_flow_kg_s'];t+=dt;h=max(0.,h+dt*vz)
            distance+=V*math.cos(math.asin(vz/V))*dt
            end=state(fuel,h,t,'end')
            for entry in (start,mid,end):
                candidates=dict(alpha_min=entry['alpha_deg']-cfg.alpha_min_deg,
                    alpha_max=cfg.alpha_max_deg-entry['alpha_deg'],
                    elevon_min=entry['elevon_deg']-cfg.elevon_min_deg,
                    elevon_max=cfg.elevon_max_deg-entry['elevon_deg'],
                    fixed_control_stability=-entry['cm_alpha_per_rad'])
                for key, value in candidates.items():
                    if key not in domain_states or value<domain_states[key]['margin']:
                        domain_states[key]=dict(margin=value,state=entry)
                margin=entry['power_available_kw']-entry['power_required_kw']
                if margin<min_margin:
                    min_margin=margin;critical=[entry]
                max_cma=max(max_cma,entry['cm_alpha_per_rad'])
                max_force=max(max_force,abs(entry['lift_residual_N']))
                max_moment=max(max_moment,abs(entry['moment_residual_Nm']))
            trace.append(dict(distance_km=distance/1000,**end))
        stages.append(dict(phase=phase,start_time_s=phase_start,end_time_s=t,duration_s=duration))
    return dict(burn_kg=fuel0-fuel,end_fuel_kg=fuel,duration_h=t/3600,total_distance_km=distance/1000,
        trace=trace,phases=stages,lift_residual_N=max_force,moment_residual_Nm=max_moment,
        min_power_margin_kw=min_margin,max_cm_alpha_per_rad=max_cma,
        minimum_power_state=critical[0],initial_state=initial_state,domain_states=domain_states,
        method='explicit midpoint; every start/midpoint/end checks trim, power and fixed-control stability')


def solve_fuel(evaluator,capacity_kg,model_config=None,solver_config=None,seed_kg=None):
    """Find a root on an observed connected valid branch, never assign failed residuals.

    The seed is diagnostic only; a deterministic full scan chooses the same
    first valid bracket for all legal seeds. Scan adjacency includes failures.
    No bracket is a bounded-search unknown, not a proof of global infeasibility.
    """
    cfg=ModelConfig.from_dict(model_config);sc=SolverConfig.from_dict(solver_config)
    if not math.isfinite(capacity_kg) or capacity_kg<=0:
        return dict(status='unknown',failure='invalid_fuel_capacity',attempts=[],diagnostics={'capacity_kg':capacity_kg})
    if seed_kg is None: seed_kg=capacity_kg*sc.fuel_seed_fraction
    if isinstance(seed_kg,bool) or not isinstance(seed_kg,(int,float)) or not math.isfinite(seed_kg) or not 0<=seed_kg<=capacity_kg:
        raise ValueError('Fuel seed outside capacity')
    attempts=[];cache={}
    def evaluate(fuel,phase):
        started=time.perf_counter()
        try:
            m=evaluator(fuel)
            residual=fuel-((1+cfg.reserve_fraction_of_burn)*m['burn_kg']+cfg.unusable_fuel_kg)
            if not math.isfinite(residual): raise Unsupported('nonfinite_fuel_residual')
            rec=dict(iteration=len(attempts)+1,fuel_guess_kg=fuel,required_fuel_kg=fuel-residual,
                residual_kg=residual,status='evaluated',search_phase=phase,elapsed_s=time.perf_counter()-started)
            cache[fuel]=m
        except Unsupported as exc:
            rec=dict(iteration=len(attempts)+1,fuel_guess_kg=fuel,residual_kg=None,status=exc.code,
                     failure=exc.code,failure_details=exc.details,search_phase=phase,elapsed_s=time.perf_counter()-started)
        attempts.append(rec)
        return rec
    evaluate(seed_kg,'seed')
    scanned=[evaluate(capacity_kg*i/(sc.fuel_scan_points-1),'scan') for i in range(sc.fuel_scan_points)]
    exact=[r for r in scanned if r['residual_kg'] is not None and abs(r['residual_kg'])<=sc.fuel_tolerance_kg]
    brackets=[(a,b) for a,b in zip(scanned,scanned[1:]) if a['residual_kg'] is not None and b['residual_kg'] is not None and a['residual_kg']*b['residual_kg']<0]
    diagnostics=dict(capacity_kg=capacity_kg,scan_points=sc.fuel_scan_points,
        valid_evaluations=sum(r['residual_kg'] is not None for r in scanned),
        failure_counts=dict(Counter(r['status'] for r in scanned if r['residual_kg'] is None)),
        observed_brackets_kg=[[a['fuel_guess_kg'],b['fuel_guess_kg']] for a,b in brackets],
        claim='Finite scan only: missing bracket does not prove no feasible fuel root; no signs assigned to failed evaluations.')
    if exact:
        chosen=exact[0]
    elif brackets:
        left,right=brackets[0]
        for _ in range(sc.fuel_max_iterations):
            chosen=evaluate((left['fuel_guess_kg']+right['fuel_guess_kg'])/2,'bisection')
            if chosen['residual_kg'] is None:
                return dict(status='unknown',failure='fuel_branch_interrupted',attempts=attempts,
                            diagnostics={**diagnostics,'interrupted_at_kg':chosen['fuel_guess_kg']})
            if abs(chosen['residual_kg'])<=sc.fuel_tolerance_kg: break
            if chosen['residual_kg']*left['residual_kg']<0: right=chosen
            else: left=chosen
        else:
            return dict(status='unknown',failure='fuel_iteration_budget_exhausted',attempts=attempts,diagnostics=diagnostics)
    else:
        return dict(status='unknown',failure='fuel_bracket_not_found',attempts=attempts,diagnostics=diagnostics)
    final=evaluate(chosen['fuel_guess_kg'],'independent_residual_recheck')
    if final['residual_kg'] is None or abs(final['residual_kg'])>sc.fuel_tolerance_kg:
        return dict(status='unknown',failure='fuel_recheck_failed',attempts=attempts,diagnostics=diagnostics)
    return dict(status='converged',fuel_kg=final['fuel_guess_kg'],residual_kg=final['residual_kg'],
                mission=cache[final['fuel_guess_kg']],attempts=attempts,diagnostics=diagnostics)


def beam_response(y,forces,EI):
    """Actual midpoint point forces, clamped root, free tip; positive upward."""
    if len(forces)!=len(y)-1 or len(EI)!=len(y) or any(ei<=0 for ei in EI):
        raise ValueError('Invalid beam data')
    mid=[.5*(y[i]+y[i+1]) for i in range(len(forces))]
    moments=[sum(f*(s-pos) for f,s in zip(forces,mid) if s>=pos) for pos in y]
    curvature=[m/ei for m,ei in zip(moments,EI)];theta=[0.];displacement=[0.]
    for i in range(len(y)-1):
        dx=y[i+1]-y[i]
        theta.append(theta[-1]+dx*(curvature[i]+curvature[i+1])/2)
        displacement.append(displacement[-1]+dx*(theta[-1]+theta[-2])/2)
    return moments,displacement


def load_definition(p,cfg):
    return dict(id='demo_symmetric_pull_up',load_factor=p['load_factor'],speed_ms=cfg.design_load_speed_ms,
        altitude_m=cfg.design_load_altitude_m,maneuver_type=cfg.maneuver_type,
        lift_distribution='elliptic_prescribed',inertia='same_geometry_structural_components',
        missing=['torsion','gust envelope','central body','non-structural mass distribution'])


def build_load_case(p,g,fuel,model_config=None,solver_config=None,n=None):
    cfg=ModelConfig.from_dict(model_config);sc=SolverConfig.from_dict(solver_config)
    n=sc.load_strips if n is None else n
    if isinstance(n,bool) or not isinstance(n,int) or n<5: raise ValueError('Invalid load strips')
    try:
        tc=trim(p,g,fuel,cfg.design_load_altitude_m,cfg.design_load_speed_ms,
                load_factor=p['load_factor'],model_config=cfg,enforce_power=cfg.maneuver_type=='sustained')
    except Unsupported as exc:
        raise Unsupported(exc.code,{**exc.details,'module':'M07','condition_id':'demo_symmetric_pull_up','state_id':digest([fuel,g['geometry_hash']])[:16]}) from exc
    h=p['span_m']/2;root=.2*h
    # Insert the actual structural root even when n does not divide five.
    nodes=sorted(set([root if abs(h*i/n-root)<1e-12 else h*i/n for i in range(n+1)]+[root]))
    mids=[(a+b)/2 for a,b in zip(nodes,nodes[1:])];widths=[b-a for a,b in zip(nodes,nodes[1:])]
    weights=[math.sqrt(max(0.,1-(y/h)**2))*dy for y,dy in zip(mids,widths)]
    aero=[.5*tc['lift_N']*w/sum(weights) for w in weights]
    strip_mass=[0.]*len(mids);component_sums={}
    for component in g['structural_components']:
        local=[0.]*len(mids)
        if component['distribution']=='chord-proportional':
            for i,(a,b) in enumerate(zip(nodes,nodes[1:])):
                lo=max(a,component['y_min_m']);hi=min(b,component['y_max_m'])
                if hi>lo:
                    # Integrate piecewise linear chord exactly, including kink stations.
                    cuts=[lo]+[s['y'] for s in g['stations'] if lo<s['y']<hi]+[hi]
                    local[i]=component['mass_per_chord_length']*trapezoid([station_at(g,y)['c'] for y in cuts],cuts)
        else:
            index=next(i for i,(a,b) in enumerate(zip(nodes,nodes[1:])) if a<=component['y_m']<=b)
            local[index]=component['mass_kg']/2
        component_sums[component['id']]=2*sum(local)
        strip_mass=[a+b for a,b in zip(strip_mass,local)]
    inertia=[-p['load_factor']*G*m for m in strip_mass]
    forces=[a+b for a,b in zip(aero,inertia)];first=nodes.index(root)
    case=dict(definition=load_definition(p,cfg),representation='midpoint_point_forces',
        nodes_m=nodes[first:],positions_m=mids[first:],forces_N=forces[first:],
        aero_forces_N=aero[first:],inertia_forces_N=inertia[first:],structural_strip_mass_kg=strip_mass[first:],
        full_halfwing=dict(nodes_m=nodes,positions_m=mids,aero_forces_N=aero,inertia_forces_N=inertia,forces_N=forces),
        root_y_m=root,geometry_hash=g['geometry_hash'],fuel_kg=fuel,trim=tc,
        component_mass_reconstruction_kg=component_sums,
        structural_mass_error_kg=abs(2*sum(strip_mass)-g['structural_mass_kg']),
        lift_integral_error_N=abs(2*sum(aero)-tc['lift_N']))
    case['hash']=digest(case);case['id']='load-'+case['hash'][:16]
    return case


def solve_structure(g,case,model_config=None):
    cfg=ModelConfig.from_dict(model_config)
    payload={k:v for k,v in case.items() if k not in ('hash','id')}
    if digest(payload)!=case['hash']: raise ValueError('Load case changed after creation')
    if case['geometry_hash']!=g['geometry_hash']: raise ValueError('Load case geometry mismatch')
    y=case['nodes_m'];forces=case['forces_N'];sections=[section_at(g,pos) for pos in y]
    expected=[(a+b)/2 for a,b in zip(y,y[1:])]
    if expected!=case['positions_m']: raise ValueError('Beam requires actual midpoint loads')
    moments,displacement=beam_response(y,forces,[s['EI_Nm2'] for s in sections])
    stress=[abs(m*s['extreme_z_m']/s['I_m4'])/1e6 for m,s in zip(moments,sections)]
    reaction=-sum(forces);reaction_moment=-sum(f*(pos-y[0]) for f,pos in zip(forces,case['positions_m']))
    root_force_error=abs(reaction+sum(forces));root_moment_error=abs(reaction_moment+moments[0])
    return dict(load_case=case,load_case_id=case['id'],load_case_hash=case['hash'],
        consumed_load_case_hash=case['hash'],load_factor=case['definition']['load_factor'],
        load_speed_ms=case['definition']['speed_ms'],lift_N=case['trim']['lift_N'],
        max_stress_MPa=max(stress),tip_deflection_m=displacement[-1],root_bending_Nm=moments[0],
        root_shear_N=sum(forces),root_reaction_N=reaction,root_reaction_moment_Nm=reaction_moment,
        outer_length_m=y[-1]-y[0],map_force_error_N=root_force_error,map_span_moment_error_Nm=root_moment_error,
        load_interface_force_error_N=root_force_error,load_interface_moment_error_Nm=root_moment_error,
        lift_integral_error_N=case['lift_integral_error_N'],structural_mass_error_kg=case['structural_mass_error_kg'],
        pressure_field='prescribed elliptic lift; no CFD pressure field',sections=sections,
        trace=[dict(y_m=pos,moment_Nm=m,deflection_m=u,stress_MPa=s,section_index=i) for i,(pos,m,u,s) in enumerate(zip(y,moments,displacement,stress))],
        trim=case['trim'],scope='outer-wing bending only; no torsion, buckling, central-body or full aircraft verification')


def structure(p,g,fuel,n=None,model_config=None,solver_config=None):
    case=build_load_case(p,g,fuel,model_config,solver_config,n)
    return solve_structure(g,case,model_config)


def model_metadata(g):
    return dict(id=VERSION,version='2.0.0',source_commit=None,implementation_hash=IMPLEMENTATION_HASH,geometry_decoder_id='three-trapezoid-bwb-v2',
        units=dict(length='m',mass='kg',force='N',stress='MPa',angle='rad'),
        axes='x aft, y right, z up; pitch coefficient nose-up',S_ref=g['area_m2'],length_ref=g['mac_m'],
        moment_reference=dict(x_m=g['geometric_quarter_chord_x_m'],kind='geometric quarter-chord reference'),
        supported_inputs=['geometry','TAS','altitude','fuel','payload','load_factor','control_deflection'],
        supported_quantities=['CL','CD','Cm','fixed_control_cm_alpha','trim','elliptic_lift','outer_wing_bending'],
        supported_load_cases=['demo_symmetric_pull_up'],validity_domain='controlled demo schema; assumed linear aero domain, not independently established physics domain',
        domain_check_status='assumed_bounded_domain; input_bounds_and_trim_checks_only',evidence_ids=['analytic_and_regression_tests'],
        uncertainty_metadata_or_null=None,uncertainty_reason='No independent calibration/test data; deterministic residual is not model uncertainty',
        unavailable_quantities=['CFD_pressure','torsion','buckling','stall','central_body_stress','independent_physical_validity'])


def analysis_capability_check(metadata,g):
    required={'CL','CD','Cm','trim','outer_wing_bending'}
    missing=sorted(required-set(metadata.get('supported_quantities',[])))
    failures=[]
    if missing: failures.append('missing_quantities')
    if metadata.get('geometry_decoder_id')!='three-trapezoid-bwb-v2': failures.append('geometry_decoder_mismatch')
    if 'demo_symmetric_pull_up' not in metadata.get('supported_load_cases',[]): failures.append('load_case_not_supported')
    if metadata.get('S_ref')!=g['area_m2'] or metadata.get('length_ref')!=g['mac_m']:
        failures.append('reference_normalization_mismatch')
    if metadata.get('moment_reference',{}).get('x_m')!=g['geometric_quarter_chord_x_m']:
        failures.append('moment_reference_mismatch')
    return dict(status='available_simplified' if not failures else 'unavailable',
                required_quantities=sorted(required),missing_quantities=missing,failures=failures,
                evidence_scope='Declared low-order capabilities and checked interface references; not independent physics validation')


def constraint(identifier,name,value,limit,unit,sense,source,scale=None):
    signed=value-limit if sense=='<=' else limit-value
    divisor=scale if scale is not None else abs(limit)
    if divisor<=0: raise ValueError('A positive normalization scale is required')
    return dict(id=identifier,name=name,value=value,limit=limit,unit=unit,sense=sense,g=signed,
        margin=-signed,normalized_margin=-signed/divisor,normalization_scale=divisor,pass_=signed<=0,source=source)


def analyze(supplied=None,model_config=None,solver_config=None):
    p=validate_inputs(supplied);cfg=ModelConfig.from_dict(model_config);sc=SolverConfig.from_dict(solver_config)
    g=geometry(p,cfg)
    design={k:p[k] for k,s in INPUT_FIELDS.items() if s['group']=='design'}
    requirements={k:p[k] for k,s in INPUT_FIELDS.items() if s['group']=='mission'}
    definition=load_definition(p,cfg)
    config=dict(model=cfg.snapshot(),solver=sc.snapshot())
    hardware_config={k:getattr(cfg,k) for k in ('thickness_ratio','material_E_Pa','material_density_kg_m3',
        'connection_mass_kg','propulsion_base_mass_kg','propulsion_specific_power_kw_kg',
        'systems_base_mass_kg','systems_rated_payload_fraction','landing_gear_mass_kg',
        'usable_volume_fraction','usable_tank_fraction','payload_space_fraction')}
    configuration_hash=digest(config);design_hash=digest(dict(design=design,hardware_config=hardware_config,version=VERSION))
    # A design identity must include the physical model/material configuration;
    # analysis identity additionally includes mission, load definition and solver.
    comparison=digest(dict(mission=requirements,load_case_definition=definition,configuration=config,version=VERSION,implementation_hash=IMPLEMENTATION_HASH))
    analysis_hash=digest(dict(design=design_hash,comparability=comparison))
    records=[]
    result=dict(inputs=p,design=design,requirements=requirements,design_hash=design_hash[:16],
        analysis_hash=analysis_hash,analysis_id=str(uuid.uuid4()),mission_hash=digest(requirements),
        comparability_hash=comparison,load_case_definition=definition,load_case_definition_hash=digest(definition),
        config_hash=configuration_hash,configuration={**config,'hash':configuration_hash,'model_hash':digest(cfg.snapshot()),'solver_hash':digest(sc.snapshot())},
        assumptions=cfg.snapshot(),geometry=g,model=VERSION,model_metadata=model_metadata(g),
        engineering_validation='not_performed',formal_feasibility='unknown',objective='not_defined_in_analysis_mode',
        iterations=[],module_records=records,coverage={},constraints=[],checks=[],
        numeric_convergence='not_attempted',evaluation_status='unknown',demo_constraints_satisfied=None,
        uncertainty_metadata_or_null=None,uncertainty_reason='No independent reference evaluation or calibration',
        sizing=dict(status='skipped',mode='given_candidate',reason='Analyze consumes supplied hardware; task-driven sizing belongs to explicit outer entry'),
        load_case_hash=None,constraint_applicability=dict(maneuver_power=dict(
            status='applicable' if cfg.maneuver_type=='sustained' else 'not_applicable',
            reason='Sustained constant-speed power balance' if cfg.maneuver_type=='sustained' else
                'Instantaneous normal equilibrium permits longitudinal deceleration; acceleration is reported instead')))
    def record(mid,status,inputs=None,outputs=None,**extra):
        records.append(dict(id=mid,status=status,inputs=inputs or {},outputs=outputs or {},**MODULE_METADATA[mid],**extra))
        result['coverage'][mid]=status
    record('M01','executed',outputs=dict(design=design,mission=requirements,load_case=definition))
    record('M02','configured_demo',outputs=dict(optimization='external_explicit_problem',formal_requirements='pending_teacher_confirmation'))
    record('M03','skipped',outputs=result['sizing'])
    record('M04','executed_simplified',outputs=dict(geometry_hash=g['geometry_hash'],structural_mass_kg=g['structural_mass_kg'],section_layout=g['section_layout']))
    record('M05','available_simplified',outputs=dict(atmosphere='ISA troposphere',velocity='TAS'))
    record('M09','hardware_precomputed',outputs=ledger(p,g,0,cfg))
    capability=analysis_capability_check(result['model_metadata'],g)
    result['model_capability_check']=capability
    if capability['status']=='unavailable':
        result.update(status='unsupported',failure='missing_model_capability',failure_details=capability)
        record('M06','unavailable',outputs=capability)
        for mid in ('M07','M08','M10','M11'):record(mid,'not_executed')
        record('M12','not_performed')
        result['coverage']['C01']='not_attempted'
        return result
    solved=solve_fuel(lambda fuel:mission(p,g,fuel,model_config=cfg,solver_config=sc),g['fuel_capacity_kg'],cfg,sc)
    result['iterations']=solved['attempts'];result['fuel_solver_diagnostics']=solved['diagnostics']
    if solved['status']!='converged':
        result.update(status='unsupported',failure=solved['failure'],failure_details=solved['diagnostics'],numeric_convergence='unknown')
        result['coverage']['C01']='not_converged'
        record('M06','attempted_with_failures',outputs=solved['diagnostics'])
        record('M10','unknown',outputs=dict(failure=solved['failure'],attempts=len(solved['attempts'])))
        record('M07','not_executed');record('M08','not_executed');record('M11','not_evaluated');record('M12','not_performed')
        return result
    fuel=solved['fuel_kg'];m=solved['mission']
    result.update(fuel_loaded_kg=fuel,fuel_residual_kg=solved['residual_kg'],mission=m,mass=ledger(p,g,fuel,cfg),
                  numeric_convergence='converged',status='demo_converged')
    result['coverage']['C01']='demo_converged'
    record('M06','executed_simplified',outputs=dict(model=VERSION,max_lift_residual_N=m['lift_residual_N'],max_moment_residual_Nm=m['moment_residual_Nm']))
    record('M10','converged',outputs=dict(fuel_loaded_kg=fuel,residual_kg=solved['residual_kg'],mission_burn_kg=m['burn_kg']))
    source=dict(analysis_hash=analysis_hash,module='M10',condition_id='mission_initial',state_id=m['initial_state']['state_id'],state=m['initial_state'])
    checks=[constraint('fuel_capacity','油箱容量',fuel,g['fuel_capacity_kg'],'kg','<=',source),
        constraint('payload_volume','载荷空间代理',g['payload_volume_m3'],cfg.required_payload_volume_m3,'m³','>=',{**source,'module':'M04','condition_id':'fixed_geometry'}),
        constraint('rated_payload','额定装载',p['payload_kg'],p['rated_payload_kg'],'kg','<=',{**source,'module':'M01','condition_id':'mission_loading'}),
        constraint('mission_power','任务最小功率余量',m['min_power_margin_kw'],0.,'kW','>=',
            {**source,'module':'M06','condition_id':m['minimum_power_state']['condition_id'],'state_id':m['minimum_power_state']['state_id'],'state':m['minimum_power_state']},p['power_kw'])]
    for key,label,quantity,limit,sense,unit,scale in [
        ('alpha_min','任务最小迎角','alpha_deg',cfg.alpha_min_deg,'>=','°',cfg.alpha_max_deg-cfg.alpha_min_deg),
        ('alpha_max','任务最大迎角','alpha_deg',cfg.alpha_max_deg,'<=','°',cfg.alpha_max_deg-cfg.alpha_min_deg),
        ('elevon_min','任务最小舵偏','elevon_deg',cfg.elevon_min_deg,'>=','°',cfg.elevon_max_deg-cfg.elevon_min_deg),
        ('elevon_max','任务最大舵偏','elevon_deg',cfg.elevon_max_deg,'<=','°',cfg.elevon_max_deg-cfg.elevon_min_deg),
        ('fixed_control_stability','任务固定舵静稳定导数','cm_alpha_per_rad',0.,'<=','rad⁻¹',abs(cfg.cm_alpha_per_rad))]:
        st=m['domain_states'][key]['state']
        checks.append(constraint(key,label,st[quantity],limit,unit,sense,
            {**source,'module':'M06','condition_id':st['condition_id'],'state_id':st['state_id'],'state':st},scale))
    try:
        case=build_load_case(p,g,fuel,cfg,sc)
        result['load_case_hash']=case['hash']
        record('M07','executed_simplified',outputs=dict(load_case_id=case['id'],load_case_hash=case['hash'],load_case=case))
        s=solve_structure(g,case,cfg);result['structure']=s
        record('M08','executed_simplified',outputs=dict(consumed_load_case_hash=case['hash'],max_stress_MPa=s['max_stress_MPa'],tip_deflection_m=s['tip_deflection_m']))
        worst=max(s['trace'],key=lambda entry:entry['stress_MPa'])
        ss={**source,'module':'M08','condition_id':case['id'],'state_id':digest([case['hash'],fuel])[:16],'load_case_hash':case['hash']}
        checks.extend([constraint('stress','外翼弯曲应力',s['max_stress_MPa'],cfg.demo_stress_limit_MPa,'MPa','<=',{**ss,'y_m':worst['y_m'],'section_index':worst['section_index']}),
            constraint('deflection','外翼端挠度',abs(s['tip_deflection_m']),cfg.demo_deflection_limit_fraction*s['outer_length_m'],'m','<=',{**ss,'y_m':s['trace'][-1]['y_m']})])
        maneuver=case['trim']
        ms={**ss,'module':'M07','state':maneuver}
        if cfg.maneuver_type=='sustained':
            checks.append(constraint('maneuver_power','持续机动功率余量',maneuver['power_available_kw']-maneuver['power_required_kw'],0.,'kW','>=',ms,p['power_kw']))
        for key,label,quantity,limit,sense,unit,scale in [
            ('maneuver_alpha_min','机动最小迎角','alpha_deg',cfg.alpha_min_deg,'>=','°',cfg.alpha_max_deg-cfg.alpha_min_deg),
            ('maneuver_alpha_max','机动最大迎角','alpha_deg',cfg.alpha_max_deg,'<=','°',cfg.alpha_max_deg-cfg.alpha_min_deg),
            ('maneuver_elevon_min','机动最小舵偏','elevon_deg',cfg.elevon_min_deg,'>=','°',cfg.elevon_max_deg-cfg.elevon_min_deg),
            ('maneuver_elevon_max','机动最大舵偏','elevon_deg',cfg.elevon_max_deg,'<=','°',cfg.elevon_max_deg-cfg.elevon_min_deg),
            ('maneuver_stability','机动固定舵静稳定导数','cm_alpha_per_rad',0.,'<=','rad⁻¹',abs(cfg.cm_alpha_per_rad))]:
            checks.append(constraint(key,label,maneuver[quantity],limit,unit,sense,ms,scale))
        result['demo_constraints_satisfied']=all(c['pass_'] for c in checks)
        result['evaluation_status']='feasible' if result['demo_constraints_satisfied'] else 'infeasible'
    except Unsupported as exc:
        result.update(status='unsupported',failure=exc.code,failure_details=exc.details,evaluation_status='unknown',
            partial_results=dict(mission='valid_simplified',fuel_closure='converged',structure='unavailable'))
        if exc.code=='insufficient_power' and 'power_required_kw' in exc.details:
            checks.append(constraint('maneuver_power','持续机动功率余量',exc.details['power_available_kw']-exc.details['power_required_kw'],0.,'kW','>=',
                {**source,'module':'M07','condition_id':exc.details['condition_id'],'state_id':exc.details['state_id'],
                 'load_case_definition_hash':result['load_case_definition_hash'],'state':exc.details},p['power_kw']))
        record('M07','failed',outputs=dict(failure=exc.code,details=exc.details));record('M08','not_executed')
    result['checks']=checks;result['constraints']=checks
    result['minimum_constraint_margin']=min(checks,key=lambda c:c['normalized_margin'])
    record('M11','evaluated' if result['evaluation_status']!='unknown' else 'partial',outputs=dict(evaluation_status=result['evaluation_status'],constraints=checks))
    record('M12','not_performed',outputs=dict(independent_evidence='none',engineering_validation='not_performed'))
    result['coverage']['O01']='external_search_or_manual_change'
    return result


if __name__=='__main__':
    r=analyze()
    print(json.dumps({k:v for k,v in r.items() if k not in ['mission','structure','module_records','iterations']},indent=2,ensure_ascii=True))
