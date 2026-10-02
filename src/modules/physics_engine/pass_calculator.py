from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from skyfield.api import EarthSatellite, wgs84, load

__all__ = ["compute_infrastructure_passes", "compute_target_passes"]

_GLOBAL_TS = load.timescale()


def _calculate_subsatellite_point(sat_object: EarthSatellite, t_skyfield) -> Tuple[float, float]:
    geocentric = sat_object.at(t_skyfield)
    subpoint = wgs84.subpoint(geocentric)
    return float(subpoint.latitude.degrees), float(subpoint.longitude.degrees)


def _calculate_lvlh_attitude(sat_object: EarthSatellite, t_skyfield, c_lat: float, c_lon: float) -> Tuple[float, float]:
    geocentric = sat_object.at(t_skyfield)
    r_sat = geocentric.position.km
    v_sat = geocentric.velocity.km_per_s

    target_topo = wgs84.latlon(c_lat, c_lon, elevation_m=0.0)
    r_target = target_topo.at(t_skyfield).position.km

    rho_inercial = r_target - r_sat

    z_lvlh = -r_sat / np.linalg.norm(r_sat)
    h_orbit = np.cross(r_sat, v_sat)
    y_lvlh = -h_orbit / np.linalg.norm(h_orbit)
    x_lvlh = np.cross(y_lvlh, z_lvlh)

    R_inercial_to_lvlh = np.vstack([x_lvlh, y_lvlh, z_lvlh])
    rho_lvlh = R_inercial_to_lvlh.dot(rho_inercial)
    rx, ry, rz = rho_lvlh

    pitch_deg = float(np.degrees(np.arctan2(rx, np.sqrt(ry**2 + rz**2))))
    roll_deg = float(np.degrees(np.arctan2(ry, np.sqrt(rx**2 + rz**2))))

    return pitch_deg, roll_deg


def _calculate_geodetic_centroid_and_radius(task: Any) -> Tuple[float, float, float]:
    if task.task_type == "point":
        return task.coordinates[0][0], task.coordinates[0][1], 0.0
    
    lats = [pt[0] for pt in task.coordinates[:-1]]
    lons = [pt[1] for pt in task.coordinates[:-1]]
    
    c_lat = float(np.mean(lats))
    c_lon = float(np.mean(lons))
    
    max_radius_deg = 0.0
    for lat, lon in task.coordinates[:-1]:
        distance = np.sqrt((lat - c_lat)**2 + (lon - c_lon)**2)
        if distance > max_radius_deg:
            max_radius_deg = float(distance)
            
    return c_lat, c_lon, max_radius_deg


def _vectorized_pass_finder(
    sat_object: EarthSatellite,
    topo_target,
    start_dt: datetime,
    end_dt: datetime,
    min_el_deg: float,
    c_lat: float,
    c_lon: float,
    step_seconds: int = 20
) -> List[Dict[str, Any]]:
    t0 = _GLOBAL_TS.utc(start_dt.year, start_dt.month, start_dt.day, start_dt.hour, start_dt.minute, start_dt.second)
    tf = _GLOBAL_TS.utc(end_dt.year, end_dt.month, end_dt.day, end_dt.hour, end_dt.minute, end_dt.second)
    
    t_events, y_events = sat_object.find_events(topo_target, t0, tf, altitude_degrees=min_el_deg)
    
    discovered_passes = []
    current_pass = {}
    
    for t_ev, y_ev in zip(t_events, y_events):
        if y_ev == 0:
            current_pass["t_aos_obj"] = t_ev
            current_pass["aos_dt"] = t_ev.utc_datetime().replace(tzinfo=None)
        elif y_ev == 1:
            current_pass["t_max_obj"] = t_ev
            current_pass["tmax_dt"] = t_ev.utc_datetime().replace(tzinfo=None)
            
            difference = sat_object - topo_target
            alt, az, dist = difference.at(t_ev).altaz()
            current_pass["max_el_deg"] = float(alt.degrees)
            current_pass["range_tmax_km"] = float(dist.km)  
        elif y_ev == 2 and "t_aos_obj" in current_pass:
            current_pass["t_los_obj"] = t_ev
            current_pass["los_dt"] = t_ev.utc_datetime().replace(tzinfo=None)
            
            difference = sat_object - topo_target
            _, _, dist_aos = difference.at(current_pass["t_aos_obj"]).altaz()
            _, _, dist_los = difference.at(t_ev).altaz()
            
            current_pass["range_aos_km"] = float(dist_aos.km)
            current_pass["range_los_km"] = float(dist_los.km)
            
            duration_s = max(0, int((current_pass["los_dt"] - current_pass["aos_dt"]).total_seconds()))
            current_pass["duration_s"] = duration_s
            
            if duration_s < 1200:
                if "max_el_deg" not in current_pass:
                    current_pass["max_el_deg"] = float(min_el_deg)
                    current_pass["t_max_obj"] = t_ev
                    current_pass["tmax_dt"] = current_pass["aos_dt"]
                    current_pass["range_tmax_km"] = float(dist_aos.km)
                discovered_passes.append(current_pass.copy())
            current_pass = {}
            
    return discovered_passes


def compute_infrastructure_passes(
    satellite: Any,
    ground_station: Any,
    start_dt_utc: datetime,
    end_dt_utc: datetime,
    bands_config: dict,
    step_seconds: int = 20
) -> List[Dict[str, Any]]:
    sat_band = getattr(satellite, "assigned_band", getattr(satellite, "band", None))
    gs_bands = getattr(ground_station, "bands_supported", getattr(ground_station, "supported_bands", getattr(ground_station, "bands", [])))
    
    if not sat_band or (gs_bands and sat_band not in gs_bands):
        print(f"[DISCARD INCOMPATIBLE GS BAND] Sat {satellite.norad_id} ({sat_band}) can't link to GS {ground_station.id} (Supports {gs_bands})")
        return []

    sat_object = EarthSatellite(satellite.tle_line1, satellite.tle_line2, satellite.name)
    topo_target = wgs84.latlon(ground_station.latitude, ground_station.longitude, elevation_m=ground_station.elevation)
    
    band_info = bands_config.get(sat_band, {}) if sat_band else {}
    min_el_deg = float(band_info.get("min_elevation_deg", 10.0))
    max_slant_range_km = float(band_info.get("max_slant_range_km", 999999.0))
    
    raw_passes = _vectorized_pass_finder(
        sat_object, topo_target, start_dt_utc, end_dt_utc, min_el_deg,
        ground_station.latitude, ground_station.longitude, step_seconds
    )
    
    print(f"[DEBUG INFRA] Sat: {satellite.norad_id} over GS: {ground_station.id} -> Found {len(raw_passes)} geometric passes")

    formatted_passes = []
    tx_rate = satellite.downlink_rate_mb_s if satellite.downlink_rate_mb_s is not None else 10.0

    for p in raw_passes:
        distance_at_tmax = p.get("range_tmax_km", p["range_aos_km"])
        
        if distance_at_tmax > max_slant_range_km:
            print(f"  [DISCARD SLANT RANGE] Closest distance at culmination {distance_at_tmax:.1f} km exceeds max threshold {max_slant_range_km} km")
            continue

        max_downlink_capacity_mb = float(p["duration_s"] * tx_rate)
        pitch_max, roll_max = _calculate_lvlh_attitude(sat_object, p["t_max_obj"], ground_station.latitude, ground_station.longitude)

        aos_lat, aos_lon = _calculate_subsatellite_point(sat_object, p["t_aos_obj"])
        los_lat, los_lon = _calculate_subsatellite_point(sat_object, p["t_los_obj"])

        formatted_passes.append({
            "satellite_id": satellite.norad_id,
            "ground_station_id": ground_station.id,
            "aos_utc": p["aos_dt"].strftime("%Y-%m-%d %H:%M:%S"),
            "tmax_utc": p["tmax_dt"].strftime("%Y-%m-%d %H:%M:%S"),
            "los_utc": p["los_dt"].strftime("%Y-%m-%d %H:%M:%S"),
            "max_el_deg": p["max_el_deg"],
            "range_aos_km": p["range_aos_km"],
            "range_los_km": p["range_los_km"],
            "duration_s": p["duration_s"],
            "lvlh_target_pitch_deg": pitch_max,
            "lvlh_target_roll_deg": roll_max,
            "estimated_transmission_capacity_mb": max_downlink_capacity_mb,
            "subsat_start_lat": aos_lat,
            "subsat_start_lon": aos_lon,
            "subsat_end_lat": los_lat,
            "subsat_end_lon": los_lon
        })
    return formatted_passes


def compute_target_passes(
    satellite: Any,
    task: Any,
    simulation_start_utc: datetime,
    min_el_deg: float,
    sensor_constraints: dict,
    step_seconds: int = 20,
    min_duration: int = 5,
    max_duration: int = 30
) -> List[Dict[str, Any]]:
    required_sensor = task.sensor_requirements[0] if getattr(task, "sensor_requirements", None) else task.required_sensors[0] if getattr(task, "required_sensors", None) else "VIS"
    satellite_sensors = getattr(satellite, "assigned_sensors", getattr(satellite, "sensors", []))
    
    if required_sensor not in satellite_sensors:
        return []

    sat_object = EarthSatellite(satellite.tle_line1, satellite.tle_line2, satellite.name)
    c_lat, c_lon, task_radius_deg = _calculate_geodetic_centroid_and_radius(task)
    topo_target = wgs84.latlon(c_lat, c_lon, elevation_m=0.0)
    
    task_release_dt = simulation_start_utc + timedelta(seconds=task.release_time) if hasattr(task, 'release_time') else simulation_start_utc + timedelta(seconds=task.release_time_s)
    task_deadline_dt = simulation_start_utc + timedelta(seconds=task.deadline) if hasattr(task, 'deadline') else simulation_start_utc + timedelta(seconds=task.deadline_s)
    
    raw_passes = _vectorized_pass_finder(sat_object, topo_target, task_release_dt, task_deadline_dt, min_el_deg, c_lat, c_lon, step_seconds)
    
    print(f"[DEBUG TARGET] Sat: {satellite.norad_id} over Task: {task.task_id} ({task.region_tag}) -> Found {len(raw_passes)} geometric passes")

    mean_motion_rad_min = sat_object.model.no
    satellite_speed_deg_s = (mean_motion_rad_min * (180.0 / np.pi)) / 60.0
    
    temporal_buffer = 0.0
    if task.task_type == "polygon" and satellite_speed_deg_s > 0:
        temporal_buffer = task_radius_deg / satellite_speed_deg_s
        
    valid_passes = []
    
    if hasattr(satellite, 'sensor_generation_rates_mb_s') and satellite.sensor_generation_rates_mb_s is not None:
        rates_map = satellite.sensor_generation_rates_mb_s
    elif hasattr(satellite, 'sensor_generation_rates') and satellite.sensor_generation_rates is not None:
        rates_map = satellite.sensor_generation_rates
    else:
        rates_map = {}
        
    data_ingestion_rate = rates_map.get(required_sensor, 30.0)

    sensor_info = sensor_constraints.get(required_sensor, {})
    max_look_angle = float(sensor_info.get("max_look_angle_deg", 90.0))

    for p in raw_passes:
        adjusted_aos = p["aos_dt"] - timedelta(seconds=temporal_buffer)
        adjusted_los = p["los_dt"] + timedelta(seconds=temporal_buffer)
        
        clipped_aos = max(adjusted_aos, task_release_dt)
        clipped_los = min(adjusted_los, task_deadline_dt)
        
        if clipped_los <= clipped_aos:
            continue
            
        visibility_duration_s = int((clipped_los - clipped_aos).total_seconds())
        
        if task.task_type == "polygon" and satellite_speed_deg_s > 0:
            polygon_transit_time_s = (2.0 * task_radius_deg) / satellite_speed_deg_s
            sensor_active_duration_s = min(int(polygon_transit_time_s), visibility_duration_s)
            
            mid_point_dt = clipped_aos + timedelta(seconds=visibility_duration_s / 2.0)
            img_start_dt = mid_point_dt - timedelta(seconds=sensor_active_duration_s / 2.0)
            img_end_dt = mid_point_dt + timedelta(seconds=sensor_active_duration_s / 2.0)
        else:
            seed_hash = int(satellite.norad_id) + hash(task.task_id) + int(p["aos_dt"].timestamp())
            rng = np.random.default_rng(abs(seed_hash) % (2**32))
            
            random_duration = rng.integers(int(min_duration), int(max_duration) + 1)
            sensor_active_duration_s = min(int(random_duration), visibility_duration_s)
            
            img_start_dt = p["tmax_dt"] - timedelta(seconds=sensor_active_duration_s / 2.0)
            img_end_dt = p["tmax_dt"] + timedelta(seconds=sensor_active_duration_s / 2.0)

        img_start_dt = max(img_start_dt, clipped_aos)
        img_end_dt = min(img_end_dt, clipped_los)
        sensor_active_duration_s = max(0, int((img_end_dt - img_start_dt).total_seconds()))
        
        generated_data_volume_mb = float(sensor_active_duration_s * data_ingestion_rate)
        
        pitch_start, roll_start = _calculate_lvlh_attitude(sat_object, p["t_aos_obj"], c_lat, c_lon)
        pitch_end, roll_end = _calculate_lvlh_attitude(sat_object, p["t_los_obj"], c_lat, c_lon)
        
        if abs(roll_start) > max_look_angle or abs(roll_end) > max_look_angle:
            print(f"  [DISCARD ATTITUDE] Roll angles (Start: {roll_start:.2f}°, End: {roll_end:.2f}°) exceed sensor max look angle {max_look_angle}°")
            continue

        aos_lat, aos_lon = _calculate_subsatellite_point(sat_object, p["t_aos_obj"])
        los_lat, los_lon = _calculate_subsatellite_point(sat_object, p["t_los_obj"])

        valid_passes.append({
            "satellite_id": satellite.norad_id,
            "task_id": task.task_id,
            "region_tag": task.region_tag,
            "aos_utc": clipped_aos.strftime("%Y-%m-%d %H:%M:%S"),
            "los_utc": clipped_los.strftime("%Y-%m-%d %H:%M:%S"),
            "max_el_deg": p["max_el_deg"],
            "visibility_duration_s": visibility_duration_s,
            "imaging_start_utc": img_start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "imaging_end_utc": img_end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "sensor_imaging_duration_s": sensor_active_duration_s,
            "lvlh_start_pitch_deg": pitch_start,
            "lvlh_start_roll_deg": roll_start,
            "lvlh_end_pitch_deg": pitch_end,
            "lvlh_end_roll_deg": roll_end,
            "estimated_onboard_data_generation_mb": generated_data_volume_mb,
            "is_feasible": True,
            "subsat_start_lat": aos_lat,
            "subsat_start_lon": aos_lon,
            "subsat_end_lat": los_lat,
            "subsat_end_lon": los_lon
        })
        
    return valid_passes