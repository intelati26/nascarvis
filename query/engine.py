"""Generic query engine (sketch). spec (JSON) -> SQL text + bound parameters -> read-only run -> table.

Nothing in this file knows what a driver or a race is: every table, column, flag, measure and qualifier comes from a catalog
(see catalog_nascar.json). Standard library only, SQLite dialect.

    from engine import load_catalog, compile_spec, run_sql
    sql, params, cols = compile_spec(spec, catalog)
    result = run_sql("data/query.db", sql, params)

Spec fields implemented (docs/vis-design.md section 7): subject, params, row_filters, group_by, measures,
aggregate_filters, qualifier, sort, limit, output. Recorded but not run: window, companions.
"""
import json
import re
import sqlite3
import time

MAX_ROWS = 1000
TIMEOUT_S = 10
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
OPS = {"=": "=", "!=": "<>", "<": "<", "<=": "<=", ">": ">", ">=": ">=", "like": "LIKE"}


class SpecError(ValueError):
    """The spec (or custom SQL) is invalid; the message is shown to the user."""


def load_catalog(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _coerce(value, typ, name):
    if value is None or value == "":
        return None
    try:
        if typ == "int": return int(value)
        if typ == "real": return float(value)
        if typ == "bool": return bool(value)
    except (TypeError, ValueError):
        raise SpecError(f"parameter {name!r} must be {typ}, got {value!r}")
    return str(value)


def compile_spec(spec, catalog, overrides=None):
    """Return (sql, params, columns). `params` holds only the values the SQL actually binds."""
    if not isinstance(spec, dict): raise SpecError("spec must be an object")
    subj = catalog["subjects"].get(spec.get("subject"))
    if subj is None:
        raise SpecError(f"unknown subject {spec.get('subject')!r}; choose from {sorted(catalog['subjects'])}")
    cols, measures, declared = subj["columns"], subj["measures"], subj.get("params", {})

    values = {k: v.get("default") for k, v in declared.items()}
    for src in (spec.get("params") or {}, overrides or {}):
        for k, v in src.items():
            if k not in declared: raise SpecError(f"unknown parameter {k!r}; declared: {sorted(declared)}")
            values[k] = v
    values = {k: _coerce(v, declared[k]["type"], k) for k, v in values.items()}

    bound, counter = {}, [0]

    def bind_param(name):
        if name not in declared: raise SpecError(f"unknown parameter {name!r}")
        bound[name] = values[name]
        return ":" + name

    def bind_value(v):
        counter[0] += 1
        key = f"v{counter[0]}"
        bound[key] = v
        return ":" + key

    def condition(expr, f, label):
        """SQL for one filter dict against `expr`, or None when its parameter is blank (optional filter)."""
        op = f.get("op")
        if op not in OPS and op not in ("in", "between", "is null", "is not null"):
            raise SpecError(f"{label}: unknown operator {op!r}")
        if op in ("is null", "is not null"): return f"{expr} {op.upper()}"
        if "param" in f:
            if f["param"] not in declared: raise SpecError(f"{label}: unknown parameter {f['param']!r}")
            if values[f["param"]] is None: return None
            if op in ("in", "between"): raise SpecError(f"{label}: {op} takes a literal list, not a parameter")
            rhs = bind_param(f["param"])
            if op == "like": bound[f["param"]] = "%" + str(bound[f["param"]]) + "%"
            return f"{expr} {OPS[op]} {rhs}"
        if "value" not in f: raise SpecError(f"{label}: needs 'value' or 'param'")
        v = f["value"]
        if op == "in":
            if not isinstance(v, list) or not v: raise SpecError(f"{label}: 'in' needs a non-empty list")
            return f"{expr} IN ({', '.join(bind_value(x) for x in v)})"
        if op == "between":
            if not isinstance(v, list) or len(v) != 2: raise SpecError(f"{label}: 'between' needs [low, high]")
            return f"{expr} BETWEEN {bind_value(v[0])} AND {bind_value(v[1])}"
        return f"{expr} {OPS[op]} {bind_value(v)}"

    def column(name, label):
        if name not in cols: raise SpecError(f"{label}: unknown column {name!r}")
        return cols[name]["sql"]

    group_by = spec.get("group_by") or []
    for g in group_by: column(g, "group_by")
    select, out_cols = [], []
    for g in group_by:
        select.append(f'{cols[g]["sql"]} AS "{g}"'); out_cols.append(g)

    measure_sql = {}
    for m in spec.get("measures") or []:
        if isinstance(m, str):
            if m not in measures: raise SpecError(f"unknown measure {m!r}")
            name, expr = m, measures[m]["sql"]
        elif isinstance(m, dict) and "count_if" in m:
            name = m.get("name", "")
            if not IDENT.match(name): raise SpecError("an inline measure needs a simple 'name' (letters, digits, underscore)")
            f = m["count_if"]
            c = condition(column(f.get("field"), f"measure {name}"), f, f"measure {name}")
            if c is None: raise SpecError(f"measure {name}: its parameter is blank")
            expr = f"SUM(CASE WHEN {c} THEN 1 ELSE 0 END)"
        else:
            raise SpecError("a measure is a catalog name or {name, count_if: {...}}")
        if name in out_cols: raise SpecError(f"duplicate output column {name!r}")
        measure_sql[name] = expr
        select.append(f'{expr} AS "{name}"'); out_cols.append(name)
    if not select: raise SpecError("choose at least one group_by column or measure")

    where = []
    for i, f in enumerate(spec.get("row_filters") or []):
        c = condition(column(f.get("field"), f"row_filters[{i}]"), f, f"row_filters[{i}]")
        if c is not None: where.append(c)

    having = []
    for i, f in enumerate(spec.get("aggregate_filters") or []):
        mname = f.get("measure")
        expr = measure_sql.get(mname) or (measures[mname]["sql"] if mname in measures else None)
        if expr is None: raise SpecError(f"aggregate_filters[{i}]: unknown measure {mname!r}")
        c = condition(expr, f, f"aggregate_filters[{i}]")
        if c is not None: having.append(c)
    q = spec.get("qualifier")
    if q:
        qd = subj.get("qualifiers", {}).get(q.get("name"))
        if qd is None: raise SpecError(f"unknown qualifier {q.get('name')!r}")
        for k, v in (q.get("params") or {}).items():
            if k not in declared: raise SpecError(f"qualifier parameter {k!r} is not declared")
            values[k] = _coerce(v, declared[k]["type"], k)
        text = qd["having"]
        for pname in re.findall(r":([A-Za-z_]\w*)", text): bind_param(pname)
        having.append(text)

    order = []
    for i, s in enumerate(spec.get("sort") or []):
        by, d = s.get("by"), str(s.get("dir", "asc")).lower()
        if by not in out_cols: raise SpecError(f"sort[{i}]: {by!r} is not an output column")
        if d not in ("asc", "desc"): raise SpecError(f"sort[{i}]: dir must be asc or desc")
        order.append(f'"{by}" {d.upper()}')

    lim = spec.get("limit", 100)
    if isinstance(lim, dict): lim = values.get(lim.get("param"))
    try: lim = min(int(lim if lim is not None else 100), MAX_ROWS)
    except (TypeError, ValueError): raise SpecError("limit must be a whole number")
    if lim < 1: raise SpecError("limit must be at least 1")
    bound["limit"] = lim

    lines = ["SELECT", "  " + ",\n  ".join(select), "FROM " + subj["from"]]
    if where: lines.append("WHERE " + "\n  AND ".join(where))
    if group_by: lines.append("GROUP BY " + ", ".join(cols[g]["sql"] for g in group_by))
    if having: lines.append("HAVING " + "\n  AND ".join(having))
    if order: lines.append("ORDER BY " + ", ".join(order))
    lines.append("LIMIT :limit")

    contract = (spec.get("output") or {}).get("columns")
    if contract is not None and list(contract) != out_cols:
        raise SpecError(f"output contract {list(contract)} does not match the query's columns {out_cols}")
    return "\n".join(lines), bound, out_cols


_FORBIDDEN = re.compile(r"\b(attach|detach|pragma|insert|update|delete|drop|alter|create|replace|vacuum|reindex|truncate)\b", re.I)


def check_custom_sql(sql):
    """Custom (hand-edited) SQL: one SELECT or WITH statement only. The connection is also opened read-only."""
    text = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S).strip().rstrip(";").strip()
    if not text: raise SpecError("the SQL is empty")
    if ";" in text: raise SpecError("only a single statement is allowed")
    if not re.match(r"^(select|with)\b", text, re.I): raise SpecError("only SELECT queries are allowed")
    m = _FORBIDDEN.search(text)
    if m: raise SpecError(f"{m.group(0).upper()} is not allowed in a query")
    return text


def run_sql(db_path, sql, params=None, max_rows=MAX_ROWS, timeout_s=TIMEOUT_S):
    """Run read-only with a row cap and a time limit. Returns {columns, rows, row_count, truncated, ms}."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        deadline = time.time() + timeout_s
        con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 20000)
        t0 = time.time()
        try:
            cur = con.execute(sql, params or {})
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e): raise SpecError(f"the query took longer than {timeout_s} seconds and was stopped")
            raise SpecError(str(e))
        except sqlite3.Warning as e:
            raise SpecError(str(e))
        columns = [d[0] for d in cur.description]
        truncated = len(rows) > max_rows
        rows = [list(r) for r in rows[:max_rows]]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated,
                "ms": round((time.time() - t0) * 1000)}
    finally:
        con.close()
