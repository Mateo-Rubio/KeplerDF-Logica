import json
import pathlib
import shutil
import subprocess
import sys
import time
import yaml

## TODO translate pls
INTERVALO_S = 60
DATOS = pathlib.Path("../KeplerDF-Datos")
MAQUINA = f"maquina_{input('Letra de la máquina (escribe solo la letra, ej. a): ').strip().lower()}"

if not (DATOS / MAQUINA).is_dir():
    raise FileNotFoundError(f"No existe la carpeta {DATOS / MAQUINA}. Revisa la letra ingresada.")

tasks_k = yaml.safe_load(open("config.yaml", encoding="utf-8"))["simulation"]["tasks_k"]

subprocess.run(["git", "fetch", "origin"], cwd=DATOS)
atras = int(subprocess.run(["git", "rev-list", "--count", "HEAD..@{u}"], cwd=DATOS,
                           capture_output=True, text=True).stdout.strip())
if atras > 0:
    if input(f"KeplerDF-Datos está {atras} commits atrás de origin. ¿Quieres continuar? [s/n]: ").strip().lower() != "s":
        sys.exit(0)



def completo(d: pathlib.Path) -> bool:
    try:
        with (d / "ollama_prompts_combined.json").open("r", encoding="utf-8") as f:
            total = json.load(f).get("scenario_metrics", {}).get("total_tasks_evaluated", 0)
        with (d / "physics_passes_report.json").open("r", encoding="utf-8") as f:
            json.load(f)
        return total >= tasks_k
    except (json.JSONDecodeError, OSError):
        return False

hechos = set()
while True:
    nuevos = [d for d in pathlib.Path("data").glob("*/*/temp_*/rep_*/scenario_*")
              if d not in hechos and completo(d)]
    destinos = [pathlib.Path(MAQUINA) / d for d in nuevos]
    for d, dest in zip(nuevos, destinos):
        shutil.copytree(d, DATOS / dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("physics_passes_report.json"))
    for i in range(0, len(destinos), 100):
        subprocess.run(["git", "add", *map(str, destinos[i:i + 100])], cwd=DATOS)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=DATOS).returncode:
        subprocess.run(["git", "commit", "-m", f"{MAQUINA}: {len(nuevos)} escenarios completos"], cwd=DATOS)
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=DATOS)
    hechos.update(nuevos)
    time.sleep(INTERVALO_S)