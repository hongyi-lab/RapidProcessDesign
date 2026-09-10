"""Independent, deliberately low-order BWB engineering-flow demonstrator.

No RapidProcessDesign imports and no MIT data, weights or source. All coefficients
and limits are demo assumptions. These calculations are not aircraft validation.
Coordinates for geometry/CG are x aft, y right, z up; pitch coefficient is nose-up.
"""
from __future__ import annotations

import hashlib
import json
import math

G = 9.80665
DEFAULTS = dict(root_chord_m=3.2, span_m=8.0, thickness_mm=1.2,
                payload_kg=70.0, cruise_km=500.0, cruise_speed_ms=45.0,
                altitude_m=1500.0, power_kw=80.0, tank_offset_mac=0.04,
                tank_fraction=0.12, load_factor=2.5)
BOUNDS = dict(root_chord_m=(2.4, 4.2), span_m=(6., 14.), thickness_mm=(.3, 3.),
              payload_kg=(10., 160.), cruise_km=(50., 1800.), cruise_speed_ms=(28., 65.),
              altitude_m=(0., 3000.), power_kw=(12., 100.), tank_offset_mac=(-.25, .45),
              tank_fraction=(.015, .25), load_factor=(1., 5.))
ASSUMPTIONS = dict(cl0=.2, cl_delta_per_rad=.35, cm0=.015, cm_alpha_per_rad=-.35,
                   cm_delta_per_rad=-.75, cd0=.022, oswald_e=.8,
                   propeller_efficiency=.78, bsfc_kg_kwh=.30, material_E_Pa=70e9,
                   material_density_kg_m3=2700., fuel_density_kg_m3=800.,
                   demo_stress_limit_MPa=120., demo_deflection_limit_fraction=.03,
                   usable_volume_fraction=.70, payload_space_fraction=.35,
                   required_payload_volume_m3=.12, reserve_fraction_of_burn=.15,
                   unusable_fuel_kg=1.5, climb_rate_ms=2., descent_rate_ms=-1.,
                   design_load_speed_ms=60., design_load_altitude_m=0.,
                   alpha_bounds_deg=[-6.,12.], elevon_bounds_deg=[-20.,20.])


class Unsupported(Exception):
    def __init__(self, code, details=None):
        self.code, self.details = code, details or {}
        super().__init__(code)


def trapezoid(y, x):
    return sum((y[i]+y[i+1])*.5*(x[i+1]-x[i]) for i in range(len(x)-1))


def geometry(p):
    h, c = p['span_m']/2, p['root_chord_m']
    ys = [0., .20*h, .55*h, h]
    chords = [c, .75*c, .35*c, .12*c]
    # Independent trapezoidal station geometry: not the MIT parameter convention.
    le = [0.]
    for i, sweep in enumerate([40.,32.,25.]):
        le.append(le[-1]+(ys[i+1]-ys[i])*math.tan(math.radians(sweep)))
    S = 2*trapezoid(chords, ys)
    c2int = sum((ys[i+1]-ys[i])*(chords[i]**2+chords[i]*chords[i+1]+chords[i+1]**2)/3 for i in range(3))
    mac = 2*c2int/S
    # Integrate the product of two linear functions exactly by Simpson.
    xac_int = 0.
    for i in range(3):
        xa, xb = le[i]+chords[i]/4, le[i+1]+chords[i+1]/4
        xac_int += (ys[i+1]-ys[i])/6*(chords[i]*xa+4*((chords[i]+chords[i+1])/2)*((xa+xb)/2)+chords[i+1]*xb)
    xac = 2*xac_int/S
    t = p['thickness_mm']/1000
    skin_mass = 2.05*S*t*2700
    # Extra box caps/webs are separate reinforcements, not counted as skin again.
    box_mass = 2*2700*t*.94*trapezoid(chords[1:],ys[1:])
    struct = skin_mass+box_mass+8.
    gross_volume = 2*.6*.14*c2int
    free_volume = .70*gross_volume-struct/2700
    tank = p['tank_fraction']*free_volume
    return dict(stations=[dict(y=y,c=cc,x=xx) for y,cc,xx in zip(ys,chords,le)],
                area_m2=S, mac_m=mac, xac_m=xac, aspect_ratio=p['span_m']**2/S,
                gross_volume_m3=gross_volume, free_volume_m3=free_volume,
                payload_volume_m3=.35*free_volume, tank_volume_m3=tank,
                fuel_capacity_kg=tank*.95*800, structural_mass_kg=struct,
                skin_mass_kg=skin_mass, wingbox_mass_kg=box_mass)


def atmosphere(h):
    T=288.15-.0065*h
    pressure=101325*(T/288.15)**(G/(287.05287*.0065))
    rho=pressure/(287.05287*T)
    mu=1.716e-5*(T/273.15)**1.5*(273.15+110.4)/(T+110.4)
    return dict(temperature_K=T,pressure_Pa=pressure,rho=rho,mu=mu,a=math.sqrt(1.4*287.05287*T))


def ledger(p,g,fuel):
    ac,mac=g['xac_m'],g['mac_m']
    components=[dict(name='结构（蒙皮/翼盒/示例连接项）',mass_kg=g['structural_mass_kg'],x_m=ac+.03*mac),
                dict(name='推进安装',mass_kg=18+p['power_kw']/2.5,x_m=ac+.40*mac),
                dict(name='系统',mass_kg=25+.12*p['payload_kg'],x_m=ac-.05*mac),
                dict(name='载荷',mass_kg=p['payload_kg'],x_m=ac-.12*mac),
                dict(name='固定起落架示例项',mass_kg=15,x_m=ac),
                dict(name='当前油箱燃油',mass_kg=fuel,x_m=ac+p['tank_offset_mac']*mac)]
    mass=sum(a['mass_kg'] for a in components)
    cg=sum(a['mass_kg']*a['x_m'] for a in components)/mass
    return dict(mass_kg=mass,cg_x_m=cg,cg_mac=.25+(cg-ac)/mac,components=components)


def trim(p,g,fuel,h,V,vz=0.,load_factor=1.):
    lm=ledger(p,g,fuel); at=atmosphere(h)
    q=.5*at['rho']*V*V
    gamma=math.asin(vz/V)
    L=load_factor*lm['mass_kg']*G*math.cos(gamma)
    cl=L/(q*g['area_m2'])
    a=2*math.pi*math.cos(math.radians(32))/(1+2*math.cos(math.radians(32))/(.8*g['aspect_ratio']))
    b=.35; c=-.35; d=-.75
    rhs1=cl-.2; rhs2=-.015-(lm['cg_mac']-.25)*cl
    det=a*d-b*c
    alpha=(rhs1*d-b*rhs2)/det; delta=(a*rhs2-rhs1*c)/det
    CL=.2+a*alpha+b*delta
    CM=.015+c*alpha+d*delta+(lm['cg_mac']-.25)*CL
    cd=.022+CL*CL/(math.pi*.8*g['aspect_ratio'])+.025*delta*delta
    drag=q*g['area_m2']*cd
    thrust=drag+lm['mass_kg']*G*math.sin(gamma)
    required_kw=thrust*V/(.78*1000)
    available_kw=p['power_kw']*.85*at['rho']/1.225
    vals=dict(alpha_deg=math.degrees(alpha),elevon_deg=math.degrees(delta),CL=CL,CD=cd,Cm_CG=CM,
              lift_N=L,drag_N=drag,thrust_N=thrust,ld=CL/cd,power_required_kw=required_kw,
              power_available_kw=available_kw,fuel_flow_kg_s=.30*required_kw/3600,
              lift_residual_N=q*g['area_m2']*CL-L,moment_residual_Nm=q*g['area_m2']*g['mac_m']*CM,
              cm_alpha_per_rad=c+(lm['cg_mac']-.25)*a,mass_kg=lm['mass_kg'],cg_mac=lm['cg_mac'],
              cg_x_m=lm['cg_x_m'],q_Pa=q,Re=at['rho']*V*g['mac_m']/at['mu'],Mach=V/at['a'])
    if not (-6<=vals['alpha_deg']<=12 and -20<=vals['elevon_deg']<=20):
        raise Unsupported('trim_outside_demo_bounds',vals)
    if required_kw<0:
        raise Unsupported('descent_needs_extra_drag',vals)
    if required_kw>available_kw:
        raise Unsupported('insufficient_power',vals)
    if vals['cm_alpha_per_rad']>=0:
        raise Unsupported('static_stability_not_supported',vals)
    return vals


def mission(p,g,fuel0,steps=36):
    # Prescribed climb / cruise leg / descent. Takeoff and landing are NOT modeled.
    phases=[('climb',p['altitude_m']/2.,min(42.,p['cruise_speed_ms']),2.),
            ('cruise',p['cruise_km']*1000/p['cruise_speed_ms'],p['cruise_speed_ms'],0.),
            ('descent',p['altitude_m'],min(45.,p['cruise_speed_ms']),-1.)]
    fuel=fuel0; t=0.; distance=0.; h=0.; trace=[]
    max_force=max_moment=0.; min_power_margin=float('inf')
    for phase,duration,V,vz in phases:
        if duration==0: continue
        dt=duration/steps
        for i in range(steps):
            if fuel<0: raise Unsupported('fuel_exhausted',{'phase':phase,'time_s':t})
            # Midpoint integration evaluates trim at midpoint mass and altitude.
            start=trim(p,g,fuel,h,V,vz)
            middle_fuel=fuel-.5*dt*start['fuel_flow_kg_s']
            if middle_fuel<0: raise Unsupported('fuel_exhausted',{'phase':phase,'time_s':t})
            mid=trim(p,g,middle_fuel,h+.5*dt*vz,V,vz)
            fuel-=dt*mid['fuel_flow_kg_s']
            if fuel<0: raise Unsupported('fuel_exhausted',{'phase':phase,'time_s':t+dt})
            t+=dt; h=max(0.,h+dt*vz); distance+=V*math.cos(math.asin(vz/V))*dt
            end=trim(p,g,fuel,h,V,vz)
            max_force=max(max_force,abs(start['lift_residual_N']),abs(mid['lift_residual_N']),abs(end['lift_residual_N']))
            max_moment=max(max_moment,abs(start['moment_residual_Nm']),abs(mid['moment_residual_Nm']),abs(end['moment_residual_Nm']))
            min_power_margin=min(min_power_margin,start['power_available_kw']-start['power_required_kw'],mid['power_available_kw']-mid['power_required_kw'],end['power_available_kw']-end['power_required_kw'])
            trace.append(dict(phase=phase,time_s=t,distance_km=distance/1000,altitude_m=h,fuel_kg=fuel,**end))
    return dict(burn_kg=fuel0-fuel,end_fuel_kg=fuel,duration_h=t/3600,total_distance_km=distance/1000,
                trace=trace,lift_residual_N=max_force,moment_residual_Nm=max_moment,
                min_power_margin_kw=min_power_margin)


def beam_response(y,forces,EI):
    """Point forces at element midpoints; root fixed, tip free. Positive upward."""
    mid=[.5*(y[i]+y[i+1]) for i in range(len(forces))]
    moments=[sum(f*(s-pos) for f,s in zip(forces,mid) if s>=pos) for pos in y]
    curvature=[m/ei for m,ei in zip(moments,EI)]
    theta=[0.]; displacement=[0.]
    for i in range(len(y)-1):
        dx=y[i+1]-y[i]
        theta.append(theta[-1]+dx*(curvature[i]+curvature[i+1])/2)
        displacement.append(displacement[-1]+dx*(theta[-1]+theta[-2])/2)
    return moments,displacement


def structure(p,g,fuel,n=100):
    # A single illustrative symmetric pull-up at sea level, 60 m/s, not an envelope.
    tc=trim(p,g,fuel,0.,60.,load_factor=p['load_factor'])
    h=p['span_m']/2; root=.2*h
    ys=[h*i/n for i in range(n+1)]; mids=[.5*(ys[i]+ys[i+1]) for i in range(n)]
    def chord(y):
        st=g['stations']
        for a,b in zip(st,st[1:]):
            if y<=b['y']+1e-12:
                return a['c']+(b['c']-a['c'])*(y-a['y'])/(b['y']-a['y'])
        return st[-1]['c']
    weights=[math.sqrt(max(0.,1-(y/h)**2)) for y in mids]
    aero=[.5*tc['lift_N']*w/sum(weights) for w in weights]
    structure_weights=[chord(y) for y in mids]
    inertia=[-.5*p['load_factor']*g['structural_mass_kg']*G*w/sum(structure_weights) for w in structure_weights]
    nodal=[0.]*(n+1)
    for i,f in enumerate(aero):
        nodal[i]+=.5*f; nodal[i+1]+=.5*f
    force_error=abs(sum(nodal)-sum(aero))
    moment_error=abs(sum(f*y for f,y in zip(nodal,ys))-sum(f*y for f,y in zip(aero,mids)))
    # Bending is only solved on the outer wing, with mass relief from structure.
    first=round(.2*n); yo=ys[first:]; net=[a+b for a,b in zip(aero[first:],inertia[first:])]
    t=p['thickness_mm']/1000
    inertia_I=[]; halfdepth=[]
    for y in yo:
        width=.35*chord(y); depth=.14*chord(y)
        I=(width*depth**3-(width-2*t)*(depth-2*t)**3)/12
        inertia_I.append(I); halfdepth.append(depth/2)
    moments,displacements=beam_response(yo,net,[70e9*I for I in inertia_I])
    stress=[abs(m*z/I)/1e6 for m,z,I in zip(moments,halfdepth,inertia_I)]
    return dict(load_case='demo_symmetric_pull_up',load_factor=p['load_factor'],load_speed_ms=60.,
                lift_N=tc['lift_N'],max_stress_MPa=max(stress),tip_deflection_m=displacements[-1],
                root_bending_Nm=moments[0],root_shear_N=sum(net),outer_length_m=h-root,
                map_force_error_N=force_error,map_span_moment_error_Nm=moment_error,
                lift_integral_error_N=abs(2*sum(aero)-tc['lift_N']),
                pressure_field='prescribed elliptic lift, not CFD pressure',
                trace=[dict(y_m=y,moment_Nm=m,deflection_m=u,stress_MPa=s) for y,m,u,s in zip(yo,moments,displacements,stress)],
                trim=tc)


def analyze(supplied=None):
    supplied=supplied or {}
    if not isinstance(supplied,dict): raise ValueError('Inputs must be an object')
    if set(supplied)-set(DEFAULTS): raise ValueError('Unknown input field')
    p={**DEFAULTS,**supplied}
    for k,v in p.items():
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not BOUNDS[k][0]<=v<=BOUNDS[k][1]:
            raise ValueError(f'{k} outside demo input bounds {BOUNDS[k]}')
    g=geometry(p)
    design_keys=['root_chord_m','span_m','thickness_mm','power_kw','tank_offset_mac','tank_fraction']
    x={k:p[k] for k in design_keys}
    digest=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()[:12]
    result=dict(inputs=p,design=x,design_hash=digest,assumptions=ASSUMPTIONS,geometry=g,
                model='illustrative-bwb-flow-v1',engineering_validation='not_performed',
                formal_feasibility='unknown',objective='pending_teacher_decision',iterations=[],
                coverage=dict(M01='demo_input',M02='pending_teacher_decision',M03='demo_initial_guess',
                              M04='computed_proxy',M05='computed',M06='illustrative_aero',M07='prescribed_load',
                              M08='outer_wing_bending_only',M09='illustrative_ledger',M10='three_phases_only',
                              M11='demo_limits_only',M12='not_performed',C01='not_converged',O01='manual_design_change'))
    # Start with capacity as a conservative fuel guess. Retry a lighter admissible
    # seed for trim/power failures; all attempted seeds remain visible in history.
    cap=g['fuel_capacity_kg']; fuel=cap
    phase_result=None
    try:
        for k in range(60):
            try:
                phase_result=mission(p,g,fuel)
            except Unsupported as exc:
                if k==0 and exc.code!='fuel_exhausted':
                    result['iterations'].append(dict(iteration=0,fuel_guess_kg=fuel,status=exc.code,residual_kg=None))
                    fuel=cap*.5
                    continue
                raise
            needed=1.15*phase_result['burn_kg']+1.5
            residual=fuel-needed
            result['iterations'].append(dict(iteration=k+1,fuel_guess_kg=fuel,required_fuel_kg=needed,
                                              residual_kg=residual,takeoff_mass_kg=ledger(p,g,fuel)['mass_kg'],status='evaluated'))
            if needed>cap: raise Unsupported('fuel_capacity_exceeded',dict(required_fuel_kg=needed,capacity_kg=cap))
            if abs(residual)<=1e-4:
                break
            fuel=.45*fuel+.55*needed
        else: raise Unsupported('coupling_not_converged',dict(last_residual_kg=residual))
        # Reevaluate with the final state, not the relaxed update delta.
        phase_result=mission(p,g,fuel)
        residual=fuel-(1.15*phase_result['burn_kg']+1.5)
        if abs(residual)>1e-4: raise Unsupported('coupling_not_converged')
        result.update(status='demo_converged',fuel_loaded_kg=fuel,fuel_residual_kg=residual,
                      mission=phase_result,mass=ledger(p,g,fuel),structure=structure(p,g,fuel))
        s=result['structure']
        checks=[dict(name='油箱容量',value=fuel,limit=cap,unit='kg',pass_=fuel<=cap),
                dict(name='载荷空间代理',value=g['payload_volume_m3'],limit=.12,unit='m³',pass_=g['payload_volume_m3']>=.12),
                dict(name='外翼弯曲应力',value=s['max_stress_MPa'],limit=120.,unit='MPa',pass_=s['max_stress_MPa']<=120),
                dict(name='外翼端挠度',value=abs(s['tip_deflection_m']),limit=.03*s['outer_length_m'],unit='m',pass_=abs(s['tip_deflection_m'])<=.03*s['outer_length_m']),
                dict(name='最小功率余量',value=phase_result['min_power_margin_kw'],limit=0.,unit='kW',pass_=phase_result['min_power_margin_kw']>=0)]
        result['checks']=checks
        result['demo_constraints_satisfied']=all(c['pass_'] for c in checks)
        result['coverage']['C01']='demo_converged'
    except Unsupported as exc:
        result.update(status='unsupported',failure=exc.code,failure_details=exc.details,
                      demo_constraints_satisfied=None,checks=[])
        if phase_result: result['last_valid_mission_attempt']=phase_result
    return result


if __name__=='__main__':
    r=analyze()
    print(json.dumps({k:v for k,v in r.items() if k not in ['mission','structure','last_valid_mission_attempt']},indent=2,ensure_ascii=True))
