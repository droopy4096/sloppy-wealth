"""Drawing the scenario timeline (ADR-0066) from its model, as the web module gets it from
the API (``POST /api/timeline``; ``timeline.layout`` builds it). Two drawings of the same
model: ``svg`` (horizontal, a time axis to scale) and ``graph`` (vertical, like
``git log --graph --oneline``: one row per month, each lane a column, branch and merge
curves, the month's happenings as a line of text; time is in order, not to scale).
Every element has a mouse-over tip. No engine imports (ADR-0069 decision 5).
"""
from html import escape


def month_label(idx):
    """A month index as 'YYYY-MM' (the engine's dates.month_label)."""
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


COLOR = {"income": "#2a8a4a", "pension": "#3a9a8a", "expense": "#c0392b",
         "contribution": "#7a5cc0", "withdrawal": "#a05cc0", "extraPayment": "#d98000",
         "property": "#2f6fc0", "vehicle": "#4a88d0", "mortgage": "#e08a00",
         "account": "#6a4fb0", "sale": "#222", "retirement": "#d4a000",
         "trunk": "#555", "renewal": "#e08a00", "lumpSum": "#e08a00",
         "improvement": "#2f6fc0", "marketAdjustment": "#9cc0ea", "adjustment": "#bbb",
         "transfer": "#6a4fb0", "cashBalance": "#555", "associatedIncome": "#6cbf84",
         "associatedOneOff": "#6cbf84"}
TRIGGER_COLOR = "#d4a000"


LABEL_W, CHART_W, LANE_H, TOP = 250, 1000, 22, 34


def svg(model):
    h0, h1 = model["start"], model["end"]
    scale = CHART_W / (h1 - h0 + 1)
    x = lambda m: LABEL_W + (min(max(m, h0), h1 + 1) - h0) * scale
    y = lambda r: TOP + r * LANE_H + LANE_H / 2
    height = TOP + len(model["lanes"]) * LANE_H + 10
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" class="timeline" width="{LABEL_W + CHART_W + 20}" '
           f'height="{height}" font-family="system-ui, sans-serif" font-size="12">',
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
           f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
           f'fill="{TRIGGER_COLOR}"/></marker></defs>']
    # Year grid.
    step = 1 if 12 * scale >= 30 else 5
    for year in range((h0 // 12), h1 // 12 + 1):
        m = year * 12
        if m < h0:
            continue
        out.append(f'<line x1="{x(m):.1f}" y1="{TOP - 4}" x2="{x(m):.1f}" y2="{height - 10}" '
                   'stroke="#eee"/>')
        if year % step == 0:
            out.append(f'<text x="{x(m):.1f}" y="{TOP - 10}" text-anchor="middle" '
                       f'fill="#777">{year}</text>')
    for g in model["guides"]:
        out.append(f'<line x1="{x(g["month"]):.1f}" y1="{TOP - 4}" x2="{x(g["month"]):.1f}" '
                   f'y2="{height - 10}" stroke="{COLOR["retirement"]}" stroke-dasharray="2,3">'
                   f'<title>{escape(g["name"])} {month_label(g["month"])}</title></line>')
    rows = {ln["id"]: ln["row"] for ln in model["lanes"]}
    color = lambda ln: COLOR.get(ln["type"], "#888")
    lane_by_id = {ln["id"]: ln for ln in model["lanes"]}
    # Branch and merge curves.
    for link in model["links"]:
        lane = lane_by_id[link["to"] if link["kind"] == "branch" else link["from"]]
        xm, yp, yc = x(link["month"]), y(rows[lane["parent"]]), y(lane["row"])
        # Off the household trunk: thin and light, so host links stand out.
        trunk = lane["parent"] is None and not link["trigger"]
        stroke = TRIGGER_COLOR if link["trigger"] else "#ccc" if trunk else color(lane)
        d = (f"M{xm - 12:.1f},{yp:.1f} Q{xm:.1f},{yp:.1f} {xm:.1f},{yc:.1f}"
             if link["kind"] == "branch" else
             f"M{xm:.1f},{yc:.1f} Q{xm:.1f},{yp:.1f} {xm + 12:.1f},{yp:.1f}")
        dash = ' stroke-dasharray="4,2"' if link["trigger"] else ""
        out.append(_tip(_link_tip(link["kind"], lane, model),
                        f'<path d="{d}" fill="none" stroke="{stroke}" '
                        f'stroke-width="{1 if trunk else 2}"{dash}{_dim(lane)}/>',
                        _hit("path", f'd="{d}"')))
    # Lanes and their names.
    for ln in model["lanes"]:
        ry = y(ln["row"])
        name = escape(ln["name"]) + (" (off)" if ln["off"] else "")
        href = "/" if ln["id"] is None else f'/#item-{escape(ln["id"])}'
        out.append(f'<a href="{href}"><text x="{6 + ln["depth"] * 12}" y="{ry + 4:.1f}" '
                   f'fill="{"#aaa" if ln["off"] else "#222"}">{name}</text></a>')
        width = 2 if ln["id"] is None else 6
        geometry = f'x1="{x(ln["first"]):.1f}" y1="{ry:.1f}" x2="{x(ln["last"] + 1):.1f}" y2="{ry:.1f}"'
        out.append(_tip(TRUNK_TIP if ln["id"] is None else _lane_tip(ln, model),
                        f'<line {geometry} stroke="{color(ln)}" stroke-width="{width}" '
                        f'stroke-linecap="round"{_dim(ln)}/>', _hit("line", geometry)))
    # Trigger arrows.
    for a in model["arrows"]:
        x1, y1, x2, y2 = x(a["month"]), y(a["from_row"]), x(a["to_month"]), y(a["to_row"])
        if (x1, y1) == (x2, y2):
            continue
        out.append(f'<path d="M{x1:.1f},{y1:.1f} L{x2:.1f},{y2 + (-5 if y2 > y1 else 5):.1f}" '
                   f'stroke="{TRIGGER_COLOR}" stroke-width="1.5" stroke-dasharray="4,3" '
                   f'fill="none" marker-end="url(#arrow)"{_dim(a)}>'
                   f'<title>&#9889; {escape(a["name"])} ({month_label(a["month"])})</title></path>')
    # One-off items.
    for d in model["dots"]:
        out.append(f'<a href="/#item-{escape(d["id"])}">' + _tip(
            _node_tip("dot", d, model, lane_by_id),
            f'<circle cx="{x(d["month"]):.1f}" cy="{y(d["row"]):.1f}" r="5" '
            f'fill="{COLOR.get(d["type"], "#fff")}" stroke="#333" stroke-width="1.2"{_dim(d)}/>',
            f'<circle cx="{x(d["month"]):.1f}" cy="{y(d["row"]):.1f}" r="8" '
            'fill="transparent"/>') + '</a>')
    out.append("</svg>")
    return "\n".join(out)


TRUNK_TIP = ("Household (cash): the household's cash over the whole horizon; items "
             "that belong to no other item branch off here")


def _tip(title, *elements):
    """Elements grouped under one mouse-over tip (an SVG <title>)."""
    return f'<g><title>{escape(title)}</title>{"".join(elements)}</g>'


def _hit(tag, geometry):
    """An invisible, wider copy of a thin line, so its tip is easy to reach."""
    return (f'<{tag} {geometry} fill="none" stroke="transparent" stroke-width="10" '
            'pointer-events="stroke"/>')


def _parent_name(lane, model):
    parent = next((ln for ln in model["lanes"] if ln["id"] == lane.get("parent")), None)
    return "the household" if parent is None or parent["id"] is None else parent["name"]


def _trigger(model, key):
    return f" (\u26a1 trigger {model['set_by'][key]})" if key in model["set_by"] else ""


def _off(thing):
    return " Switched off: not in the run." if thing.get("off") else ""


def _lane_tip(lane, model):
    """What a lane (a column or bar) stands for."""
    since = (f" (since {month_label(lane['first'])}, before the horizon)"
             if lane["first"] < model["start"] else "")
    until = ("the horizon end" if lane["last"] >= model["end"]
             else month_label(lane["last"]))
    return (f"{lane['name']} ({lane['type']}): runs {month_label(max(lane['first'], model['start']))}"
            f" to {until}{since}; belongs to {_parent_name(lane, model)}.{_off(lane)}")


def _link_tip(kind, lane, model):
    """What a branch or merge curve stands for."""
    parent = _parent_name(lane, model)
    if kind == "branch":
        return (f"{lane['name']} starts in {month_label(lane['first'])}, branching off "
                f"{parent}{_trigger(model, lane['id'] + ':start')}.")
    return (f"{lane['name']} ends after {month_label(lane['last'])}, merging back into "
            f"{parent}{_trigger(model, lane['id'] + ':end')}.")


def _node_tip(kind, thing, model, lane_by_id):
    """What a point on the graph stands for."""
    if kind == "dot":
        on = next((ln for ln in model["lanes"] if ln["row"] == thing["row"]), None)
        where = "the household" if on is None or on["id"] is None else on["name"]
        return (f"{thing['name']} ({thing['type']}, one-off) in {month_label(thing['month'])},"
                f" on {where}{_trigger(model, thing['id'] + ':start')}.{_off(thing)}")
    if kind == "end":
        return (f"End of {thing['name']} ({thing['type']}): last month "
                f"{month_label(thing['last'])}{_trigger(model, thing['id'] + ':end')}.{_off(thing)}")
    return (f"Start of {thing['name']} ({thing['type']}) in "
            f"{month_label(max(thing['first'], model['start']))}"
            f"{_trigger(model, thing['id'] + ':start')}.{_off(thing)}")


def _dim(thing):
    return ' opacity="0.3"' if thing.get("off") else ""


# ---------------------------------------------------------------- vertical graph
ROW_H, COL_W, GRAPH_LEFT, GRAPH_TOP = 20, 14, 10, 10
RANK = {"dot": 0, "end": 1, "start": 2}         # order of happenings within a month


def graph_rows(model):
    """The happenings in time order: (month, kind, lane or dot); kind start/end/dot. A lane
    started before the horizon gets its start row at the horizon start."""
    h0, h1 = model["start"], model["end"]
    rows = []
    for lane in model["lanes"][1:]:
        rows.append((max(lane["first"], h0), "start", lane))
        if lane["last"] < h1:
            rows.append((lane["last"] + 1, "end", lane))
    rows += [(d["month"], "dot", d) for d in model["dots"]]
    # Within a month: parents start before their children, children end before them.
    rows.sort(key=lambda r: (r[0], RANK[r[1]], -r[2]["row"] if r[1] == "end" else r[2]["row"]))
    return rows


def months(rows):
    """The happenings grouped by month: [(month, [(kind, thing), ...])] in time order."""
    out = []
    for month, kind, thing in rows:
        if not out or out[-1][0] != month:
            out.append((month, []))
        out[-1][1].append((kind, thing))
    return out


def columns(model, rows):
    """lane id -> its column: the first free one right of its parent's (trunk = 0). Lanes
    of one month share a row, so a column freed by an end is reused from the next month."""
    col, busy = {None: 0}, {0}
    for _, happenings in months(rows):
        for kind, thing in happenings:
            if kind == "start":
                c = col.get(thing["parent"], 0) + 1
                while c in busy:
                    c += 1
                col[thing["id"]] = c
                busy.add(c)
        for kind, thing in happenings:
            if kind == "end":
                busy.discard(col[thing["id"]])
    return col


LINE_CHARS, CHAR_W, DATE_W = 110, 6.4, 62       # wrapping of a month's text


def graph(model, newest_first=False):
    """One row per month (git log --graph style): the month's nodes side by side, then
    the month and its happenings, comma-separated (wrapped onto more lines if long)."""
    rows = graph_rows(model)
    col = columns(model, rows)
    groups = months(rows)
    if newest_first:
        groups.reverse()
    lane_by_id = {ln["id"]: ln for ln in model["lanes"]}
    ncols = max(col.values()) + 1
    cx = lambda c: GRAPH_LEFT + c * COL_W
    text_x = cx(ncols) + 10
    color = lambda t: COLOR.get(t, "#888")
    # Text lines per month, then each month's y (its first line).
    texts = [_month_lines(happenings, model, lane_by_id) for _, happenings in groups]
    ys, y = [], GRAPH_TOP + ROW_H / 2 + (ROW_H if newest_first else 0)   # merges' room
    for lines in texts:
        ys.append(y)
        y += ROW_H * len(lines)
    height = y + ROW_H / 2                     # room for the last merges
    index = {m: n for n, (m, _) in enumerate(groups)}
    edge = (GRAPH_TOP if newest_first else height - ROW_H)       # where open lanes run to
    back = ROW_H * (1 if newest_first else -1)                   # towards earlier rows
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" class="timeline-graph" '
           f'width="{text_x + DATE_W + LINE_CHARS * CHAR_W + 20:.0f}" height="{height:.0f}" '
           'font-family="system-ui, sans-serif" font-size="12">']
    trunk_line = f'x1="{cx(0)}" y1="{GRAPH_TOP}" x2="{cx(0)}" y2="{height - ROW_H}"'
    out.append(_tip(TRUNK_TIP, f'<line {trunk_line} stroke="{color("trunk")}" stroke-width="2"/>',
                    _hit("line", trunk_line)))
    h0, h1 = model["start"], model["end"]
    # Each lane's vertical extent, so a link never reaches a parent where it is not drawn.
    span = {None: (GRAPH_TOP, height - ROW_H)}
    for lane in model["lanes"][1:]:
        ys_ = ys[index[max(lane["first"], h0)]]
        ye_ = ys[index[lane["last"] + 1]] if lane["last"] < h1 else edge
        span[lane["id"]] = (min(ys_, ye_), max(ys_, ye_))
    for lane in model["lanes"][1:]:
        ys_ = ys[index[max(lane["first"], h0)]]
        ye_ = ys[index[lane["last"] + 1]] if lane["last"] < h1 else edge
        x, px = cx(col[lane["id"]]), cx(col[lane["parent"]])
        dim = _dim(lane)
        geometry = f'x1="{x}" y1="{ys_:.1f}" x2="{x}" y2="{ye_:.1f}"'
        out.append(_tip(_lane_tip(lane, model),
                        f'<line {geometry} stroke="{color(lane["type"])}" stroke-width="3"{dim}/>',
                        _hit("line", geometry)))
        trunk = lane["parent"] is None
        for kind, yy in (("branch", ys_ if lane["first"] > h0 else None),
                         ("merge", ye_ if lane["last"] < h1 else None)):
            if yy is None:
                continue
            end = "to" if kind == "branch" else "from"          # this lane's own link
            by_trigger = any(k["kind"] == kind and k[end] == lane["id"] and k["trigger"]
                             for k in model["links"])
            stroke = TRIGGER_COLOR if by_trigger else "#ccc" if trunk else color(lane["type"])
            d = back if kind == "branch" else -back
            dash = ' stroke-dasharray="3,2"' if by_trigger else ""
            # On the parent one row away; if the parent starts (ends) in the same month,
            # or is gone by then, at its own first (last) node instead.
            lo, hi = span.get(lane["parent"], span[None])
            at = min(max(yy + d * 0.9, lo), hi)
            t = at - yy
            path = (f'd="M{px},{at:.1f} L{x},{yy:.1f}"' if abs(t) < 1 else
                    f'd="M{px},{at:.1f} C{px},{yy + t / 3:.1f} {x},{yy + t * 2 / 3:.1f} '
                    f'{x},{yy:.1f}"')
            out.append(_tip(_link_tip(kind, lane, model),
                            f'<path {path} fill="none" stroke="{stroke}" '
                            f'stroke-width="{1.5 if trunk else 2}"{dash}{dim}/>',
                            _hit("path", path)))
    # Each month: its nodes on one row, then its text.
    row_lane = {ln["row"]: ln["id"] for ln in model["lanes"]}
    for n, (month, happenings) in enumerate(groups):
        y = ys[n]
        for kind, thing in happenings:
            if kind == "dot":
                x, fill, r = cx(col.get(row_lane.get(thing["row"]), 0)), color(thing["type"]), 5
            else:
                x, r = cx(col[thing["id"]]), 4
                fill = "#fff" if kind == "end" else color(thing["type"])
            out.append(_tip(_node_tip(kind, thing, model, lane_by_id),
                            f'<circle cx="{x}" cy="{y:.1f}" r="{r}" fill="{fill}" stroke="#333" '
                            f'stroke-width="1"{_dim(thing)}/>',
                            f'<circle cx="{x}" cy="{y:.1f}" r="8" fill="transparent"/>'))
        for k, line in enumerate(texts[n]):
            date = (f'<tspan font-family="monospace" fill="#b58900">{month_label(month)}</tspan>'
                    if k == 0 else "")
            out.append(f'<text x="{text_x}" y="{y + k * ROW_H + 4:.1f}">{date}</text>')
            out.append(f'<text x="{text_x + DATE_W}" y="{y + k * ROW_H + 4:.1f}" '
                       f'xml:space="preserve">{line}</text>')
    out.append("</svg>")
    return "\n".join(out)


def _month_lines(happenings, model, lane_by_id):
    """A month's text, wrapped: its one-off items, "ends:" and "starts:" lists, each name
    linked to the builder with its tip; markup per line."""
    groups = [(None, [t for k, t in happenings if k == "dot"], "dot"),
              ("ends:", [t for k, t in happenings if k == "end"], "end"),
              ("starts:", [t for k, t in happenings if k == "start"], "start")]
    tokens = []                                 # (plain length, markup)
    for label, things, kind in groups:
        if not things:
            continue
        if tokens:
            tokens[-1] = (tokens[-1][0] + 2, tokens[-1][1] + '<tspan fill="#bbb">\u00b7 </tspan>')
        if label:
            tokens.append((len(label) + 1, f'<tspan fill="#888">{label} </tspan>'))
        for n, thing in enumerate(things):
            key = f'{thing["id"]}:{"end" if kind == "end" else "start"}'
            mark = " \u26a1" if key in model["set_by"] else ""
            name = thing["name"] + (" (off)" if thing.get("off") else "")
            comma = "," if n < len(things) - 1 else ""
            fill = ' fill="#aaa"' if thing.get("off") else ""
            tokens.append((len(name) + len(mark) + len(comma) + 1,
                           f'<a href="/#item-{escape(thing["id"])}"><tspan{fill}>'
                           f'<title>{escape(_node_tip(kind, thing, model, lane_by_id))}</title>'
                           f'{escape(name)}<tspan fill="{TRIGGER_COLOR}">{mark}</tspan></tspan></a>'
                           f'{comma} '))
    lines, width = [[]], 0
    for size, markup in tokens:
        if width + size > LINE_CHARS and lines[-1]:
            lines.append([])
            width = 0
        lines[-1].append(markup)
        width += size
    return ["".join(line) for line in lines]
