"""NASCAR's driver file (driver_info.json, from fetch_driver_info.py) matched to the names in the results.

    import driver_info
    info = driver_info.match(driver_info.load(), ids, names)     # {results driver name: record}; ids: {results driver name: NASCAR driver id} from the lap files

A driver is matched by NASCAR's driver id when the lap files gave one (the lap and loop-statistic feeds use the same id as the driver file's Nascar_Driver_ID), else by
full name with accents, spaces and punctuation ignored ('Daniel Suarez' = 'Daniel Suárez'; 'Dale Earnhardt Jr.' is not 'Dale Earnhardt'). Where the file has two records
for a name, the one with a birth date is kept. A driver with no match is left out."""
import json
import os
import unicodedata

import nascar_data as nd

PATH = os.path.join(nd.ROOT, "driver_info.json")


def plain(name):
    """A name as letters only, lower case, accents removed; a leading '* ' (the feed's mark for a driver not in the points) is dropped."""
    s = unicodedata.normalize("NFKD", str(name).lstrip("* ")).encode("ascii", "ignore").decode()
    return nd.norm(s)


def load(path=PATH):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []


def match(records, ids, names):
    """records: load(); ids: {results name: NASCAR id}; names: all results driver names -> {name: record}."""
    by_id = {r["nascar_driver_id"]: r for r in records if r.get("nascar_driver_id")}
    by_name = {}
    for r in records:
        k = plain(r["name"])
        if k not in by_name or (r["born"] and not by_name[k]["born"]): by_name[k] = r
    out = {}
    for n in names:
        r = by_id.get(ids.get(n)) or by_name.get(plain(n))
        if r: out[n] = r
    return out
