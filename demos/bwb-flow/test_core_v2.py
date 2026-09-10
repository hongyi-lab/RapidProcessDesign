"""Regression and analytic numerical evidence; not independent aircraft validation.

The compressed source fixture is exactly the pre-fix engine, SHA-256 checked
before execution. It is retained only to test the reported historical fuel root
after the current geometry/section model changes, not used by the application.
"""
import base64
import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import math
import types
import unittest
from unittest.mock import patch
import zlib

from configuration import ModelConfig, SolverConfig, config_schema
from engine import (DEFAULTS, Unsupported, analyze, build_load_case, geometry, ledger,
                    mission, solve_fuel, solve_structure, structure, thinwall_section)


class CoreV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline=analyze()

    def test_exact_original_counterexample_with_preserved_source(self):
        source=zlib.decompress(base64.b85decode(LEGACY_ENGINE_B85))
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         'c693b1e7462f081518b937ae9fa426803c70c1cd2167cb84eed0c6a6415ac751')
        legacy=types.ModuleType('legacy_bwb_v1')
        exec(compile(source,'legacy_engine_snapshot.py','exec'),legacy.__dict__)
        p={**legacy.DEFAULTS,'tank_offset_mac':.45};g=legacy.geometry(p)
        failure=legacy.analyze({'tank_offset_mac':.45})
        self.assertEqual(failure['failure'],'static_stability_not_supported')
        def evaluate_legacy(fuel):
            try: return legacy.mission(p,g,fuel)
            except legacy.Unsupported as exc: raise Unsupported(exc.code,exc.details) from exc
        result=solve_fuel(evaluate_legacy,g['fuel_capacity_kg'],
                          solver_config=SolverConfig(fuel_tolerance_kg=1e-9))
        self.assertEqual(result['status'],'converged')
        self.assertAlmostEqual(result['fuel_kg'],26.270214692232862,places=7)
        self.assertLess(abs(result['residual_kg']),1e-9)
        self.assertGreater(result['diagnostics']['failure_counts']['static_stability_not_supported'],0)
        physical=legacy.structure(p,g,result['fuel_kg'])
        self.assertAlmostEqual(physical['max_stress_MPa'],8.549423942578947,places=7)

    def test_new_geometry_root_independent_of_seed_and_matches_direct_bisection(self):
        p={**DEFAULTS,'tank_offset_mac':.45};g=geometry(p)
        roots=[]
        for seed in (.05,.5,1.):
            result=solve_fuel(lambda f:mission(p,g,f),g['fuel_capacity_kg'],
                solver_config=SolverConfig(fuel_tolerance_kg=1e-8,fuel_seed_fraction=seed))
            self.assertEqual(result['status'],'converged')
            roots.append(result['fuel_kg'])
            self.assertEqual(result['attempts'][0]['search_phase'],'seed')
            self.assertTrue(all(r['residual_kg'] is None for r in result['attempts'] if r['status']!='evaluated'))
        lo,hi=25.,28.
        for _ in range(40):
            middle=(lo+hi)/2
            residual=middle-(1.15*mission(p,g,middle)['burn_kg']+1.5)
            if residual>0: hi=middle
            else: lo=middle
        self.assertEqual(roots[0],roots[1]);self.assertEqual(roots[1],roots[2])
        self.assertAlmostEqual(roots[0],(lo+hi)/2,places=7)

    def test_failed_samples_are_not_signed_and_interior_discontinuity_aborts(self):
        cfg=ModelConfig(reserve_fraction_of_burn=0.,unusable_fuel_kg=0.)
        def interrupted(fuel):
            if .32<fuel<.33: raise Unsupported('branch_hole',{'phase':'cruise','time_s':10.})
            return {'burn_kg':.325}
        r=solve_fuel(interrupted,1.,cfg,SolverConfig(fuel_scan_points=21))
        self.assertEqual(r['failure'],'fuel_branch_interrupted')
        self.assertIsNone(r['attempts'][-1]['residual_kg'])
        self.assertEqual(r['attempts'][-1]['failure_details']['phase'],'cruise')
        def everywhere_invalid(fuel): raise Unsupported('no_reference_model',{'phase':'climb','time_s':0.})
        r=solve_fuel(everywhere_invalid,1.,cfg,SolverConfig(fuel_scan_points=21))
        self.assertEqual(r['status'],'unknown')
        self.assertEqual(r['failure'],'fuel_bracket_not_found')
        self.assertTrue(all(x['residual_kg'] is None for x in r['attempts']))
        self.assertEqual(r['diagnostics']['valid_evaluations'],0)

    def test_falsey_inputs_config_and_unknown_keys_are_rejected(self):
        for value in ([],0,'',False):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): analyze(value)
                with self.assertRaises(ValueError): ModelConfig.from_dict(value)
        for cfg in ({'cd0':False},{'cd0':float('nan')},{'unused_field':1},{'material_E_Pa':-1}):
            with self.assertRaises(ValueError): analyze(model_config=cfg)
        with self.assertRaises(ValueError): SolverConfig(mission_steps=36.)
        with self.assertRaises(ValueError): SolverConfig(fuel_scan_points=0)

    def test_json_integer_and_float_configuration_values_have_same_identity(self):
        def integerize(values):
            return {key:int(value) if isinstance(value,float) and value.is_integer() else value
                    for key,value in values.items()}
        model=integerize(ModelConfig().snapshot())
        solver=integerize(SolverConfig().snapshot())
        inputs=integerize(DEFAULTS)
        self.assertEqual(ModelConfig.from_dict(model).snapshot(),ModelConfig().snapshot())
        self.assertEqual(SolverConfig.from_dict(solver).snapshot(),SolverConfig().snapshot())
        canonical=analyze(inputs,model_config=model,solver_config=solver)
        self.assertEqual(self.baseline['config_hash'],canonical['config_hash'])
        self.assertEqual(self.baseline['analysis_hash'],canonical['analysis_hash'])
        self.assertEqual(self.baseline['comparability_hash'],canonical['comparability_hash'])

    def test_configuration_snapshot_immutable_and_parameters_consumed(self):
        cfg=ModelConfig()
        with self.assertRaises(FrozenInstanceError): cfg.cd0=.044
        source={'cd0':.044};drag=analyze(model_config=source)
        source['cd0']=.01
        self.assertEqual(drag['configuration']['model']['cd0'],.044)
        self.assertGreater(drag['fuel_loaded_kg'],self.baseline['fuel_loaded_kg'])
        reserve=analyze(model_config={'reserve_fraction_of_burn':.3})
        self.assertGreater(reserve['fuel_loaded_kg'],self.baseline['fuel_loaded_kg'])
        efficiency=analyze(model_config={'propeller_efficiency':.7})
        self.assertGreater(efficiency['fuel_loaded_kg'],self.baseline['fuel_loaded_kg'])
        flexible=analyze(model_config={'material_E_Pa':35e9})
        self.assertAlmostEqual(flexible['structure']['tip_deflection_m'],2*self.baseline['structure']['tip_deflection_m'],places=10)
        dense=analyze(model_config={'material_density_kg_m3':3000.})
        self.assertGreater(dense['geometry']['structural_mass_kg'],self.baseline['geometry']['structural_mass_kg'])
        limiting=analyze(model_config={'demo_stress_limit_MPa':5.})
        self.assertEqual(limiting['evaluation_status'],'infeasible')
        self.assertFalse(next(c for c in limiting['constraints'] if c['id']=='stress')['pass_'])
        schema=config_schema();schema['model_defaults']['cd0']=9.
        self.assertEqual(config_schema()['model_defaults']['cd0'],.022)

    def test_design_mission_state_and_analysis_identities_are_separate(self):
        base=self.baseline
        loaded=analyze({'payload_kg':120.})
        self.assertEqual(base['design_hash'],loaded['design_hash'])
        self.assertNotEqual(base['analysis_hash'],loaded['analysis_hash'])
        self.assertNotEqual(base['comparability_hash'],loaded['comparability_hash'])
        self.assertAlmostEqual(base['mass']['hardware_mass_kg'],loaded['mass']['hardware_mass_kg'],places=10)
        resized=analyze({'rated_payload_kg':120.})
        self.assertNotEqual(base['design_hash'],resized['design_hash'])
        self.assertAlmostEqual(resized['mass']['hardware_mass_kg']-base['mass']['hardware_mass_kg'],6.,places=10)
        repeated=analyze()
        self.assertEqual(base['analysis_hash'],repeated['analysis_hash'])
        self.assertNotEqual(base['analysis_id'],repeated['analysis_id'])
        changed_design=analyze({'thickness_mm':1.4})
        self.assertEqual(base['comparability_hash'],changed_design['comparability_hash'])

    def test_thinwall_rectangle_matches_analytic_line_integral_and_translation(self):
        width,height,t=2.,.5,.003
        points=[(0.,-height/2),(width,-height/2),(width,height/2),(0.,height/2)]
        section=thinwall_section(points,t)
        self.assertAlmostEqual(section['area_m2'],2*(width+height)*t,places=14)
        self.assertAlmostEqual(section['I_m4'],t*width*height**2/2+t*height**3/6,places=14)
        self.assertAlmostEqual(section['centroid_x_m'],width/2,places=14)
        moved=thinwall_section([(x+3,z+4) for x,z in points],t)
        self.assertAlmostEqual(moved['I_m4'],section['I_m4'],places=13)
        self.assertAlmostEqual(moved['centroid_z_m'],4.,places=14)

    def test_actual_load_object_mass_and_root_equilibrium_are_consumed(self):
        r=self.baseline;p=r['inputs'];g=r['geometry']
        case=build_load_case(p,g,r['fuel_loaded_kg'])
        answer=solve_structure(g,case)
        self.assertEqual(case['hash'],answer['consumed_load_case_hash'])
        self.assertEqual(case['id'],answer['load_case_id'])
        self.assertLess(case['structural_mass_error_kg'],1e-10)
        for component in g['structural_components']:
            self.assertAlmostEqual(component['mass_kg'],case['component_mass_reconstruction_kg'][component['id']],places=10)
        self.assertAlmostEqual(answer['root_reaction_N']+sum(case['forces_N']),0.,places=10)
        moment=sum(f*(y-case['root_y_m']) for f,y in zip(case['forces_N'],case['positions_m']))
        self.assertAlmostEqual(answer['root_bending_Nm'],moment,places=10)
        self.assertAlmostEqual(answer['root_reaction_moment_Nm']+moment,0.,places=10)
        tampered=copy.deepcopy(case);tampered['forces_N'][0]+=1.
        with self.assertRaises(ValueError):solve_structure(g,tampered)

    def test_actual_geometry_sections_follow_surface_and_mesh_refines(self):
        r=self.baseline;g=r['geometry'];tc=g['section_layout']['thickness_ratio']
        for section in g['sections']:
            c=section['chord_m'];le=section['leading_edge_x_m']
            for corner in section['corners']:
                u=(corner['x_m']-le)/c
                expected=.5*tc*c*4*u*(1-u)*(1-.5*(2*u-1)**2)
                self.assertAlmostEqual(abs(corner['z_m']),expected,places=10)
        results=[structure(r['inputs'],g,r['fuel_loaded_kg'],n=n) for n in (40,80,160,320)]
        values=[a['tip_deflection_m'] for a in results]
        self.assertLess(abs(values[3]-values[2]),abs(values[2]-values[1]))
        self.assertLess(abs(values[2]-values[1]),abs(values[1]-values[0]))
        self.assertLess(abs(values[3]-values[2])/abs(values[3]),.005)

    def test_structure_failure_preserves_successful_mission_and_dynamic_condition(self):
        partial=analyze({'load_factor':5.,'power_kw':50.})
        self.assertEqual(partial['status'],'unsupported')
        self.assertEqual(partial['numeric_convergence'],'converged')
        self.assertIn('mission',partial);self.assertIn('fuel_loaded_kg',partial)
        self.assertNotIn('structure',partial)
        self.assertEqual(partial['failure_details']['module'],'M07')
        self.assertEqual(partial['evaluation_status'],'unknown')
        failed_power=next(c for c in partial['constraints'] if c['id']=='maneuver_power')
        self.assertFalse(failed_power['pass_'])
        self.assertEqual(failed_power['source']['module'],'M07')
        instantaneous=analyze({'load_factor':5.,'power_kw':50.},model_config={'maneuver_type':'instantaneous'})
        self.assertIn('structure',instantaneous)
        trim=instantaneous['structure']['trim']
        self.assertFalse(trim['power_enforced'])
        self.assertLess(trim['longitudinal_acceleration_ms2'],0.)
        self.assertEqual(instantaneous['constraint_applicability']['maneuver_power']['status'],'not_applicable')
        self.assertFalse(any(c['id']=='maneuver_power' for c in instantaneous['constraints']))

    def test_signed_constraints_and_module_records_trace_actual_execution(self):
        r=self.baseline
        for check in r['constraints']:
            self.assertEqual(check['pass_'],check['g']<=0)
            self.assertAlmostEqual(check['margin'],-check['g'])
            self.assertEqual(check['source']['analysis_hash'],r['analysis_hash'])
            self.assertIn('condition_id',check['source']);self.assertIn('state_id',check['source'])
        records={rec['id']:rec for rec in r['module_records']}
        self.assertEqual(records['M03']['status'],'skipped')
        self.assertEqual(records['M12']['status'],'not_performed')
        self.assertEqual(records['M07']['outputs']['load_case_hash'],records['M08']['outputs']['consumed_load_case_hash'])
        self.assertEqual(r['model_metadata']['id'],'illustrative-bwb-v2')
        self.assertEqual(r['formal_feasibility'],'unknown')
        self.assertIsNone(r['uncertainty_metadata_or_null'])
        maneuver_power=next(c for c in r['constraints'] if c['id']=='maneuver_power')
        self.assertEqual(maneuver_power['source']['load_case_hash'],r['structure']['consumed_load_case_hash'])

    def test_capability_gate_prevents_partial_model_becoming_full_analysis(self):
        metadata=copy.deepcopy(self.baseline['model_metadata'])
        metadata['supported_quantities']=['CL','CD']
        with patch('engine.model_metadata',return_value=metadata):
            result=analyze()
        self.assertEqual(result['failure'],'missing_model_capability')
        self.assertEqual(result['iterations'],[])
        self.assertIn('Cm',result['model_capability_check']['missing_quantities'])
        self.assertNotIn('mission',result)


LEGACY_ENGINE_B85 = 'c-pNyX^-5<b>I6}Fxn41x|)5=p;<{KU{||d2$8f4ODlgEGzd0X-Axah<dW=}ZY>rFki)SPAFzW2_6BwWJ3)c~>%>lCcn>d--(qRxPyP#e?^P99eT<|87ND78)vH&pUcI|&u3fu!H;Y9f;73+7D;8-o5oK75bZw>iMK3R7QCe?)?M+K$vm_IuOtM*T3PS+9$g`>j;JoxZod>z~)v!q7_sTpHRrQvrl38XYiy|-U$_lgC%5v-e-A7g&)*-VlL^7MhKwer^zAPi*TW_SP73E?&O`-&-sX90*O%@5xF9j`Vg;lj&6m<ei`_`kmsDu@TX|zm3>Lb7`udOgCqcWV<)_IsFF%9~iJ2~tp$zXexHHDRDB43EQT=(z1LlajP%wX2qDv>y5J+YR>O{+-iXl_zwB^9huiQcmCJJ+sV>rBghVFkf-SuaZw1Zvl?X`n>X)#<3dd05SX$NKZ@Ri5egBCO|~&N~*jUiVK1$HzyVx8DBB8}HwH^boq@B&wY<&+8zX!zO|SKk!G)s){g!_K81WRy|LmvkZ72EEaqSqaADOUlFd;JdA_08NWWjDN(shDiNG5_|d@Zs0txqjfx*0LGKQpFs+k%84Fl>s3sQqg(!ow3w}bMb(oz6`E*)|I#`4eht9)YJOni@!w7i<Fhkf85jcgeyyPSQ$nCuO?)wkk+Rp-K<R3EY&>y)CC!AxSS;Ir$-QtJiA290xx;t00#2F57?(qO8x14c~sQYAK_BRZ2Mkg?Oe6)+%V3LCv4h9lK!zpJtLd3Fnn_*7RA008vKRnt&yva4k9}E$21b`dNbB2H&=yE%6Jbd{6{r4W-efL4b#wZ<dl%FUKK<Dc)D1fFijJbaR$f5;|6541HglREv$9o8{bCB>4AU84f{OgDyMpPqMDz7fWG!6v!Pxc}x%DfP13bVDMMQiR~KVjCSnnrLyz_U5f2hs(a0){9|gSUhCLJ(!~`d*9;7#O!Isn>{Oall8{2Y4RSrPv<9Gv12{O-}%}4uy#<Qg9y@9*z(Xjm2V`3OW!q-kgs=IM|DFS%s5S1m}6WTnGdFIx3SAN|5Qu9J_+`rTAc(lpv3Ko<a&cB9#KNMS0#L0yzsN%MuU{_aj_piaO#EsK(I8qlBGJ0(1^2_#@hS6@fi$`g+5w*oV#_P<v9Eb1a$Hju;Aa#W6@xoaD<au7Kq;e%b?d2Q?ZqOQhl)wze^d=L7%8Zl}|UQg9vC`&qRt(AtXFd3zNJ@+9t!j-+x5Mm)*j^a7_6=@hn{#{!A0!z8WvgFF)o7XKlLFCnO@z(B<|rlE`b@S}Ft5){O7{bnTuMgnnp@TP@$k|(jVX4XorRSIw`8BAO_&iXVNci~5OICee%$a7ZI?!m9IOFk{JlFTZ@Y$lvkWX{U%4PA|1`#YylsOPXnptm@+rTMhSeUKOUG|j9%CfGIZ>=X~p9}PU1=^q{8uels1U;>F?==za|zYgTD;mC_5)N7UzZ?xMDQ>&7mvZ3(?x$$}~C}=3cGK6l3MWQ@Ahq>g>5o0POSrR{S0M6q=hyocQGEf8*Pv`UyNIw9n9UXx{w5ON~KP-?SVApAHIPN;@O7awc1DDY)`(Se&YJg=+!mM&=1s6DrIMA$)y!P-UFCdVp<ajhnV7FWy;U;<o3~kRFb=wc!0?@9}1|YY8uzk`8iV*M|L<%j~f7r0R7Bgf5u@mfUyo_oq2XVW|A;8K+Sb{aoA{jx66<7%f|0ZkeAw(vXW;ApMavKA`<+Vve%hVM_c&iD30#B2c{&64NHFj-ns()zAl&f^PwZ*CavB|4d*gf=|w!=i{_D8^12S8R6Y;W)ny7YF4Rcb-StXgV=89IPYfR7%~aCMe|mY^Ylss7-|d+603`V+<Jw^twp)+Ap+P+C;|3o(%qX(dpA;Q&gJWWcvbEHJ`lB;yg7EU-rq+7f;%oP~+vIbdp*qjg|8|MkNiQ9B*p7_&9~lDh+6g=frLin|(D_eA2Jl{xHBx(dSYAAA1rP|A)x;8KVd06ddt&gscD`pxz+E>Y|=BNTh=8Hh}aMv;ip`--2^=bEos#G{C<_-Z9B8g#(t3MK7HQh-!2rC+IV$9sa)QiQ=`#2;du5P>s+pN!;c!B^M}!39O+w33_~rVmuB|8N(dxo32#<~K8WgoDQC)#10{p20wxQ)Fz{j^pPp9`ec{U|}Rf7XkyhIPxHXVe0IcB?LZr-UuMOb}=>5K|uNgvNOo?w7lSuZfi#p){DF<=AsnNT&evdJ~}ypfTHIQ2FKtSIx?mM9fF*Q4+q185xA>IeF^1yp7Ty0g6Hd?Mex(3S;~r)b2t|@(}a1XjNB69k?X@_(US<TA4r5l^oR1RJA_#N(Cs^qRBK1<YOyHLF<`>>$NUk~>tR5t+YAYT{|r`KELq6O15_WBHN@73o=KQyOe*3Txc7q17@m^i4M-iv^s`f&#LylyXf9+^I*1%nzzj`-QiBY<9k(w(`@ypx|Jm<9|I6p!|Ka72KIvb6`T6C?-|t`k?9<===C7WA`QvBb`KRCg<F9}J`8RE*PYMw4o<A%I=f}gS3(+Vzw8-5R1!LJ~-}#s4Uw-`blW#u%>7TclhbLW77M;CdqyRyoMteATIoiu#es=lUPg;bdqb^1Uh_p$<8cKU;U0;gw`4?Y2|Mst1lvm+`WnPNw>BpZw{p3f_|La%JzxTznAOE*xGO*X+fZp#*5Pk83r{DbcvtRuB@{|9#{KlU`qeX#2p_!%)Wt;VZ4MH-<%9mFa$A}?BSyAUm1~Eia*ousbF=ji!9(=4&#`ezYBixQ&XhO*jM6&>Cjb_+F35G1Q>qN625ZOnwYRIigj}B&&MWYF9&K|S#Cm7kAN$Sv7Dv~bvw(i^nGs8D54MBduLC?b)V$^vKdwlFYmhLQEER=?ZRgyX9Px_DLgnQgr(MuO5hu)FlU6fZ2AyB+b`MtjLfd|T@yos&+YRE@&Mv=5LHv+?hkqdTb*d4ua+&>}Yh9`m*<PsC~3OB8YQtg|TOr(`vtcE;Fd;aJqwns1mNqW!0Ey)A2$5=LSy(m=~4KUD)dlN6}H2D*E5D)bt61NXfH!aHDxf4=fk02r%qKS9z!O?d^j}UYx9zn~I`&23DMrtgUW8FPO-MJ^38&g4`d*>eX^c~I3y&M611zv+N8f(U7IOChA<3+KILFVPMsyRY*_ntJ0hH=tO>U?&=<y`MEoX+(V4`V)c=I4;cQ92Aj8zvBlHbk*M^hYCkQs*J0i=<C7WyN%qmWKwo`$~4ZOeL*5!?ahI0o(7~V|U)-QOxcvf;;c<JNLIuPnt~Y-~qqKaL>@dUrcTVzGQ=?F(B##7D>CgYoonW8zbP2?VBH@r2*E0v3yctX~r|K^$(5*gT2&(drjgcxTgo(r+DXH?;cy^3o0r!P>XG_)_Z!p4B07JMf-#?Y)tZom}o<1PS{yMT15py29|w*al;4ftAd-Bsim`z-HRna-VdWWe@x$@wkpY#5&@@oe2b&#z>pRjdwh!zM^r!WjRtzSl^Yx%4UE*Q43kQ1)H!T4#6iBSfuACva+R!-*bK2XBp7FRYw$vZy6%$+5m$l0q$fbRyBgtbQ*d60JAn^fXb(sNx3EeMY@f0{zRh1uG$k5Q0KX<lih(n*JZQ$vMU+3p4&}-gNmW6T()gwUt7=hH{NPw|{x$18kk_b8CXmQcq0H*5S~0|gGx$(E^Q}kWnE;nhN1DP92(>9keDLlgYmtNIi&!RTu)9h?K<L<n&}Ie7g|3lN0LB(z&JN)>3~g1WLAKavyDIG{DBGBDhH8Y?uD=h-Ud(K;i&*V%he}D}(N!e&AOcXO8{jL&M}wPI4RHeaqy!Etiv)el=_g1Ue4pwFX%$d1&9NoT20_7+QglFp%UP0fFj8TSvNg5crglO6W$}`nO-A7fhDeg_ttf%WX&4S7h6SiP$(Eu4h{4||fIf*uGqP17p+Q4c6?WV+DBM1oB?~K7^AL<U%IJqSQD@(fwA*z8d17VXs6TQyu)b#9PvRoSLQ0~FKUiB6Aks^^{X&xf;T3R7fl-wKMN*%gzkv`AqOAG8h;DOXz!$5!F`Z=(Vzs#TX!@zW=`d98V{pQl{Rd_UU~Z{5mSOX*r11R7p54$6IE=!Kms9_TAiEoHQ(kw002F_aalA*GcZpiJRgW%zycKJ<0k8{u+dwC>_*IV4)GVj@V&SB6)LCwMa@1uUB~D#225avd+g)0zvR+$$nv3s-2pj8PJxnC*9p09gEenEHY`c>wYIfr!h%z?D3{OZFF}`AwF|s*@=-xZU7}=PzB}HgAb)lOAQ<6L`<xh$qubCDpy!X^?s(v!#a%Rr-wGhdV=K)T4x59!qOd4p=BTxVgHs)%(8O(Vt<Hb6!@xty(I(F}n$s^EDwjEuzg1aZCG$d;W>Gnxu=)2vg)7*&&7l;_L-%2=ZMhjN#?Yqj-U%PhgJu<O!0Ie?gcwD!!z7^ziIRt>yWF=x|)k#5hMc;ZauaY`B7uK@42+P>V#|GM*onpDmybs!U{Ug_ObxDD?3n2wo3Z|Y@^@_Zb^QNrQ1y;2ISi?oLR^8?e6f_WOt*Tbb@|-GY{B+S52|+BFNHij~9I|4pvNHimCSKN%^(xX(7Q*@F{mteU)_8-}I?Z^+*XmjT_TF?8YAxXOL6<r4%5xer>6)PZP&WlFW`m+uRocD=VT)e1MlB+x0eb7^d?hcsJSSQcoN<utCX#%^0`omfg_We~k{;Ng1XSw<-isxXRV>rAw=7VQDiK0>c@8M7<AJs4s~d$7FTS8RFO(avqb;Kkj^uc&6a(>@@u>~SoNrtXN<roRNELY3AWU;F>1W#~mvx8k7$dQ`Qj$uyH0nxcM^-Z>A;=)A?!&PgH?6g-Ys#Af!}C&Ii%qn^L8e>PbP2K(WUX)U$*H}z$K9dm4M#URyO-#6a3Msg0OU;QcTax0Kt48My4!ao9{t_fLQs*M&@>uS51l|on&PqY<inn`?$2Gk(Nh;4xDVu*oEeHTC*IYOa+}~Sy^B67ufi(lUEn;`Gd8Y&u$<j2uerK!r6dz&oq%RyxV9|^-W4Tf?;S<U&SC~tJ7aReERVyKwB930G45`so7c9;1miSmA_@`~0jD?hH{K^wk46NpLzE>*H3bboBmufTDv=^e*D#1%pi^(HOyXJ#7R_dBFr>XJAP^~<%u3%0zh=EDWOA2OR-UD6tIE@J$POV6$7@)~$3;mOEqL8h&t(K&iZlTgpa*3Q@6>f`Qi2|on7KQke;Gu8>zso^(ZCH*woHH}4ZD+VwLsc56jNudzqMuNFSzwoQ-ZsYctIo@rqfsy^<1Z6jX<sQ_Mk43xSrGfmKHp$G2$$`V^n<&_+9SM43A(u@1Q5Ydn2y~?W11V_72?saMWgJnl^2*@45zwjTy%eZKC(t=8A8*@tgrS*(ts)^6t_W@8TAl<=T5z;1_TmLr?EX|1J<Gj+G~T!tQRn!iF-|U{WVwhEAk^5yoe>e0ij8e}J|>SQhpREjQbJXtQJPRN2rpEes<f^~edIH=&u5pDsj*h55#bqOz8GXz_NJpf@BFsRR^oNgkXI#*Bulxd=<3fz(sfE+dr)z~|5EImVei1ltpwg+*YfIAAco7>-JRW$1Rhyn@=#50xvY4Prdjk=GcFp2@B~mq5)W;xrLy%<ZDB35hgKiW<B(PM2Q#&R5=QX4qE+w(3?K*s<0@EbfJE9LACv$5!cE^95VBK^+M6Ub$B@_g$o8!~g=)-1%l<x_%-YOl!eN#pZLUrcXDFM^CD_nLtn@1NjC6!@apWVSXH@OYt@`-m&jy#j>uf1%y8kUt>IzPreS@wVNtnCF%wb7-jg<k7f5Fd_OzO@(a{oKy1<RC|m{q(DU?MNM<zBj~d%{#?GlO<R`UQRF1n*8Zx$Z&L(-Dy14bN4WBayM2k@s%54BBAV{hyz5@f8re8jIJv|$PrrhG^w|Ltz9B&3LI~$$aAD(?=samgmF)g<&E56o;4X%&W{%72H71l9c>zxS<?lxb7F&zrBO=rQ{OA)qnsmZqAgUI(c{KK;w1rQ>6j2t!=mfVk%nE;=s-c0+|JRBVzJNRbWkC%(0a#pO$%UY89s9Xxy7a6{%b6nS-i<O-3xTiOUBW-1?Wm?Ot8DdPu3ntg)E7b^aJuc@m<GndI-qAA6G(Ov7ps<R|Z8LoDO)e(%Y`%9sw3+diK4{;ka~mttg(!g`3#=0DKKy_IuufAER*5WPb9*Tz+h$TjU@fpa%IMZ2jOK7Gv4|3^U)u~Mt<>*r_NaW6pTqb}NCw>>43z^SR@v<SVDuv7_Xh_JJfy8a>1+uCV()#+Y5coCIOI0oAA|jmgQCn=YeaU`cH-ypCPxFb$k>0~w6pY*^c5C7;kNWP7=SfS3d1x+`TEvU@@5)Fh64_Qj}LZal~~Pq*>Xe8NBP$bdY$2D=g99M%dwB1IhHf*dl&l_VYZ}~%p{@F9J4072{j*Lu}OxJ`dtt{CkwGyjc<Qt3W=GYMMvUWUq#^sfE1&02t>n}?l>l?P$(;i9!NFO4fIL9t!bE~;H;{fR+y%cf8rw=e7T0O7`rY)(Bkui(4a!klL`WowTxeZFwEk%A1~PuQc}4X`r2!cKq)Hv7#X0J>l+(s-&vbH9uKziy$#^TIh%O5FLXAmWrAJ?n<ZT2CiL!N1s8C}`G89206_17|A=oFd~fWP5J}6a-72L$-l)+v1AHKBZghA}^$Zi@WySTftf_7R06AxO@3NZPo`1A=eCL8=!`p21;sqdh{h>dEywTwAsjaGim~U?_qp6hl0}?~$|H+oK?r<MtnnI{9Hp*3Arl)((r{Sk=vszx?HBaNVU#*yz$?AY?eeV+6TStPi5s`Kq&g1HvgGOCYFcI8l@{eJz*r)k65Zb$oVqB|t<lf>#(L3A~(Mc)7vz_}8?jJ&)4UI0o|K2)2kyc{wHlln9Q5BfjE!!s3ov<=Wvj(#b!e0Z6rP(MA9VXEbJE^DRf;I2OA%_lEpt8#%MqqkN(cWggq8ZqfQs-q7?sl%??rmc3|A8kPG{8!}+=ruui5!W+LOOeNdm?TWfco}|?-eSb7{Sdg(hG?l`DRU7g6~!`jRUK=W>f=a6z(8$h|V@2JIV)hPe1wf@4oR}x{Y57xfybrD93CGVFkB==d3^-qv2a5;ji#Y@bX_j{oUXF=Wjpz>E-wSLgSyc?**Gjx0pZEiukuPa>d2}{8BHuf5vSDe#xuApZ)FSm!CiV{O8X;{>9Tz|K{npKGsB3Xfn*qyP<&oz(|sS-HL=g@c2e#@G9$H{@c%={q;XQ{q&#p;#BlHwYT$oOm7tz1_vGhZ06=bq2i1t>S{c<u0rvWN2q`QCr|(VyHCIMlgsaX<F{Y@&=87EHQaMm)9|n1-r3hQov$$YHXpd-&bBv_5^ImSZ0w9{wZxziuXKV6TofdCprT_A;gS=f<NyikIc7x9F$tHuyO@f@?eVD%At7McR{PE?#wq)4$TBk?zNo0KjU!Y?p#Sa(2UPni`*HQ|DH35?-^Uw<(maeC&F0A+P+AlyvlOUM6Zl|GG3#ckr_)LBkGN2Tf`D^72rwoM0u_OkTvstv@((FkZ6=hElb)MNf2osx3iM=NpIIn4mCShz>&9M4`A00FKYHRLNdKrv6jo7^$h6h%{4ZwAstf'

if __name__=='__main__':
    unittest.main()
