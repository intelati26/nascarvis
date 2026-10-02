#!/usr/bin/env python3
"""
Show what NASCAR's lap-time / loop-stat feeds return, so the best-lap fetcher can be built
against the real field names.

  pip install nascar-api            (needs Python 3.11+)
  python inspect_lap_data.py 2026              # lists the season's races and their race_id
  python inspect_lap_data.py 2026 5161         # also dumps a short sample of lap times + loop stats
  python inspect_lap_data.py 2026 --find-red   # scans the season for races with a red flag
  python inspect_lap_data.py 2026 5161 events  # lap notes + weekend feed, with red-flag / caution entries
                                               # pulled out (use a race_id that had a red flag)

Paste the output back and the fetcher gets written to match. Writes lap_data_sample.txt too.
"""
import json
import sys


def shrink(obj, depth=0):
    """Dump-friendly copy: lists cut to 2 items, long strings trimmed."""
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        return {k: shrink(v, depth + 1) for k, v in list(obj.items())[:40]}
    if isinstance(obj, (list, tuple)):
        return [shrink(v, depth + 1) for v in obj[:2]] + ([f"... {len(obj)} items"] if len(obj) > 2 else [])
    if isinstance(obj, str) and len(obj) > 80:
        return obj[:80] + "..."
    return obj


def find(obj, pred, path="", hits=None, limit=6):
    """Collect up to `limit` dicts anywhere inside obj for which pred(dict) is true."""
    hits = [] if hits is None else hits
    if len(hits) >= limit:
        return hits
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        if pred(obj):
            hits.append((path, obj))
        for k, v in obj.items():
            find(v, pred, f"{path}.{k}", hits, limit)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            find(v, pred, f"{path}[{i}]", hits, limit)
    return hits


def _text(d):
    return " ".join(str(v).lower() for v in d.values() if isinstance(v, str))


def is_red(d):
    return "red flag" in _text(d) or any(str(k).lower().startswith("flag") and str(v).lower() in ("3", "red")
                                          for k, v in d.items())


def is_yellow(d):
    return "caution" in _text(d) or "yellow" in _text(d) or any(
        str(k).lower().startswith("flag") and str(v).lower() in ("2", "yellow", "caution") for k, v in d.items())


def show(label, obj, out):
    text = f"\n=== {label} ===\n type: {type(obj).__name__}"
    if isinstance(obj, (list, tuple)):
        text += f", {len(obj)} items"
    text += "\n" + json.dumps(shrink(obj), indent=1, default=str)
    print(text)
    out.append(text)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    from nascar_api.enums import Series
    from nascar_api.repos import HistoricNascarRepo

    year = int(sys.argv[1])
    repo = HistoricNascarRepo()
    out = []
    races = repo.get_races(year, Series.CUP)
    show("first race record", races[0] if races else None, out)
    print("\nrace_id list (first 40):")
    for r in races[:40]:
        print("  ", getattr(r, "race_id", "?"), getattr(r, "race_name", ""), "-", getattr(r, "track_name", ""))
    if len(sys.argv) > 2 and sys.argv[2] == "--find-red":
        print("\nscanning lap notes for red flags (one request per race)...")
        for r in races:
            r = r.model_dump() if hasattr(r, "model_dump") else r
            if not (r.get("actual_laps") or 0):
                continue
            try:
                n = len(find(repo.get_lap_notes(year, Series.CUP, race_id=r["race_id"]), is_red, limit=50))
            except Exception as e:
                n = f"error {e.__class__.__name__}"
            print(f"  {r['race_id']}  type {r.get('race_type_id')}  {r.get('track_name')}: {n}")
        return
    if len(sys.argv) > 3 and sys.argv[3] == "events":
        rid = int(sys.argv[2])
        notes = repo.get_lap_notes(year, Series.CUP, race_id=rid)
        weekend = repo.get_weekend_data(year, Series.CUP, race_id=rid)
        show("lap notes", notes, out)
        show("weekend data", weekend, out)
        for label, pred in (("RED FLAG entries", is_red), ("CAUTION entries", is_yellow)):
            for src_name, src in (("lap notes", notes), ("weekend", weekend)):
                hits = find(src, pred, limit=4)
                show(f"{label} in {src_name} ({len(hits)} shown)", [h[1] for h in hits], out)
        with open("lap_data_sample.txt", "w") as f:
            f.write("\n".join(out))
        print("\nsaved lap_data_sample.txt")
        return
    if len(sys.argv) > 2:
        rid = int(sys.argv[2])
        show("lap times", repo.get_lap_times(year, Series.CUP, race_id=rid), out)
        show("loop stats", repo.get_loopstats(year, Series.CUP, race_id=rid), out)
    with open("lap_data_sample.txt", "w") as f:
        f.write("\n".join(out))
    print("\nsaved lap_data_sample.txt")


if __name__ == "__main__":
    main()
