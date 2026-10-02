import json
import pathlib
from datetime import datetime, timezone
from src.core.datatypes import CollectedContext
from .pass_calculator import compute_target_passes, compute_infrastructure_passes

__all__ = ["physics_engine_main"]


def _export_physics_report(all_infra_passes: list, all_target_passes: list, context: CollectedContext, simulation_start_utc: datetime, simulation_end_utc: datetime, output_path: str) -> None:
    path = pathlib.Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    report_data = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "simulation_start_utc": simulation_start_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "simulation_end_utc": simulation_end_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "total_satellites": len(context.satellites),
            "total_ground_stations": len(context.ground_stations),
            "total_targets": len(context.targets),
            "compiled_infrastructure_passes": len(all_infra_passes),
            "compiled_target_passes": len(all_target_passes)
        },
        "infrastructure_passes": all_infra_passes,
        "target_passes": all_target_passes
    }
    
    with path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)


def physics_engine_main(
    context: CollectedContext,
    bands_config: dict,
    sensor_constraints: dict,
    simulation_start_utc: datetime,
    simulation_end_utc: datetime,
    output_path: str = "data/physics_passes_report.json",
    step_seconds: int = 20,
    min_duration: int = 5,
    max_duration: int = 30
) -> None:
    t0_naive = simulation_start_utc.astimezone(timezone.utc).replace(tzinfo=None)
    tf_naive = simulation_end_utc.astimezone(timezone.utc).replace(tzinfo=None)

    all_infra_passes = []
    for gs in context.ground_stations:
        for sat in context.satellites:
            passes = compute_infrastructure_passes(
                satellite=sat,
                ground_station=gs,
                start_dt_utc=t0_naive,
                end_dt_utc=tf_naive,
                bands_config=bands_config,
                step_seconds=step_seconds
            )
            all_infra_passes.extend(passes)

    all_target_passes = []
    for task in context.targets:
        for sat in context.satellites:
            sat_band = getattr(sat, "assigned_band", getattr(sat, "band", None))
            band_info = bands_config.get(sat_band, {}) if sat_band else {}
            dynamic_min_el_deg = float(band_info.get("min_elevation_deg", 10.0))

            passes = compute_target_passes(
                satellite=sat,
                task=task,
                simulation_start_utc=t0_naive,
                min_el_deg=dynamic_min_el_deg,
                sensor_constraints=sensor_constraints,
                step_seconds=step_seconds,
                min_duration=min_duration,
                max_duration=max_duration
            )
            all_target_passes.extend(passes)

            if passes:
                task.assigned_lvlh_pitch_deg = passes[-1]["lvlh_end_pitch_deg"]
                task.assigned_lvlh_roll_deg = passes[-1]["lvlh_end_roll_deg"]

    _export_physics_report(
        all_infra_passes=all_infra_passes,
        all_target_passes=all_target_passes,
        context=context,
        simulation_start_utc=t0_naive,
        simulation_end_utc=tf_naive,
        output_path=output_path
    )