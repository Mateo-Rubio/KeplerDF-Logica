import random
from typing import List, Dict, Any, Optional
from src.core.datatypes import TargetTask

__all__ = ["generate_dynamic_tasks"]


def generate_dynamic_tasks(
    k: int,
    bounding_boxes: List[Dict[str, Any]],
    polygon_ratio: float = 0.5,
    min_area_deg: float = 0.05,
    max_area_deg: float = 0.20,
    min_release_delay: int = 0,
    max_release_delay: int = 7200,     
    min_lifetime: int = 1800,          
    max_lifetime: int = 7200,          
    available_sensors: List[str] = None,
    priority_weights: Optional[List[float]] = None,
    seed: Optional[int] = None
) -> List[TargetTask]:
    """
    Procedurally synthesizes an array of target observation requests across selected geographical regions.

    Generates distinct, deterministically seeded metadata sets modeling Earth-observation tasks.
    Each task configuration maps stochastically chosen properties, including mission allocation priority 
    hierarchies, operational payload hardware sensor prerequisites, and localized geodetic tracking 
    coordinates structured as discrete points or enclosed polygonal scan tracks. Timeline parameters 
    (queue injection release time and strict expiration deadline bounds) are procedurally computed 
    as relative integer offsets anchored to t0 = 0 seconds.

    Args:
        k: The exact number of unique target task configurations to procedurally generate.
        bounding_boxes: List of geographical bounding envelope configurations containing lat/lon ranges.
        polygon_ratio: Stochastic probability threshold controlling task geometry selection (polygon vs point).
        min_area_deg: Lower bound delta constraint in degrees for generating polygonal perimeter dimensions.
        max_area_deg: Upper bound delta constraint in degrees for generating polygonal perimeter dimensions.
        min_release_delay: Lower bound relative time window in seconds for task availability injection.
        max_release_delay: Upper bound relative time window in seconds for task availability injection.
        min_lifetime: Lower bound operational lifespan limit in seconds determining expiration windows.
        max_lifetime: Upper bound operational lifespan limit in seconds determining expiration windows.
        available_sensors: Complete registry array of payload instrumentation suites supported in the current run.
        priority_weights: Probability density distribution vector controlling the assignment frequency of task priorities.
        seed: Fixed pseudo-random initialization anchor used to guarantee experimental simulation reproducibility.

    Returns:
        A list of procedurally generated and parameterized TargetTask dataclass objects.

    Raises:
        ValueError: If the bounding_boxes collection template is empty or unprovided.
    """
    if k <= 0:
        return []
        
    if not bounding_boxes:
        raise ValueError("Task generation requires at least one active bounding box definition.")
        
    sensors = available_sensors if available_sensors is not None else ["VIS", "SAR", "TIR"]
    rng = random.Random(seed)
    tasks = []

    priorities_pool = [1, 2, 3]

    for i in range(k):
        task_id = f"TASK_GEN_{i+1:03d}"
        
        if priority_weights is not None:
            priority = int(rng.choices(priorities_pool, weights=priority_weights, k=1)[0])
        else:
            priority = rng.randint(1, 5)
        
        release_time = rng.randint(min_release_delay, max_release_delay)
        task_lifetime = rng.randint(min_lifetime, max_lifetime)
        deadline = release_time + task_lifetime
        
        box = bounding_boxes[i % len(bounding_boxes)]
        region_tag = box.get("name", "unknown_region")
        
        lat_envelope = box.get("lat_envelope", [0.0, 0.0])
        lon_envelope = box.get("lon_envelope", [0.0, 0.0])
        
        center_lat = rng.uniform(lat_envelope[0], lat_envelope[1])
        center_lon = rng.uniform(lon_envelope[0], lon_envelope[1])
        
        num_sensors = 1
        required_sensors = rng.sample(sensors, num_sensors)
        
        is_polygon = rng.random() < polygon_ratio
        coordinates = []
        
        if not is_polygon:
            task_type = "point"
            coordinates.append((center_lat, center_lon))
        else:
            task_type = "polygon"
            delta_lat = rng.uniform(min_area_deg, max_area_deg)
            delta_lon = rng.uniform(min_area_deg, max_area_deg)
            
            p1 = (center_lat + delta_lat, center_lon - delta_lon)
            p2 = (center_lat + delta_lat, center_lon + delta_lon)
            p3 = (center_lat - delta_lat, center_lon + delta_lon)
            p4 = (center_lat - delta_lat, center_lon - delta_lon)
            
            coordinates.extend([p1, p2, p3, p4, p1])

        tasks.append(
            TargetTask(
                task_id=task_id,
                region_tag=region_tag,
                priority=priority,
                task_type=task_type,
                coordinates=coordinates,
                required_sensors=required_sensors,
                release_time=release_time,
                deadline=deadline
            )
        )
        
    return tasks