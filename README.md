# KeplerDF-Logica

Este repositorio contiene el código que genera las solicitudes en lenguaje natural para tareas de observación de la Tierra con distintos modelos de lenguaje,
estrategias de prompting y temperaturas. Los datos generados no se guardan aquí: se publican en el repositorio KeplerDF-Datos.

## Contenido

| Archivo / carpeta | Descripción |
|---|---|
| `src/` | Módulos de KDF: Data Collector, Physics Engine y Prompt Factory. Se mantienen sin modificaciones respecto a la implementación original. |
| `run_all_models.py` | Punto de entrada para la generación de datos. |
| `auto_commit.py` | Publica automáticamente en KeplerDF-Datos los escenarios completos. |
| `precache_geocode.py` | Precarga la caché de geocodificación de los 34 escenarios. |
| `config.yaml` | Configuración de la simulación (escenarios, satélites, sensores, tareas). |
| `data/cache/celestrak_weather.json` | TLE congelados de la constelación `weather` (epoch del 6 de julio de 2026). |
| `data/cache/geocode_cache.json` | Caché de geocodificación: 510 ubicaciones, 50 de ellas en el mar. |
| `data/ground_station.csv` | Estaciones terrenas. |
| `requirements.txt` | Dependencias de Python. |

## Reproducibilidad

`run_all_models.py` aplica, sin modificar `src/`, las siguientes decisiones para que todas las máquinas, temperaturas y repeticiones usen exactamente los mismos escenarios:

- **TLE congelados.** La descarga en vivo desde CelesTrak se reemplaza por la caché `data/cache/celestrak_weather.json`. Sin esto, cada ejecución usaría TLE distintos y cambiarían los satélites y el *ground truth*.
- **Caché de geocodificación.** Las consultas a Nominatim se reemplazan por `data/cache/geocode_cache.json`. Esto elimina la pausa de 1,2 s por tarea y garantiza que la información de ubicación del prompt sea idéntica en todas las condiciones.
- **Semillas fijas.** Cada escenario usa la semilla `seed + idx` de `config.yaml` (2027 a 2060), con 34 escenarios de 15 tareas.
- **Fecha de referencia fija.** `GENERATION_NOW_UTC = 2026-01-15 12:00 UTC`.
- **Physics Engine desactivado.** El reporte físico no lo usa el análisis, que se basa en `ollama_prompts_combined.json`, por lo que su cálculo está comentado para acelerar la generación.
- **Categorías semánticas.** El archivo `semantic_categories.json` no existe, así que se usan los valores por defecto del Prompt Factory, igual que en todas las corridas.

## Requisitos

1. Python 3 y Git.
2. [Ollama](https://ollama.com) con los siguientes modelos instalados:
   ```
   ollama pull gemma2:27b
   ollama pull llama3.1:8b
   ollama pull phi3.5:3.8b
   ollama pull phi4:14b
   ollama pull qwen2:7b
   ollama pull mxbai-embed-large
   ```
   `mxbai-embed-large` lo usa el validador semántico. Todas las máquinas deben tener la misma versión de Ollama y los mismos modelos; esto se verifica con la columna **ID** de `ollama list`.
3. Dependencias de Python:
   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

## Generación de datos

```
.venv\Scripts\python run_all_models.py --temperatures 0.8,1.0 --reps 2
```

| Argumento | Descripción | Por defecto |
|---|---|---|
| `--temperatures` | Temperaturas separadas por coma. | `ollama_temperature` de `config.yaml` |
| `--reps` | Repeticiones por temperatura. | 10 |
| `--models` | Modelos separados por coma. | Los 5 modelos listados arriba |

El script recorre las 4 estrategias (`zero_shot`, `few_shot`, `chain_of_thought`, `chaining`) en el orden temperatura → repetición → estrategia → modelo → escenario, y escribe en:

```
data/{modelo}/{estrategia}/temp_{T}/rep_{r}/scenario_{idx}/
```

Es reanudable: un escenario se considera completo cuando su `ollama_prompts_combined.json` registra las 15 tareas. Si la ejecución se interrumpe, al relanzar el mismo comando se omiten los escenarios completos y se repite el que quedó a medias. Si una llamada a Ollama falla, el escenario se marca como `[FAIL]` y se repite en la siguiente ejecución.

## Publicación de datos (`auto_commit.py`)

Requiere clonar **KeplerDF-Datos** junto a este repositorio, en la misma carpeta:

```
carpeta/
├── KeplerDF-Logica/
└── KeplerDF-Datos/
```

Se ejecuta desde la raíz de KeplerDF-Logica, en paralelo a `run_all_models.py`:

```
.venv\Scripts\python auto_commit.py
```

Al iniciar, pide:

1. **La letra de la máquina** (por ejemplo `a`). Debe existir la carpeta `maquina_{letra}` en KeplerDF-Datos.
2. **Un token de GitHub** *fine-grained* con permiso *Contents: Read and write* solo sobre KeplerDF-Datos. El token se mantiene en memoria durante la ejecución, no se guarda en disco y se borra del portapapeles al recibirlo.

Cada 5 a 7 minutos (intervalo aleatorio para que las máquinas no se sincronicen), copia los escenarios completos a `KeplerDF-Datos/maquina_{letra}/{modelo}/...` sin el reporte físico, hace commit firmado como `maquina_{letra}` y sube los cambios. Si otra máquina sube primero, reintenta hasta 10 veces con pausas aleatorias.
