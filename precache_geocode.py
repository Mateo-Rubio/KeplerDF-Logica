import shutil
import run_all_models as r
from src.modules.prompt_factory import generator

def _solo_geocodificar(targets, **kwargs):
    for t in targets:
        generator.build_task_fields(t, kwargs["simulation_t0"])

r.prompt_factory_main = _solo_geocodificar
cfg = r.load_config("config.yaml")
sim = cfg["simulation"]
for idx in range(1, sim["num_scenarios"] + 1):
    r.run_single_scenario("precache", idx, cfg, {}, sim["seed"] + idx, "zero_shot", 0.0, 1)
shutil.rmtree("data/precache")