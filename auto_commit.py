import json
import pathlib
import shutil
import subprocess
import sys
import time
import yaml
import base64
import getpass
import os

## TODO translate pls
INTERVALO_S = 120
DATOS = pathlib.Path("../KeplerDF-Datos")
MAQUINA = f"maquina_{input('Letra de la máquina (escribe solo la letra, ej. a): ').strip().lower()}"

if not (DATOS / MAQUINA).is_dir():
    raise FileNotFoundError(f"No existe la carpeta {DATOS / MAQUINA}. Revisa la letra ingresada.")

TOKEN_LEN = 93
token = getpass.getpass("Token de GitHub (no se muestra al escribir): ").strip()
if input(f"Se recibieron {len(token)} caracteres (el token debe tener {TOKEN_LEN}). ¿Continuar? [s/n]: ").strip().lower() != "s":
    sys.exit(0)
subprocess.run(["powershell", "-NoProfile", "-Command",
                "[Windows.ApplicationModel.DataTransfer.Clipboard, Windows.ApplicationModel.DataTransfer, ContentType=WindowsRuntime] | Out-Null; "
                "[Windows.ApplicationModel.DataTransfer.Clipboard]::ClearHistory() | Out-Null"])
cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
GIT_ENV = {**os.environ, "GIT_CONFIG_COUNT": "2",
           "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": "",
           "GIT_CONFIG_KEY_1": "http.https://github.com/.extraheader",
           "GIT_CONFIG_VALUE_1": f"AUTHORIZATION: basic {cred}"}
if subprocess.run(["git", "ls-remote", "origin"], cwd=DATOS, env=GIT_ENV, capture_output=True).returncode:
    raise PermissionError("El token no es válido o no tiene acceso a KeplerDF-Datos.")

tasks_k = yaml.safe_load(open("config.yaml", encoding="utf-8"))["simulation"]["tasks_k"]

subprocess.run(["git", "fetch", "origin"], cwd=DATOS, env=GIT_ENV)
atras = int(subprocess.run(["git", "rev-list", "--count", "HEAD..@{u}"], cwd=DATOS,
                           capture_output=True, text=True).stdout.strip())
if atras > 0:
    if input(f"KeplerDF-Datos está {atras} commits atrás de origin. ¿Quieres continuar? [s/n]: ").strip().lower() != "s":
        sys.exit(0)



def completo(d: pathlib.Path) -> bool:
    try:
        with (d / "ollama_prompts_combined.json").open("r", encoding="utf-8") as f:
            total = json.load(f).get("scenario_metrics", {}).get("total_tasks_evaluated", 0)
        return total >= tasks_k
    except (json.JSONDecodeError, OSError):
        return False

hechos = set()
while True:
    nuevos = [d for d in pathlib.Path("data").glob("*/*/temp_*/rep_*/scenario_*")
              if d not in hechos and completo(d)]
    destinos = [pathlib.Path(MAQUINA) / d.relative_to("data") for d in nuevos]
    for d, dest in zip(nuevos, destinos):
        shutil.copytree(d, DATOS / dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("physics_passes_report.json"))
    for i in range(0, len(destinos), 100):
        subprocess.run(["git", "add", *map(str, destinos[i:i + 100])], cwd=DATOS)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=DATOS).returncode:
        subprocess.run(["git", "-c", f"user.name={MAQUINA}", "-c", f"user.email={MAQUINA}@keplerdf.local", "commit", "-m", f"{MAQUINA}: {len(nuevos)} escenarios completos"], cwd=DATOS)
    subprocess.run(["git", "pull", "--rebase"], cwd=DATOS, env=GIT_ENV)
    subprocess.run(["git", "push", "origin", "HEAD"], cwd=DATOS, env=GIT_ENV)
    hechos.update(nuevos)
    time.sleep(INTERVALO_S)
