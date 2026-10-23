#!/usr/bin/env python3
"""Fetch official final standings (and, where present, race purses) for early NASCAR seasons from Wikipedia and write
curation/final_standings_<season>.csv.   python curation/fetch_wikipedia_standings.py 1951 1952 ...

One request per article (wikitext via index.php?action=raw), identified by a project user-agent. Wikipedia text is
CC BY-SA 4.0: the CSVs carry the article name and fetch date. The articles use five different layouts, so the parser
looks for a standings table with a "Pts"/"Points" column, or a numbered list, and prints what it found: always check
the champion and top totals against the article before trusting a new season.
"""
import csv, datetime, os, re, sys, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "nascarvis/1.0 (https://github.com/intelati26/nascarvis; personal research)"


def article(season):
    for name in (f"{season}_NASCAR_Strictly_Stock_Series", f"{season}_NASCAR_Grand_National_Series", f"{season}_NASCAR_Winston_Cup_Series", f"{season}_NASCAR_Grand_National_season"):
        url = "https://en.wikipedia.org/w/index.php?title=" + urllib.parse.quote(name) + "&action=raw"
        try:
            txt = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")
        except urllib.error.HTTPError:
            continue                                   # no article under this name
        if len(txt) > 8000 and not txt.lstrip().lower().startswith("#redirect"):
            return name, txt
    return None, ""


def val(c):
    c = re.sub(r"\{\{efn.*?\}\}|<ref.*?(</ref>|/>)|<sup>.*?</sup>", "", c, flags=re.S)
    m = re.search(r"\{\{frac\|(\d+)\|(\d+)\|(\d+)\}\}", c)
    if m: return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.search(r"\{\{frac\|(\d+)\|(\d+)\}\}", c)
    if m: return int(m.group(1)) / int(m.group(2))
    c = re.sub(r"\{\{[^}]*\}\}|<[^>]*>|\[\[|\]\]|'''", "", c).replace(",", "")
    m = re.search(r"\d+(\.\d+)?", c)
    return float(m.group()) if m else None


def name_of(cell):
    cell = re.sub(r"<br\s*/?>.*$", "", cell)                               # "<br /><small>(Rookie OTY)</small>" and similar
    cell = re.sub(r"\{\{sortname\|([^|}]*)\|([^|}]*)[^}]*\}\}", r"\1 \2", cell)   # {{sortname|David|Pearson|...}} -> David Pearson
    n = re.sub(r"\{\{flagicon[^}]*\}\}|<[^>]*>", "", cell)
    n = re.sub(r"\{\{nowrap\|", "", n)
    n = re.sub(r"\{\{[^}]*\}\}", "", n)
    n = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]|]+)\]\]", r"\1", n)
    n = re.sub(r"^[|!]\s*(?:[a-z\-]+=[^|]*\|)?", "", n)
    n = re.sub(r"'{2,}", "", n)                                              # bold/italic markup, including the rookie marker
    n = re.sub(r"\s*\((?:R|r|Rookie)\)|[✝†‡*]+", "", n)
    return re.sub(r"[}\s]+$", "", n).strip().strip("'")


def cells_of(block):
    out = []
    for l in block.split("\n"):
        l = l.strip()
        if not l or l.startswith(("{|", "|}", "|+", "|-")): continue
        if l[0] in "!|":
            for part in re.split(r"\|\||!!", l[1:]):
                out.append(re.sub(r"^\s*(?:(?:style|rowspan|colspan|align|valign|scope|class|width|bgcolor)=[^|]*)\|(?!\|)", "", part).strip())
    return out


def table_points(txt, start):
    a = txt.find("{|", start); b = txt.find("\n|}", a); blocks = txt[a:b].split("\n|-")
    clean = lambda c: re.sub(r"\[\[(?:[^\]|]+\|)?([^\]|]+)\]\]", r"\1", re.sub(r"<[^>]*>|\{\{Tooltip\|([^|}]*)\|[^}]*\}\}", r"\1", c)).strip()
    hb = idx = hdr = None
    for bi, bl in enumerate(blocks[:4]):
        h = [clean(c) for c in cells_of(bl)]
        i = next((i for i, c in enumerate(h) if re.match(r"(?i)^(pts|points)\.?$", c)), None)
        if i is not None: hb, idx, hdr = bi, i, h; break
    if hb is None: return []
    last = idx == len(hdr) - 1
    out = []
    for r in blocks[hb + 1:]:
        cs = cells_of(r)
        if len(cs) < 3: continue
        p = re.sub(r"\D", "", re.sub(r"\{\{[^}]*\}\}", "", cs[0]))
        ni = next((i for i, c in enumerate(cs[:4]) if i > 0 and ("[[" in c or "sortname" in c or re.search(r"[A-Za-z]{3}", re.sub(r"\{\{[^}]*\}\}", "", c)))), None)
        if not p or ni is None: continue
        pts = val(cs[-1]) if last else (val(cs[idx]) if idx < len(cs) else None)
        nm = name_of("|" + cs[ni])
        if nm and pts is not None: out.append((int(p), nm, pts))
    return out


def list_points(txt, start):
    rx = r"^#\s*(?:\{\{[^}]*\}\}\s*)?\[\[(?:[^\]|]+\|)?([^\]|]+)\]\][^\n]*?[-–]\s*([\d,\.]+)\s*$"
    return [(i, m.group(1), float(m.group(2).replace(",", ""))) for i, m in enumerate(re.finditer(rx, txt[start:], re.M), 1)]


def continuation(txt, start, rows):
    """Some articles show only the top drivers and put the rest in a collapsed table straight after (Fin, Driver, Pts ...).
    Append such tables while their first position follows on from the last one."""
    pos = txt.find("\n|}", txt.find("{|", start)) + 3
    for _ in range(6):
        nxt = txt.find("{|", pos)
        if nxt < 0 or nxt - pos > 400: break
        more = table_points(txt, nxt - 1)
        if not more or more[0][0] != rows[-1][0] + 1: break
        rows = rows + more
        pos = txt.find("\n|}", nxt) + 3
    return rows


def standings(txt):
    for m in re.finditer(r"\n=+ *([^=\n]*(?:tandings|hampionship|Points)[^=\n]*?) *=+ *\n", txt):
        if re.search(r"^#\s*\[\[", txt[m.end():m.end() + 3000], re.M):
            o = list_points(txt, m.end())
            if len(o) >= 5: return m.group(1).strip(), o
        a = txt.find("{|", m.end())
        if a >= 0 and a - m.end() < 2500:
            o = table_points(txt, m.end())
            if len(o) >= 5: return m.group(1).strip(), continuation(txt, m.end(), o)
    # fallback: any table on the page with a Pts/Points column (headings vary: "Season statistics", unnamed sections, ...)
    best = None
    for m in re.finditer(r"\{\|", txt):
        o = table_points(txt, m.start() - 1)
        if len(o) >= 5 and (best is None or len(o) > len(best[1])): best = ("table on the page", continuation(txt, m.start() - 1, o))
    return best if best else (None, [])


def champions(today):
    """Champion, starts, wins, points and winning margin for 1949-2003 from Wikipedia's list of Cup champions.
    The article cites a Racing-Reference page for each season; the URL is recorded, nothing is fetched from it."""
    name = "List_of_NASCAR_Cup_Series_champions"
    url = "https://en.wikipedia.org/w/index.php?title=" + name + "&action=raw"
    txt = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")
    a = txt.find('{| class="wikitable sortable"'); seg = txt[a:txt.find("\n|}", a)]
    out = []
    for bl in seg.split("\n|-"):
        m = re.match(r"\s*!.*?\[\[(\d{4}) NASCAR", bl)
        if not m or int(m.group(1)) > 2003: continue
        cells = []
        for l in bl.split("\n")[1:]:
            if l.startswith(("|", "!")) and not l.startswith("|-"):
                cells.append(re.sub(r"^\s*[|!]\s*(?:(?:rowspan|colspan|style|scope|class)=(?:\"[^\"]*\"|\S+)\s*)*\|?\s*", "", l.rstrip()))
        num = lambda c: val(re.sub(r"\{\{tooltip\|(\d+)\|[^}]*\}\}", r"\1", c, flags=re.I))
        ref = re.search(r"url\s*=\s*(\S+?)[\s|]", cells[-1] + " ")
        champ = re.sub(r"\s*\(\d+\)", "", name_of("|" + cells[1]))
        out.append([int(m.group(1)), champ, num(cells[-7]), num(cells[-6]), num(cells[-5]), num(cells[-4]), num(cells[-3]), num(cells[-2]), ref.group(1) if ref else ""])
    path = os.path.join(HERE, "champions_points.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["season", "champion", "starts", "poles", "wins", "top10", "pts", "gap", "reference_url_cited_by_wikipedia", "source"])
        for r in out:
            w.writerow([r[0], r[1]] + [("%g" % v) if v is not None else "" for v in r[2:8]] + [r[8], f"Wikipedia: {name.replace('_', ' ')} (CC BY-SA 4.0), fetched {today}"])
    print(f"champions_points.csv: {len(out)} seasons ({out[0][0]}-{out[-1][0]})")


norm_name = lambda x: re.sub(r"[^a-z]", "", x.lower())


def champion_of(season):
    """(name, points) from champions_points.csv, used to sanity-check a parsed table's first row."""
    path = os.path.join(HERE, "champions_points.csv")
    if os.path.exists(path):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            if r["season"] == str(season): return r["champion"], float(r["pts"])
    return None


def main():
    import time
    today = datetime.date.today().isoformat()
    if sys.argv[1:] == ["champions"]:
        champions(today); return
    for n, season in enumerate(sys.argv[1:]):
        if n: time.sleep(0.8)                                          # one request per article, spaced out
        name, txt = article(season)
        if not txt: print(season, "no article"); continue
        head, rows = standings(txt)
        if not rows: print(season, f"{name}: no standings table found (not on this page)"); continue
        rows.sort(key=lambda r: (r[0], -r[2]))
        champ = champion_of(season)
        if champ and (norm_name(rows[0][1]) != norm_name(champ[0]) or abs(rows[0][2] - champ[1]) > 1e-6):
            print(season, f"SUSPECT, not written: first row {rows[0][1]} {rows[0][2]:g} but the champions list says {champ[0]} {champ[1]:g} ({head})"); continue
        path = os.path.join(HERE, f"final_standings_{season}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["season", "pos", "driver", "pts", "source"])
            for pos, nm, p in rows:
                w.writerow([season, pos, nm, ("%g" % p), f"Wikipedia: {name.replace('_', ' ')}, section '{head}' (CC BY-SA 4.0), fetched {today}"])
        print(season, f"{len(rows)} rows ({head}); champion {rows[0][1]} {rows[0][2]:g}")


if __name__ == "__main__":
    main()
