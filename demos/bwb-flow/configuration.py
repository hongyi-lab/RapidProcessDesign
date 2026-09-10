"""Immutable runtime configuration and controlled presentation metadata.

These are demonstrator assumptions, not validated aircraft design values.
"""
from dataclasses import asdict, dataclass, fields
from types import MappingProxyType
import hashlib
import json
import math


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class ConfigMixin:
    def snapshot(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, supplied=None):
        if supplied is None:
            return cls()
        if isinstance(supplied, cls):
            return supplied
        if not isinstance(supplied, dict):
            raise ValueError(f'{cls.__name__} must be an object')
        if set(supplied) - {f.name for f in fields(cls)}:
            raise ValueError(f'Unknown {cls.__name__} field')
        return cls(**supplied)

    def __post_init__(self):
        schema = MODEL_FIELDS if isinstance(self, ModelConfig) else SOLVER_FIELDS
        for key, spec in schema.items():
            value = getattr(self, key)
            if 'choices' in spec:
                if value not in spec['choices']:
                    raise ValueError(f'{key}: invalid choice')
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not spec['min'] <= value <= spec['max']:
                raise ValueError(f'{key} outside configured bounds')
            if spec.get('integer') and not isinstance(value, int):
                raise ValueError(f'{key} must be an integer')
            # JSON clients may emit 80 where Python defaults contain 80.0.
            # Canonicalize numeric physical fields before snapshot/hashing;
            # frozen instances remain immutable after construction.
            if 'choices' not in spec and not spec.get('integer'):
                object.__setattr__(self, key, float(value))
        if isinstance(self, ModelConfig):
            if self.alpha_min_deg >= self.alpha_max_deg or self.elevon_min_deg >= self.elevon_max_deg:
                raise ValueError('Invalid trim bounds')


@dataclass(frozen=True)
class ModelConfig(ConfigMixin):
    cl0: float = .2
    cl_delta_per_rad: float = .35
    cm0: float = .015
    cm_alpha_per_rad: float = -.35
    cm_delta_per_rad: float = -.75
    cd0: float = .022
    elevon_drag_factor: float = .025
    oswald_e: float = .8
    aerodynamic_sweep_deg: float = 32.
    propeller_efficiency: float = .78
    bsfc_kg_kwh: float = .30
    installed_power_fraction: float = .85
    material_E_Pa: float = 70e9
    material_density_kg_m3: float = 2700.
    fuel_density_kg_m3: float = 800.
    demo_stress_limit_MPa: float = 120.
    demo_deflection_limit_fraction: float = .03
    usable_volume_fraction: float = .70
    usable_tank_fraction: float = .95
    payload_space_fraction: float = .35
    required_payload_volume_m3: float = .12
    reserve_fraction_of_burn: float = .15
    unusable_fuel_kg: float = 1.5
    climb_rate_ms: float = 2.
    descent_rate_ms: float = -1.
    climb_speed_cap_ms: float = 42.
    descent_speed_cap_ms: float = 45.
    design_load_speed_ms: float = 60.
    design_load_altitude_m: float = 0.
    maneuver_type: str = 'sustained'
    alpha_min_deg: float = -6.
    alpha_max_deg: float = 12.
    elevon_min_deg: float = -20.
    elevon_max_deg: float = 20.
    thickness_ratio: float = .14
    connection_mass_kg: float = 8.
    propulsion_base_mass_kg: float = 18.
    propulsion_specific_power_kw_kg: float = 2.5
    systems_base_mass_kg: float = 25.
    systems_rated_payload_fraction: float = .12
    landing_gear_mass_kg: float = 15.


@dataclass(frozen=True)
class SolverConfig(ConfigMixin):
    mission_steps: int = 36
    load_strips: int = 100
    fuel_scan_points: int = 101
    fuel_tolerance_kg: float = 1e-5
    fuel_max_iterations: int = 60
    fuel_seed_fraction: float = 1.


def spec(label, unit, lo, hi, step, group, **extra):
    return dict(label=label, unit=unit, min=lo, max=hi, step=step, group=group, **extra)


INPUT_FIELDS = {
    'root_chord_m': spec('根弦', 'm', 2.4, 4.2, .1, 'design'),
    'span_m': spec('翼展', 'm', 6., 14., .2, 'design'),
    'thickness_mm': spec('蒙皮及翼盒补强层壁厚', 'mm', .3, 3., .1, 'design'),
    'rated_payload_kg': spec('设计额定载荷', 'kg', 10., 160., 5., 'design'),
    'power_kw': spec('安装轴功率', 'kW', 12., 100., 2., 'design'),
    'tank_offset_mac': spec('油箱相对参考点位置', 'MAC', -.25, .45, .01, 'design'),
    'tank_fraction': spec('自由容积油箱占比', '1', .015, .25, .005, 'design'),
    'payload_kg': spec('本次任务装载', 'kg', 10., 160., 5., 'mission'),
    'cruise_km': spec('巡航段距离', 'km', 50., 1800., 50., 'mission'),
    'cruise_speed_ms': spec('巡航真空速', 'm/s', 28., 65., 1., 'mission'),
    'altitude_m': spec('巡航高度', 'm', 0., 3000., 100., 'mission'),
    'load_factor': spec('设计载荷因子', 'g', 1., 5., .25, 'load_case'),
}

MODEL_FIELDS = {
    'cl0': spec('零迎角升力系数', '1', -.2, .5, .01, 'aero'),
    'cl_delta_per_rad': spec('升力舵效', 'rad⁻¹', .01, 1., .01, 'aero'),
    'cm0': spec('参考点零迎角力矩系数', '1', -.1, .1, .005, 'aero'),
    'cm_alpha_per_rad': spec('参考点固定舵力矩斜率', 'rad⁻¹', -2., -.01, .01, 'aero'),
    'cm_delta_per_rad': spec('力矩舵效', 'rad⁻¹', -2., -.05, .05, 'aero'),
    'cd0': spec('零升阻力系数', '1', .005, .1, .001, 'aero'),
    'elevon_drag_factor': spec('舵偏二次阻力系数', 'rad⁻²', 0., .2, .005, 'aero'),
    'oswald_e': spec('诱导阻力效率', '1', .4, 1., .01, 'aero'),
    'aerodynamic_sweep_deg': spec('升力斜率等效后掠角', '°', 0., 60., 1., 'aero'),
    'propeller_efficiency': spec('螺旋桨效率', '1', .3, .95, .01, 'propulsion'),
    'bsfc_kg_kwh': spec('轴功率耗油率', 'kg/kWh', .1, .8, .01, 'propulsion'),
    'installed_power_fraction': spec('安装功率利用比例', '1', .3, 1., .01, 'propulsion'),
    'material_E_Pa': spec('弹性模量', 'Pa', 1e9, 250e9, 1e9, 'structure'),
    'material_density_kg_m3': spec('结构材料密度', 'kg/m³', 500., 9000., 100., 'structure'),
    'fuel_density_kg_m3': spec('燃油密度', 'kg/m³', 500., 1000., 10., 'mission'),
    'demo_stress_limit_MPa': spec('演示弯曲应力上限', 'MPa', 1., 500., 5., 'constraints'),
    'demo_deflection_limit_fraction': spec('挠度/外翼长上限', '1', .001, .1, .001, 'constraints'),
    'usable_volume_fraction': spec('内部可用容积比例', '1', .3, .9, .01, 'geometry'),
    'usable_tank_fraction': spec('油箱有效装填比例', '1', .5, 1., .01, 'geometry'),
    'payload_space_fraction': spec('载荷空间占比', '1', .1, .6, .01, 'geometry'),
    'required_payload_volume_m3': spec('任务载荷体积需求', 'm³', .01, 2., .01, 'constraints'),
    'reserve_fraction_of_burn': spec('备份油/任务耗油', '1', 0., .5, .01, 'mission'),
    'unusable_fuel_kg': spec('不可用燃油', 'kg', 0., 10., .1, 'mission'),
    'climb_rate_ms': spec('爬升率', 'm/s', .5, 5., .1, 'mission'),
    'descent_rate_ms': spec('下降率', 'm/s', -3., -.1, .1, 'mission'),
    'climb_speed_cap_ms': spec('爬升速度上限', 'm/s', 28., 60., 1., 'mission'),
    'descent_speed_cap_ms': spec('下降速度上限', 'm/s', 28., 60., 1., 'mission'),
    'design_load_speed_ms': spec('载荷工况真空速', 'm/s', 28., 90., 1., 'load_case'),
    'design_load_altitude_m': spec('载荷工况高度', 'm', 0., 3000., 100., 'load_case'),
    'maneuver_type': dict(label='机动动力学条件', unit='', group='load_case', choices=['sustained', 'instantaneous']),
    'alpha_min_deg': spec('最小迎角', '°', -20., 0., 1., 'aero'),
    'alpha_max_deg': spec('最大迎角', '°', 1., 25., 1., 'aero'),
    'elevon_min_deg': spec('最小舵偏', '°', -40., 0., 1., 'aero'),
    'elevon_max_deg': spec('最大舵偏', '°', 1., 40., 1., 'aero'),
    'thickness_ratio': spec('最大外形厚弦比', '1', .08, .22, .01, 'geometry'),
    'connection_mass_kg': spec('中央连接质量项', 'kg', 0., 40., 1., 'mass'),
    'propulsion_base_mass_kg': spec('推进固定质量项', 'kg', 0., 50., 1., 'mass'),
    'propulsion_specific_power_kw_kg': spec('推进比功率', 'kW/kg', .5, 10., .1, 'mass'),
    'systems_base_mass_kg': spec('系统固定质量', 'kg', 0., 80., 1., 'mass'),
    'systems_rated_payload_fraction': spec('系统/额定载荷质量比例', '1', 0., .5, .01, 'mass'),
    'landing_gear_mass_kg': spec('固定起落架质量', 'kg', 0., 50., 1., 'mass'),
}

SOLVER_FIELDS = {
    'mission_steps': spec('每航段积分步数', 'steps', 6, 288, 6, 'numerics', integer=True),
    'load_strips': spec('全半翼载荷条带数', 'strips', 20, 400, 20, 'numerics', integer=True),
    'fuel_scan_points': spec('燃油区间扫描点数', 'points', 21, 501, 20, 'numerics', integer=True),
    'fuel_tolerance_kg': spec('燃油独立残差容差', 'kg', 1e-9, .001, .00001, 'numerics'),
    'fuel_max_iterations': spec('括区二分最大步数', 'steps', 10, 100, 10, 'numerics', integer=True),
    'fuel_seed_fraction': spec('记录的初猜/容量', '1', 0., 1., .1, 'numerics'),
}

DEFAULTS = dict(root_chord_m=3.2, span_m=8., thickness_mm=1.2, rated_payload_kg=70.,
                payload_kg=70., cruise_km=500., cruise_speed_ms=45., altitude_m=1500.,
                power_kw=80., tank_offset_mac=.04, tank_fraction=.12, load_factor=2.5)
BOUNDS = {k:(s['min'],s['max']) for k,s in INPUT_FIELDS.items()}

MODULE_METADATA = {
    'M01': dict(name='任务与固定硬件', formula='r ≠ x ≠ y', method='严格 schema；额定载荷决定系统质量，本次装载只改变状态', limitation='默认任务待老师确认'),
    'M02': dict(name='问题定义', formula='g(x,y;r) ≤ 0', method='分析返回真实数值；目标由外层显式配置', limitation='演示约束不是适航要求'),
    'M03': dict(name='候选来源', formula='x = supplied candidate', method='Analyze 模式明确跳过任务尺寸初猜', limitation='不把手填尺寸称为自动 sizing'),
    'M04': dict(name='统一几何与截面', formula='A_wall = Σ tℓ; I = Σ t∫(z−zc)² ds', method='同一翼型截面生成蒙皮、翼盒、质量和 EI', limitation='薄壁；补强层与蒙皮分层，不含屈曲和中央舱分析'),
    'M05': dict(name='大气与工况', formula='q = ρV²/2', method='ISA 对流层；速度为 TAS', limitation='0–3000 m 演示域'),
    'M06': dict(name='气动与配平', formula='CL = cl0 + aα + bδ; Cm_CG = cm0 + cα + dδ + ΔxCL', method='固定控制导数；2×2 线性求解；显式模型能力', limitation='低阶示例系数，没有 CFD 或失速验证'),
    'M07': dict(name='实际载荷对象', formula='Fi = Laero,i − n g mstructure,i', method='中点集中力；椭圆升力与真实部件质量卸载', limitation='单工况；没有压力场、扭矩和非结构质量在外翼的分布'),
    'M08': dict(name='外翼弯曲', formula='κ = M/(EI); σ = M(z−zc)/I', method='根部固支；直接消费 M07 中点力与 hash', limitation='只算外翼弯曲，不含剪切变形、扭转、屈曲、中央舱'),
    'M09': dict(name='质量与重心', formula='m = Σmi; xCG = Σmixi/Σmi', method='硬件质量在候选内固定；任务燃油改变质量和 CG', limitation='安装位置仍为显式演示假设'),
    'M10': dict(name='任务与燃油闭合', formula='R = fuel − [(1+reserve) burn + unusable]', method='有效相邻扫描括区 + 二分；任务中点积分', limitation='无起飞、着陆、等待；未括区只说明证据不足'),
    'M11': dict(name='逐项约束', formula='g ≤ 0; margin = −g', method='每项值和边界保留模块、工况和状态来源', limitation='数值收敛与约束可行性分别报告'),
    'M12': dict(name='独立证据', formula='prediction ≠ independently verified aircraft', method='仅保存本次证据状态', limitation='本核心没有独立 CFD/FEA'),
}


def config_schema():
    # Return a fresh serializable copy; no mutable exported configuration reference.
    return json.loads(json.dumps(dict(version='bwb-schema-v2', inputs=INPUT_FIELDS,
        model_config=MODEL_FIELDS, solver_config=SOLVER_FIELDS, modules=MODULE_METADATA,
        defaults=DEFAULTS, model_defaults=ModelConfig().snapshot(), solver_defaults=SolverConfig().snapshot())))


def validate_inputs(supplied=None):
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict) or set(supplied)-set(DEFAULTS):
        raise ValueError('Inputs must be an object containing known fields')
    p = {**DEFAULTS, **supplied}
    for key, value in p.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not BOUNDS[key][0] <= value <= BOUNDS[key][1]:
            raise ValueError(f'{key} outside demo input bounds {BOUNDS[key]}')
        p[key] = float(value)
    return p
