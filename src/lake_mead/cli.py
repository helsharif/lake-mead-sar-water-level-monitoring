"""Command-line analysis, data retrieval and validation."""
import argparse
from dataclasses import asdict
from datetime import date
import json
import logging
from math import isfinite
from pathlib import Path
import sys

import ee
import pandas as pd
import requests

from . import gee, observations, sentinel1, storage, validation, workflow
from .config import SHORE_WINDOWS, Settings

LOG = logging.getLogger(__name__)


def positive(text: str) -> int:
    result = int(text)
    if result < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="lake-mead", description=__doc__)
    subs = command.add_subparsers(dest="command", required=True)
    for name in ("scenes", "run", "gauge"):
        sub = subs.add_parser(name)
        sub.add_argument("--start", type=date.fromisoformat, required=True)
        sub.add_argument("--end", type=date.fromisoformat, required=True, help="Exclusive end date")
        if name != "gauge":
            sub.add_argument("--pass", dest="orbit_pass", choices=["ASCENDING", "DESCENDING"],
                             default="DESCENDING")
            sub.add_argument("--track", type=int)
            sub.add_argument("--polarization", choices=["VV", "VH"], default="VV")
            sub.add_argument("--no-auth", action="store_true", help="Use existing EE credentials")
        if name == "gauge":
            sub.add_argument("--output", type=Path, default=Path("outputs/gauge.csv"))
        if name == "run":
            sub.add_argument("--limit", type=positive)
            sub.add_argument("--domains", nargs="+", choices=tuple(SHORE_WINDOWS))
            sub.add_argument("--monitor-window", choices=tuple(SHORE_WINDOWS),
                             help="Restrict area and classification to one basin for a pilot run")
            sub.add_argument("--output", type=Path, default=Path("outputs/run"))
            source = sub.add_mutually_exclusive_group()
            source.add_argument("--gauge-csv", type=Path)
            source.add_argument("--no-gauge", action="store_true")
            sub.add_argument("--gauge-to-egm96-m", type=float)
            sub.add_argument("--datum-source", help="Independent source and method for datum shift")
            sub.add_argument("--capacity-csv", type=Path)
    return command


def run(args: argparse.Namespace, settings: Settings) -> None:
    shift = args.gauge_to_egm96_m
    if shift is not None and (not isfinite(shift) or not args.datum_source):
        raise ValueError("A finite datum shift requires --datum-source")
    if args.no_gauge and (args.capacity_csv or shift is not None):
        raise ValueError("Datum shift and capacity interpolation require gauge observations")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.monitor_window and args.domains and set(args.domains) != {args.monitor_window}:
        raise ValueError("Pilot sampling must use the selected monitoring window")
    domains = args.domains or ([args.monitor_window] if args.monitor_window else None)
    analysis = workflow.Analysis.create(settings, monitor_window=args.monitor_window)
    areas, estimates, samples = analysis.run(args.start, args.end, args.limit, domains)
    def write(frame: pd.DataFrame, name: str) -> None:
        frame.to_csv(args.output / f"{name}.csv", index=False)

    write(areas, "acquisitions")
    write(estimates, "elevations")
    write(samples, "shoreline_samples")
    provenance = dict(start=args.start.isoformat(), end_exclusive=args.end.isoformat(),
                      settings=asdict(settings), actual_track=int(areas["track"].iloc[0]),
                      terrain=analysis.terrain.source, terrain_datum=analysis.terrain.datum,
                      terrain_scale_m=analysis.terrain.scale, datum_source=args.datum_source,
                      gauge_to_terrain_m=shift, limit=args.limit,
                      domains=domains or list(analysis.domains), monitor_window=args.monitor_window,
                      gauge_source="none" if args.no_gauge else
                      "user CSV" if args.gauge_csv else "USBR RISE 6123")
    (args.output / "run.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    matched = pd.DataFrame()
    if not args.no_gauge:
        gauge = (observations.read_csv(args.gauge_csv) if args.gauge_csv else
                 observations.download(min(args.start, date.fromisoformat(areas["date"].min())),
                                       args.end))
        write(gauge, "gauge")
        if args.capacity_csv:
            gauge = gauge.assign(capacity_acre_ft=storage.capacity(args.capacity_csv, gauge["gauge_ft"]))
            gauge["change_from_first_acre_ft"] = gauge["capacity_acre_ft"] - gauge["capacity_acre_ft"].iloc[0]
            write(gauge, "gauge_capacity")
        if "elevation_m" in estimates:
            matched, summary = validation.compare(estimates, gauge, shift)
            write(matched, "validation_pairs")
            (args.output / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    from .visualization import plot_results
    plot_results(areas, estimates, matched, args.output)
    eligible_count = int(estimates.get("qc", pd.Series(dtype=str)).eq("pass").sum())
    paired_count = int(matched.get("residual_m", pd.Series(dtype=float)).notna().sum())
    LOG.info("%d acquisitions, %d eligible domain estimates, %d eligible gauge pairs",
             len(areas), eligible_count, paired_count)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parser().parse_args()
    try:
        if args.end <= args.start:
            raise ValueError("End date must follow the start date")
        if args.command == "gauge":
            gauge = observations.download(args.start, args.end)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            gauge.to_csv(args.output, index=False)
            LOG.info("Retrieved %d daily RISE gauge measurements", len(gauge))
            return
        settings = Settings(polarization=args.polarization, orbit_pass=args.orbit_pass, track=args.track)
        gee.initialize(authenticate=not args.no_auth)
        if args.command == "scenes":
            from .config import MONITOR_BOUNDS
            scenes = sentinel1.scenes(args.start, args.end, gee.rectangle(MONITOR_BOUNDS), settings)
            print(json.dumps([asdict(scene) for scene in scenes], indent=2))
        else:
            run(args, settings)
    except (ee.EEException, OSError, ValueError, requests.RequestException) as error:
        LOG.error("%s", error)
        sys.exit(1)


if __name__ == "__main__":
    main()
