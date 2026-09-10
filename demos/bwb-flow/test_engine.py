"""Meaningful numerical checks for the illustrative model, not aircraft validation.

Run: python -m unittest -v test_engine.py
"""
import math
import unittest
from engine import analyze,atmosphere,beam_response,geometry,ledger,mission,DEFAULTS


class EngineeringDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=analyze()

    def test_standard_atmosphere_sea_level(self):
        state=atmosphere(0)
        self.assertEqual(state['temperature_K'],288.15)
        self.assertEqual(state['pressure_Pa'],101325)
        self.assertAlmostEqual(state['rho'],1.225,places=6)

    def test_uniform_beam_matches_analytic_solution_and_refines(self):
        length=3.; EI=4e6; load=1200.
        exact=load*length**4/(8*EI)
        errors=[]
        for count in (20,40,80):
            y=[length*i/count for i in range(count+1)]
            moment,disp=beam_response(y,[load*length/count]*count,[EI]*(count+1))
            self.assertAlmostEqual(moment[0],load*length**2/2,places=7)
            self.assertLess(abs(disp[-1]-exact),1e-10)
            # Uniform-load tip error cancels for this quadrature. Use a
            # triangular load to measure nonzero discretization error.
            triangular=[load*((y[i]+y[i+1])/2)*(length/count) for i in range(count)]
            _,variable_disp=beam_response(y,triangular,[EI]*(count+1))
            triangular_exact=11*load*length**5/(120*EI)
            errors.append(abs(variable_disp[-1]-triangular_exact))
        self.assertLess(errors[2],errors[1])
        self.assertLess(errors[1],errors[0])
        self.assertLess(errors[-1]/triangular_exact,2e-4)

    def test_mass_and_cg_follow_fuel_centroid(self):
        p={**DEFAULTS,'tank_offset_mac':.45};g=geometry(p)
        empty=ledger(p,g,0);full=ledger(p,g,40)
        self.assertAlmostEqual(full['mass_kg']-empty['mass_kg'],40)
        tank_x=g['xac_m']+.45*g['mac_m']
        exact=(empty['mass_kg']*empty['cg_x_m']+40*tank_x)/(empty['mass_kg']+40)
        self.assertAlmostEqual(full['cg_x_m'],exact,places=12)
        self.assertGreater(full['cg_x_m'],empty['cg_x_m'])

    def test_convergence_and_conservation_are_recomputed(self):
        r=self.base
        self.assertEqual(r['status'],'demo_converged')
        self.assertEqual(r['engineering_validation'],'not_performed')
        self.assertEqual(r['formal_feasibility'],'unknown')
        m=mission(r['inputs'],r['geometry'],r['fuel_loaded_kg'])
        residual=r['fuel_loaded_kg']-(1.15*m['burn_kg']+1.5)
        self.assertLess(abs(residual),1e-4)
        self.assertLess(m['lift_residual_N'],1e-8)
        self.assertLess(m['moment_residual_Nm'],1e-8)
        self.assertLess(r['structure']['map_force_error_N'],1e-8)
        self.assertLess(r['structure']['map_span_moment_error_Nm'],1e-8)
        self.assertLess(r['structure']['lift_integral_error_N'],1e-8)

    def test_mission_step_refinement_and_fuel_monotonicity(self):
        r=self.base;burn=[]
        for count in (18,36,72):
            m=mission(r['inputs'],r['geometry'],r['fuel_loaded_kg'],steps=count)
            burn.append(m['burn_kg'])
            fuel=[r['fuel_loaded_kg']]+[p['fuel_kg'] for p in m['trace']]
            self.assertTrue(all(a>b for a,b in zip(fuel,fuel[1:])))
        self.assertLess(abs(burn[2]-burn[1]),abs(burn[1]-burn[0]))
        self.assertLess(abs(burn[2]-burn[1]),.005) # Numerical demo budget, 5 g.

    def test_manual_design_change_exposes_mass_strength_tradeoff(self):
        thinner=analyze({'thickness_mm':.8})
        self.assertEqual(thinner['status'],'demo_converged')
        self.assertLess(thinner['mass']['mass_kg'],self.base['mass']['mass_kg'])
        self.assertGreater(thinner['structure']['max_stress_MPa'],self.base['structure']['max_stress_MPa'])
        self.assertNotEqual(thinner['design_hash'],self.base['design_hash'])

    def test_failed_candidates_never_become_valid_metrics(self):
        for p,reason in [({'power_kw':12},'insufficient_power'),
                         ({'cruise_km':1800,'tank_fraction':.015},'fuel_exhausted')]:
            r=analyze(p)
            self.assertEqual(r['status'],'unsupported')
            self.assertEqual(r['failure'],reason)
            self.assertIsNone(r['demo_constraints_satisfied'])
            self.assertEqual(r['checks'],[])
            self.assertNotIn('fuel_loaded_kg',r)

    def test_invalid_inputs_are_rejected(self):
        for p in ({'span_m':0},{'span_m':math.nan},{'power_kw':True},{'new_field':1}):
            with self.assertRaises(ValueError):analyze(p)


if __name__=='__main__':unittest.main()
