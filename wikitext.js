// Wikipedia wikitext for a driver's Cup results, in WikiProject NASCAR's layout. Pure functions, no DOM: inlined into the
// dashboard by build_dashboard.py and unit-tested under node (tests/test_wikitext.js).
//
// Two tables, both taken from the project's own pages:
//   grid     the per-race results table used under "Motorsports career results" in driver articles (Year, Team, No., Make, 1..N, the
//            championship classification, Pts, Ref), coloured by Template:NASCAR driver results legend.
//   summary  the "Career results" table in Wikipedia:WikiProject NASCAR/quickbio (Year, Rank, Points, Starts, Wins, Top 5, Top 10, Avg. Start, Avg. Finish).
// nascaR.data has no winnings column, so the summary table leaves that column out.
const NASCARWikitext = (function () {
  // Template:NASCAR driver results legend: win, 2nd-5th, 6th-10th, 11th-20th, 21st or worse, DNF, DSQ, DNQ.
  const COLORS = { win: '#FFFFBF', top5: '#DFDFDF', top10: '#FFDF9F', top20: '#DFFFDF', rest: '#CFCFFF', dnf: '#EFCFFF', dsq: '#000000', dnq: '#FFCFCF' };

  // The series names and the season articles they link to, by era. `cls` is the championship-classification abbreviation used in the header.
  const SERIES = [
    { from: 1949, to: 1949, heading: 'Strictly Stock Series', title: '[[NASCAR]] [[NASCAR Strictly Stock Series|Strictly Stock Series]] results', cls: ['NGNC', 'NASCAR Grand National classification'], article: () => 'NASCAR Strictly Stock Series' },
    { from: 1950, to: 1970, heading: 'Grand National Series', title: '[[NASCAR]] [[Grand National Series]] results', cls: ['NGNC', 'NASCAR Grand National classification'], article: () => 'NASCAR Grand National Series' },
    { from: 1971, to: 2003, heading: 'Winston Cup Series', title: '[[NASCAR]] [[Winston Cup Series]] results', cls: ['NWCC', 'NASCAR Winston Cup classification'], article: () => 'NASCAR Winston Cup Series' },
    { from: 2004, to: 2007, heading: 'Nextel Cup Series', title: '[[NASCAR]] [[Nextel Cup Series]] results', cls: ['NNCC', 'NASCAR Nextel Cup classification'], article: () => 'NASCAR Nextel Cup Series' },
    { from: 2008, to: 2016, heading: 'Sprint Cup Series', title: '[[NASCAR]] [[Sprint Cup Series]] results', cls: ['NSCC', 'NASCAR Sprint Cup classification'], article: () => 'NASCAR Sprint Cup Series' },
    { from: 2017, to: 9999, heading: 'Cup Series', title: '[[NASCAR]] [[NASCAR Cup Series|Cup Series]] results', cls: ['NCSC', 'NASCAR Cup Series classification'],
      article: y => y <= 2019 ? 'Monster Energy NASCAR Cup Series' : 'NASCAR Cup Series' },
  ];
  const seriesOf = y => SERIES.find(s => y >= s.from && y <= s.to);

  // Track codes as used in the articles' result cells, keyed by the track names in nascaR.data. A track not listed gets initials and a comment to check.
  const TRACK = {
    'Daytona International Speedway': 'DAY', 'Daytona International Speedway Road Course': 'DAY', 'Daytona Beach & Road Course': 'DAY', 'Martinsville Speedway': 'MAR',
    'Darlington Raceway': 'DAR', 'Charlotte Motor Speedway': 'CLT', 'Charlotte Motor Speedway Road Course': 'CLT', 'Charlotte Speedway': 'CLT', 'Atlanta Motor Speedway': 'ATL',
    'EchoPark Speedway': 'ATL', 'Talladega Superspeedway': 'TAL', 'Richmond Raceway': 'RCH', 'Bristol Motor Speedway': 'BRI', 'Bristol Motor Speedway Dirt Track': 'BRI',
    'Michigan International Speedway': 'MCH', 'Dover International Speedway': 'DOV', 'Pocono Raceway': 'POC', 'Rockingham Speedway': 'CAR', 'North Wilkesboro Speedway': 'NWS',
    'Phoenix Raceway': 'PHO', 'New Hampshire Motor Speedway': 'NHA', 'Texas Motor Speedway': 'TEX', 'Riverside International Raceway': 'RSD', 'Kansas Speedway': 'KAN',
    'Watkins Glen International': 'GLN', 'Sonoma Raceway': 'SON', 'Las Vegas Motor Speedway': 'LVS', 'Auto Club Speedway': 'CAL', 'Indianapolis Motor Speedway': 'IND',
    'Indianapolis Motor Speedway Road Course': 'IND', 'Nashville Speedway': 'NSV', 'Nashville Superspeedway': 'NSH', 'Homestead-Miami Speedway': 'HOM', 'Columbia Speedway': 'CLB',
    'Asheville-Weaverville Speedway': 'AWS', 'Chicagoland Speedway': 'CHI', 'Chicago Street Course': 'CHI', 'Hickory Speedway': 'HCY', 'Occoneechee Speedway': 'HBO',
    'Langhorne Speedway': 'LAN', 'Greenville-Pickens Speedway': 'GPS', 'Bowman Gray Stadium': 'BGS', 'Piedmont Interstate Fairgrounds': 'PIF', 'Kentucky Speedway': 'KEN',
    'Ontario Motor Speedway': 'ONT', 'Texas World Speedway': 'TWS', 'Smokey Mountain Raceway': 'SMR', 'Trenton Speedway': 'TRN', 'Beltsville Speedway': 'BLV',
    'Circuit of the Americas': 'COA', 'Augusta International Speedway': 'AUG', 'Augusta International Raceway': 'AUG', 'South Boston Speedway': 'SBO', 'Middle Georgia Raceway': 'MGR',
    'Concord Speedway': 'CON', 'Birmingham International Raceway': 'BIR', 'Islip Speedway': 'ISP', 'Old Dominion Speedway': 'ODS', 'California State Fairgrounds': 'CSF',
    'Wilson Speedway': 'WIL', 'New Asheville Speedway': 'ASH', 'Langley Field Speedway': 'LGY', 'World Wide Technology Raceway at Gateway': 'GTW', 'Iowa Speedway': 'IOW',
    'Oxford Plains Speedway': 'OXF', 'Starkey Speedway': 'STR', 'Road America': 'ELK', 'Portland Speedway': 'POR', 'Dog Track Speedway': 'DTS', 'Old Bridge Stadium': 'OBS',
    'Cleveland County Fairgrounds': 'CCF', 'Savannah Speedway': 'SVH',
  };
  const guess = t => t.replace(/\b(Speedway|Raceway|International|Motor|Fairgrounds|Stadium|Park)\b/g, '').split(/\s+/).filter(Boolean).map(w => w[0]).join('').toUpperCase().padEnd(3, 'X').slice(0, 3);
  const code = t => TRACK[t] || guess(t);
  const unmappedTracks = seasons => [...new Set(seasons.flatMap(s => s.slots.map(x => x.track)).filter(t => !TRACK[t]))];

  const MAKE = { Chevrolet: '[[Chevrolet]]', Ford: '[[Ford Motor Company|Ford]]', Dodge: '[[Dodge]]', Plymouth: '[[Plymouth (automobile)|Plymouth]]', Pontiac: '[[Pontiac]]',
    Buick: '[[Buick]]', Oldsmobile: '[[Oldsmobile]]', Toyota: '[[Toyota]]', Mercury: '[[Mercury (automobile)|Mercury]]' };
  const ordinal = n => `${n}${n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' })[n % 10] || 'th'}`;
  const num = v => v == null ? '' : String(+(+v).toFixed(1));

  function color(e) {
    if (e.dsq) return COLORS.dsq;
    if (e.dnq) return COLORS.dnq;
    if (e.dnf) return COLORS.dnf;
    const f = e.finish;
    return f === 1 ? COLORS.win : f <= 5 ? COLORS.top5 : f <= 10 ? COLORS.top10 : f <= 20 ? COLORS.top20 : COLORS.rest;
  }

  // One race cell. `e` is the driver's result in that race (or undefined if he did not enter it).
  function raceCell(slot, e, o) {
    const c = code(slot.track), white = e && e.dsq;
    const text = white ? `<span style="color:white;">${c}</span>` : c;
    let label = o.link ? `[[${slot.name}|${text}]]` : text;
    if (!e) return `| ${label}`;
    if (o.pole && e.start === 1) label = `'''${label}'''`;
    if (e.dns) return `| ${label}<br>{{small|DNS}}`;
    const style = white ? 'background:#000000; color:white' : `background:${color(e)};`;
    return `| style="${style}"| ${label}<br>{{small|${e.finish}}}`;
  }

  // The grid for the seasons of one series. seasons: [{season, slots:[{num, track, name}], entries:{raceNum: {finish, start, dnf, dsq, dns, team, car, make}}, rank, pts}]
  function seriesTable(series, seasons, o) {
    const width = Math.max(...seasons.map(s => s.slots.length));
    const L = [`====${series.heading}====`, '{| class="wikitable" style="text-align:center; font-size:75%"', '|-', `!colspan=${width + 7}| ${series.title}`, '|-',
      '! Year', '! Team', '! No.', '! Make'];
    for (let i = 1; i <= width; i++) L.push(`! ${i}`);
    L.push(`! {{Tooltip|${series.cls[0]}|${series.cls[1]}}}`, '! Pts', ...(o.ref === false ? [] : ['! Ref']));
    for (const s of seasons) {
      // One row per ride (team, car number and make) he had that year, in the order he first drove it; every race appears in exactly one row, the row of the ride he drove it in.
      // A race he did not enter shows its track code only, in the row of the ride he last drove before it (the first row until his first start); the other rows leave it blank.
      const nums = Object.keys(s.entries).map(Number).sort((a, b) => a - b);
      const rides = new Map();
      for (const n of nums) {
        const e = s.entries[n], k = `${e.team}|${e.car}|${e.make}`;
        if (!rides.has(k)) rides.set(k, { e, nums: new Set() });
        rides.get(k).nums.add(n);
      }
      if (!rides.size) continue;
      const rows = [...rides.values()], rideOf = n => { const e = s.entries[n]; return rides.get(`${e.team}|${e.car}|${e.make}`); };
      const owner = new Map(); let cur = rows[0];
      for (const slot of s.slots) { if (s.entries[slot.num]) cur = rideOf(slot.num); owner.set(slot.num, cur); }
      const rs = rows.length > 1 ? `rowspan=${rows.length}| ` : '';
      rows.forEach((ride, k) => {
        L.push('|-');
        if (k === 0) L.push(`! ${rs}[[${s.season} ${series.article(s.season)}|${s.season}]]`);
        L.push(`! ${ride.e.team || ''}`, `! ${ride.e.car ?? ''}`, `! ${MAKE[ride.e.make] || ride.e.make || ''}`);
        let blanks = 0;
        const flush = () => { if (blanks) L.push(blanks > 1 ? `| colspan=${blanks}|` : '|'); blanks = 0; };
        for (const slot of s.slots) {
          if (owner.get(slot.num) !== ride) { blanks++; continue; }                          // another row has this race
          flush(); L.push(raceCell(slot, ride.nums.has(slot.num) ? s.entries[slot.num] : undefined, o));
        }
        blanks += width - s.slots.length; flush();
        if (k === 0) L.push(`! ${rs}${s.rank == null ? '' : ordinal(s.rank)}`, `! ${rs}${s.pts == null ? '-' : num(s.pts)}`, ...(o.ref === false ? [] : [`! ${rs}`]));
      });
    }
    L.push('|}');
    return L.join('\n');
  }

  // All series the driver raced in, one table each, headed by the key and the standard section titles.
  function grid(seasons, o = {}) {
    const by = new Map();
    for (const s of seasons.slice().sort((a, b) => a.season - b.season)) {
      const sr = seriesOf(s.season); if (!by.has(sr)) by.set(sr, []); by.get(sr).push(s);
    }
    const out = ['==Motorsports career results==', '===NASCAR===',
      "([[Template:NASCAR driver results legend|key]]) (<span style=\"font-size:85%\">'''Bold'''&nbsp;– Pole position awarded by qualifying time ''Italics''&nbsp;– Pole position earned by points standings or practice time</span>)", ''];
    for (const [sr, ss] of by) out.push(seriesTable(sr, ss, o), '');
    const um = unmappedTracks(seasons);
    if (um.length) out.push(`<!-- Track codes guessed from initials, check before saving: ${um.join('; ')} -->`);
    return out.join('\n');
  }

  // Wikipedia:WikiProject NASCAR/quickbio "Career results". rows: [{season, rank, pts, starts, wins, t5, t10, avgstart, avgfin}]
  function summary(rows) {
    const L = ['==Career results==', '{| class="wikitable sortable" border="1" style="font-size:80%; text-align:left;"', '|-',
      '! Year  || Rank || Points || Starts || Wins || Top 5 || Top 10 || Avg. Start || Avg. Finish'];
    for (const r of rows.slice().sort((a, b) => a.season - b.season))
      L.push('|-', `|${r.season} ||${r.rank ?? ''} ||${r.pts == null ? '' : num(r.pts)} ||${r.starts} ||${r.wins} ||${r.t5} ||${r.t10} ||${num(r.avgstart)} ||${num(r.avgfin)}`);
    L.push('|}');
    return L.join('\n');
  }

  return { COLORS, SERIES, TRACK, seriesOf, code, grid, summary, seriesTable, unmappedTracks, ordinal };
})();
if (typeof module !== 'undefined') module.exports = NASCARWikitext;
