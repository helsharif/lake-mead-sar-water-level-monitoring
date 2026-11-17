"""Analysis parameters and Lake Mead study geometry."""
from dataclasses import dataclass

CRS = "EPSG:32611"
MONITOR_BOUNDS = (-115.02, 35.98, -113.78, 36.57)
# Sampling windows are interpreted only inside the reservoir's water corridor.
SHORE_WINDOWS = {
    "overton": (-114.66, 36.27, -114.30, 36.55),
    "boulder": (-114.93, 36.02, -114.61, 36.23),
    "virgin": (-114.61, 36.06, -114.29, 36.27),
}
# Broad Boulder Basin core, intersected with historically persistent water.
SEED_BOUNDS = (-114.84, 36.04, -114.72, 36.13)
LOCAL_ZONE = "Etc/GMT+7"  # Reclamation's fixed Mountain Standard Time


@dataclass(frozen=True)
class Settings:
    """Starting parameters to test against independent shoreline references."""

    polarization: str = "VV"
    orbit_pass: str = "DESCENDING"
    track: int | None = None
    scale: int = 20
    angle_min: float = 30
    angle_max: float = 46
    speckle_m: int = 30
    corridor_m: int = 180
    min_water_pixels: int = 9
    water_reach_m: int = 4_000
    water_slope_max: float = 15
    sample_slope_max: float = 12
    terrain_min_m: float = 250
    terrain_max_m: float = 395
    land_min_m: int = 25
    land_max_m: int = 65
    margin_db: float = 0.75
    min_coverage: float = 0.95
    min_separation: float = 0.50
    min_blocks: int = 6
    max_block_iqr_m: float = 8
    block_m: int = 500
    samples_per_domain: int = 1500
    max_dsm_std_m: float = 2.0
    max_dsm_spread_m: float = 5.0
    max_surface_gap_m: float = 2.0

    def __post_init__(self) -> None:
        if self.polarization not in {"VV", "VH"}:
            raise ValueError("Polarization must be VV or VH")
        if self.orbit_pass not in {"ASCENDING", "DESCENDING"}:
            raise ValueError("Invalid orbit direction")
        if self.track is not None and not 1 <= self.track <= 175:
            raise ValueError("Relative orbit must be between 1 and 175")
        if self.scale < 10 or not 0 < self.angle_min < self.angle_max < 90:
            raise ValueError("Invalid pixel scale or incidence angle range")
        if not self.scale <= self.land_min_m < self.land_max_m:
            raise ValueError("Landward sampling must begin at least one SAR pixel away")
        if not 0 < self.min_coverage <= 1 or not 0 < self.min_separation < 1:
            raise ValueError("Coverage and separation must be fractional")
        if min(self.speckle_m, self.corridor_m, self.water_reach_m, self.margin_db,
               self.max_block_iqr_m) <= 0:
            raise ValueError("Distances, confidence margin and maximum IQR must be positive")
        if not 0 < self.sample_slope_max <= self.water_slope_max < 90:
            raise ValueError("Invalid terrain slope limits")
        if not self.terrain_min_m < self.terrain_max_m:
            raise ValueError("Invalid shoreline terrain elevation range")
        if not 1 <= self.min_water_pixels <= 100 or self.min_blocks < 2:
            raise ValueError("Invalid connectivity or sample block requirement")
        if self.block_m < 30 or self.samples_per_domain < self.min_blocks:
            raise ValueError("Invalid sample budget or block size")
        if min(self.max_dsm_std_m, self.max_dsm_spread_m, self.max_surface_gap_m) <= 0:
            raise ValueError('Terrain quality thresholds must be positive')
