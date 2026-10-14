"""Render the real public GitHub calendar as an animated SVG. No dependencies."""
import argparse
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
from math import log2
from pathlib import Path
import re
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
USER = 'StephenCurryAn'
COLORS = ['#182e36', '#205a54', '#2d9380', '#63e6c4', '#f5bd66']


class Calendar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells, self.labels = {}, {}
        self.tip = None
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'td' and 'data-date' in attrs:
            self.cells[attrs['id']] = (attrs['data-date'], int(attrs['data-level']))
        if tag == 'tool-tip':
            self.tip = attrs.get('for')
            self.buffer = []

    def handle_data(self, data):
        if self.tip:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == 'tool-tip' and self.tip:
            self.labels[self.tip] = ''.join(self.buffer).strip()
            self.tip = None


def parse_calendar(source, start, end):
    parser = Calendar()
    parser.feed(source)
    days = {}
    for key, (day, level) in parser.cells.items():
        d = date.fromisoformat(day)
        if not start <= d <= end:
            continue
        label = parser.labels.get(key, '')
        match = re.match(r'([\d,]+) contributions?\b', label)
        if label.startswith('No contributions'):
            count = 0
        elif match:
            count = int(match.group(1).replace(',', ''))
        else:
            raise ValueError(f'Cannot read contribution count for {day}: {label!r}')
        if level not in range(5) or day in days:
            raise ValueError(f'Invalid or duplicate calendar cell: {day}')
        if (count == 0) != (level == 0):
            raise ValueError(f'Inconsistent intensity for {day}')
        days[day] = {'date': day, 'count': count, 'level': level}
    expected = (end-start).days + 1
    if len(days) != expected:
        raise ValueError(f'Incomplete calendar: {len(days)} / {expected} days. Existing artwork will be preserved.')
    return [days[key] for key in sorted(days)]


def text(x, y, value, size=13, color='#94afaf', extra=''):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" {extra}>{escape(str(value))}</text>'


def render(days, year, updated):
    first = date(year, 1, 1)
    offset = (first.weekday()+1) % 7
    total = sum(d['count'] for d in days)
    active = sum(d['count'] > 0 for d in days)
    peak = max(d['count'] for d in days)
    longest = run = 0
    for day in days:
        run = run + 1 if day['count'] else 0
        longest = max(longest, run)
    body = text(38,43,f'{year} / CONTRIBUTION ATLAS',16,'#63e6c4','class="mono"')
    body += text(38,77,'Small steps. A visible journey.',26,'#edf6f4','font-weight="600"')
    for x, value, label in [(758,total,'CONTRIBUTIONS'),(920,active,'ACTIVE DAYS'),(1070,longest,'BEST STREAK')]:
        body += text(x,48,value,30,'#f5bd66','font-weight="700"') + text(x,72,label,9,extra='class="mono"')
    cells, blocks = [], []
    for item in days:
        d = date.fromisoformat(item['date'])
        index = (d-first).days+offset
        week, weekday = divmod(index,7)
        level, count = item['level'], item['count']
        color = COLORS[level]
        x,y = 69+week*20, 125+weekday*20
        label = escape(f'{d.isoformat()}: {count} contributions')
        cell = f'<rect x="{x}" y="{y}" width="15" height="15" rx="3" fill="{color}"/>'
        if count:
            cell += f'<rect x="{x-2}" y="{y-2}" width="19" height="19" rx="5" fill="none" stroke="{color}" opacity=".5" class="spark" style="animation-delay:-{week*.21}s"/>'
        cells.append(f'<g><title>{label}</title>{cell}</g>')
        # Isometric floor: one tile per date, pillar height grows logarithmically with count.
        bx,by = 100+week*17+weekday*10, 447-week*1.55+weekday*6
        h = min(100, 10+20*log2(count+1)) if count else 0
        top = f'{bx:.1f},{by-h:.1f} {bx+8:.1f},{by+4-h:.1f} {bx+22:.1f},{by-1-h:.1f} {bx+14:.1f},{by-5-h:.1f}'
        block = ''
        if count:
            block += f'<polygon points="{bx},{by-h} {bx+8},{by+4-h} {bx+8},{by+4} {bx},{by}" fill="{color}" opacity=".5"/>'
            block += f'<polygon points="{bx+8},{by+4-h} {bx+22},{by-1-h} {bx+22},{by-1} {bx+8},{by+4}" fill="{color}" opacity=".75"/>'
        block += f'<polygon points="{top}" fill="{color}" stroke="#29424a" stroke-width=".65"/>'
        if count:
            block += f'<polygon points="{top}" fill="#fff" opacity=".14" class="spark" style="animation-delay:-{week*.21}s"/>'
        blocks.append((by,f'<g><title>{label}</title>{block}</g>'))
    for weekday,label in [(1,'MON'),(3,'WED'),(5,'FRI')]:
        body += text(26,136+weekday*20,label,8,extra='class="mono"')
    for month in range(1,13):
        d = date(year,month,1)
        week = ((d-first).days+offset)//7
        body += text(69+week*20,112,d.strftime('%b').upper(),9,extra='class="mono"')
    body += ''.join(cells)
    body += '<g clip-path="url(#calendar)"><path d="M65 122 V262" stroke="#b8ffe9" stroke-width="2" opacity=".5" class="sweep"/></g>'
    body += text(69,293,'LESS',8,extra='class="mono"')
    for i,color in enumerate(COLORS):
        body += f'<rect x="{111+i*18}" y="283" width="12" height="12" rx="2" fill="{color}"/>'
    body += text(212,293,'MORE',8,extra='class="mono"')
    body += text(1132,293,f'PEAK / {peak} IN ONE DAY',9,extra='text-anchor="end" class="mono"')
    body += '<path d="M38 316 H1162" stroke="#29424a"/>'
    body += text(40,345,'THE CONTRIBUTION TERRAIN',10,'#63e6c4','class="mono"')
    body += ''.join(block for _,block in sorted(blocks,key=lambda entry:entry[0]))
    body += text(1132,474,'HEIGHT = DAILY COUNT',9,extra='text-anchor="end" class="mono"')
    body += text(1132,495,'logarithmic scale',11,extra='text-anchor="end"')
    body += '<path d="M38 520 H1162" stroke="#29424a"/>'
    body += text(40,548,f'PUBLIC GITHUB CALENDAR / {USER}',9,extra='class="mono"')
    body += text(1160,548,f'{days[0]["date"]} → {days[-1]["date"]} · Updated {updated}',10,extra='text-anchor="end"')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="575" viewBox="0 0 1200 575" role="img" aria-labelledby="title desc">
<title id="title">{USER} · {year} contribution atlas</title><desc id="desc">Real GitHub calendar. {total} contributions, {active} active days, longest streak {longest} days. Height represents daily count using a logarithmic scale.</desc>
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#10222b"/><stop offset="1" stop-color="#091218"/></linearGradient><clipPath id="calendar"><rect x="65" y="122" width="1070" height="141"/></clipPath></defs>
<style>text{{font-family:Segoe UI,Arial,sans-serif}}.mono{{font-family:Consolas,monospace;letter-spacing:1.3px}}.spark{{animation:spark 4s ease-in-out infinite}}.sweep{{animation:sweep 16s linear infinite}}@keyframes spark{{50%{{opacity:.08}}}}@keyframes sweep{{to{{transform:translateX(1070px)}}}}@media(prefers-reduced-motion:reduce){{.spark,.sweep{{animation:none}}}}</style>
<rect x=".5" y=".5" width="1199" height="574" rx="20" fill="url(#bg)" stroke="#2a4249"/>{body}</svg>'''


def main():
    today = datetime.now(timezone(timedelta(hours=8))).date()
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--year', type=int, default=today.year)
    args.add_argument('--output', default='assets/contributions.svg')
    options = args.parse_args()
    if not 2008 <= options.year <= today.year:
        args.error('Year must be between 2008 and the current year.')
    start, end = date(options.year,1,1), min(today,date(options.year,12,31))
    url = f'https://github.com/users/{USER}/contributions?from={start}&to={end}'
    request = Request(url,headers={'User-Agent':f'{USER}-profile','Accept-Language':'en-US,en;q=0.9'})
    with urlopen(request,timeout=45) as response:
        source = response.read().decode('utf-8')
    days = parse_calendar(source,start,end)
    artwork = render(days,options.year,today.isoformat())
    output = ROOT / options.output
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(artwork,encoding='utf-8')
    data = ROOT / 'data' / f'contributions-{options.year}.json'
    data.parent.mkdir(exist_ok=True)
    data.write_text(json.dumps({'source':url,'updated':str(today),'days':days},indent=2)+'\n',encoding='utf-8')
    print(f'{options.year}: {len(days)} days, {sum(d["count"] for d in days)} contributions. Saved {output.name}.')


if __name__ == '__main__':
    main()
