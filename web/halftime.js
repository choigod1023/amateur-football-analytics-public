// The page /halftime[?session=NAME][&half=2]: the picture-first report of app/halftime_rich.py (/api/v1/halftime/rich), drawn with DOM nodes and inline SVG only.
// The mini-maps follow the final's phone preview (work/match-1125/preview/build_preview2.py): pitch 100 x 64 at 3.4 px per unit with 10 px padding, our dots green
// with a dark ring (r 6.2), the other team red, solid lines for what happened, dashed yellow arrows (6 4, 2.2 px, arrow heads) for what is suggested.
// The pure part of the picture's direction (tests/test_halftime_flip.cjs runs it with node): the mini-maps 2, 4, 5 and 6 are drawn in the direction of the half they show
// (the same turn as map 7: the pitch rotated by 180 degrees, so left and right of the team stay what they are for the players, only the screen side changes).
const HalftimeFlip = {
  flipFor: direction => (direction === 1 || direction === -1 ? direction < 0 : false),            // no direction record: the fixed picture (we attack to the right)
  toPicture: (flip, x, y) => [flip ? 100 - x : x, flip ? 64 - y : y],                           // a point of the 100 x 64 picture (we attack to the right) -> where it is drawn
  attack: (flip, text) => (flip ? { side: 'left', text: `← ${text}` } : { side: 'right', text: `${text} →` }),
  goalSide: flip => (flip ? 'right' : 'left'),
  laneOrder: flip => (flip ? [2, 1, 0] : [0, 1, 2]),                                            // the lanes 왼 / 가운데 / 오른 from the top of the picture to the bottom
  note: direction => (direction === 1 || direction === -1 ? '그림은 영상(카메라)과 같은 방향입니다.' : '그림은 우리 공격이 오른쪽인 고정 방향입니다(공격 방향 기록 없음).'),
};
if (typeof module !== 'undefined') module.exports = HalftimeFlip;

(() => {
  if (typeof document === 'undefined') return;
  const el = id => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const session = params.get('session') || '', asked = params.get('half');
  let half = asked === '2' ? 2 : 1, generation = 0;
  const NS = 'http://www.w3.org/2000/svg';
  const SX = 3.4, PAD = 10;
  let uid = 0, lastKey = '';

  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const k in attrs) { if (k === 'class') e.className = attrs[k]; else if (k === 'text') e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]); }
    for (const kid of kids) if (kid) e.append(kid);
    return e;
  };
  const s = (tag, attrs = {}, text) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    return e;
  };

  // ---- the pitch of the preview ------------------------------------------------------------------------------------------------------
  // view: [u0, u1] metres of the pitch to show (zoomed like the preview's x0 / x1); renderW: the narrowest width the picture gets on a 375 px phone, so that a dot is 7 px or more
  function pitch(geo, label, flip = false, view = null, renderW = 300) {
    const id = ++uid, H = 64 * SX + 2 * PAD;
    const X = x => PAD + HalftimeFlip.toPicture(flip, x, 0)[0] * SX, Y = y => PAD + HalftimeFlip.toPicture(flip, 0, y)[1] * SX;
    const px = u => (u + geo.L / 2) / geo.L * 100, py = v => (v + geo.W / 2) / geo.W * 64;
    const [u0, u1] = view || [-geo.L / 2, geo.L / 2];
    const xa = X(px(u0)), xb = X(px(u1)), vx = Math.min(xa, xb) - PAD, vw = Math.abs(xb - xa) + 2 * PAD;
    const R = Math.max(6.2, 7.2 * vw / renderW);
    const svg = s('svg', { viewBox: `${vx.toFixed(1)} 0 ${vw.toFixed(1)} ${H}`, role: 'img', 'aria-label': label, class: 'mm' });
    const defs = s('defs');
    for (const [name, colour] of [['am', 'var(--lamp)'], ['ap', 'var(--chalk)'], ['ao', 'var(--red)'], ['ag', 'var(--pitch)']]) {
      const m = s('marker', { id: `${name}${id}`, viewBox: '0 0 10 10', refX: 8, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse' });
      m.append(s('path', { d: 'M0 0L10 5L0 10z', fill: colour })); defs.append(m);
    }
    svg.append(defs, s('rect', { x: vx, y: 0, width: vw, height: H, rx: 10, fill: 'var(--grass)' }));
    const g = s('g', { fill: 'none', stroke: 'var(--chalkline)', 'stroke-width': 1.2 });
    g.append(s('rect', { x: PAD, y: PAD, width: 100 * SX, height: 64 * SX }));
    g.append(s('line', { x1: PAD + 50 * SX, y1: PAD, x2: PAD + 50 * SX, y2: PAD + 64 * SX }), s('circle', { cx: PAD + 50 * SX, cy: PAD + 32 * SX, r: 9 * SX }));
    for (const x0 of [0, 84]) g.append(s('rect', { x: PAD + x0 * SX, y: PAD + 12 * SX, width: 16 * SX, height: 40 * SX }));
    for (const x0 of [0, 94.5]) g.append(s('rect', { x: PAD + x0 * SX, y: PAD + 23 * SX, width: 5.5 * SX, height: 18 * SX }));
    svg.append(g);
    const api = {
      svg, geo, flip, R, X: u => X(px(u)), Y: v => Y(py(v)),
      left: vx + 6, right: vx + vw - 6, top: PAD + 14, bottom: PAD + 64 * SX - 6,
      line(u1, v1, u2, v2, kind = 'solid', colour = 'var(--pitch)', marker = null, wide = 2.2) {
        const a = { x1: api.X(u1), y1: api.Y(v1), x2: api.X(u2), y2: api.Y(v2), stroke: colour, 'stroke-width': wide, 'stroke-linecap': 'round' };
        if (kind === 'dashed') a['stroke-dasharray'] = '6 4';
        if (marker) a['marker-end'] = `url(#${marker}${id})`;
        svg.append(s('line', a));
      },
      rect(u1, u2, v1, v2, kind, colour) {
        const x1 = api.X(u1), x2 = api.X(u2), y1 = api.Y(v1), y2 = api.Y(v2);
        const a = { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1), rx: 6, fill: colour, 'fill-opacity': kind === 'dashed' ? 0 : 0.14, stroke: colour, 'stroke-width': 1.4 };
        if (kind === 'dashed') a['stroke-dasharray'] = '6 4';
        svg.append(s('rect', a));
      },
      dot(u, v, kind = 'us', name = '', dashed = false) {
        // the dots take the shirt colours of the match (team_colours, set on the page by teamColours()); ours have a thick white ring, theirs a thin ring, so the two read apart even with close colours
        const fill = { us: 'var(--dot-ours, var(--pitch))', opp: 'var(--dot-theirs, #c8cec9)', key: 'var(--lamp)' }[kind];
        const ring = { us: ['#ffffff', 2.4], opp: ['var(--dot-theirs-ring, var(--night))', 1.1], key: ['var(--night)', 1.5] }[kind];
        const a = dashed ? { cx: api.X(u), cy: api.Y(v), r: R, fill: 'none', stroke: 'var(--lamp)', 'stroke-width': 1.6, 'stroke-dasharray': '3 2' }
          : { cx: api.X(u), cy: api.Y(v), r: R, fill, stroke: ring[0], 'stroke-width': ring[1] };
        svg.append(s('circle', a));
        if (name) {
          const yy = api.Y(v), below = yy < PAD + 56 * SX;
          svg.append(s('text', { x: api.X(u), y: yy + (below ? R + 11 : -R - 4), 'text-anchor': 'middle', class: 'pt' }, name));
        }
      },
      text(u, v, t, cls = 'lt', anchor = 'middle') { svg.append(s('text', { x: api.X(u), y: api.Y(v), 'text-anchor': anchor, class: cls }, t)); },
      raw(x, y, t, cls, anchor) { svg.append(s('text', { x, y, 'text-anchor': anchor, class: cls }, t)); },
      band(k, share, colour, label) {                       // the three lanes, left (top when we attack to the right) to right
        const v0 = -geo.W / 2 + k * geo.W / 3;
        svg.append(s('rect', { x: Math.min(api.X(-geo.L / 2), api.X(geo.L / 2)), y: Math.min(api.Y(v0), api.Y(v0 + geo.W / 3)), width: 100 * SX, height: 64 * SX / 3, fill: colour, 'fill-opacity': (0.08 + 0.8 * share / 100).toFixed(2) }));
        api.text(0, v0 + geo.W / 6 + 1.6, label, 'lt');
      },
    };
    // which side is our goal: always written; an arrow points out of the picture when the goal is cut off by the zoom
    const goalIn = u0 <= -geo.L / 2 + 1;
    const goalLeft = HalftimeFlip.goalSide(flip) === 'left';
    api.raw(goalLeft ? api.left : api.right, api.bottom, goalIn ? '우리 골문' : (goalLeft ? '← 우리 골문' : '우리 골문 →'), 'gt', goalLeft ? 'start' : 'end');
    return api;
  }

  function zoom(geo, us, margin = 7, least = 0.45) {         // the same [u0, u1] for several pictures: around the given depths, at least `least` of the pitch long
    let a = Math.min(...us) - margin, b = Math.max(...us) + margin;
    const need = least * geo.L - (b - a);
    if (need > 0) { a -= need / 2; b += need / 2; }
    if (a < -geo.L / 2) { b += -geo.L / 2 - a; a = -geo.L / 2; }
    if (b > geo.L / 2) { a -= b - geo.L / 2; b = geo.L / 2; }
    return [Math.max(-geo.L / 2, a), Math.min(geo.L / 2, b)];
  }

  const attack = (api, geo, text = '우리 공격') => { const a = HalftimeFlip.attack(api.flip, text); api.raw(a.side === 'left' ? api.left : api.right, api.bottom, a.text, 'zt', a.side === 'left' ? 'start' : 'end'); };
  // the dots of the places with their codes (LB, LDM, ST ...) or names: a name when the line-up has one ("LB 이름" when there is room), else the code; every label is put
  // below, right, left or above its dot, whichever first overlaps no dot and no label already placed
  function named(p, dots, others = []) {                    // others: [[u, v]] of further circles (the suggested places) a label must not cover
    for (const d of dots) p.dot(d.u, d.v, 'us');
    const pts = dots.map(d => ({ x: p.X(d.u), y: p.Y(d.v) })).concat(others.map(([u, v]) => ({ x: p.X(u), y: p.Y(v) }))), R = p.R, taken = [];
    const widthOf = t => [...t].reduce((w, ch) => w + (ch.charCodeAt(0) > 0x2e80 ? 12 : 7.6), 4);
    dots.forEach((d, i) => {
      if (!d.role && !d.name) return;
      const near = Math.min(Infinity, ...pts.slice(0, dots.length).filter((_, j) => j !== i).map(q => Math.abs(q.x - pts[i].x) + 0.5 * Math.abs(q.y - pts[i].y)));
      const full = d.name && d.role ? `${d.role} ${d.name}` : (d.name || d.role);
      const text = d.name && near > widthOf(full) + 2 * R ? full : (d.name || d.role);
      const w = widthOf(text), hgt = 14, { x, y } = pts[i];
      const side = R + 3 + w / 2;
      const options = [[x, y + R + 11], [x + side, y + 4], [x - side, y + 4], [x, y - R - 4], [x + side, y - R - 2], [x - side, y - R - 2], [x + side, y + R + 9], [x - side, y + R + 9], [x, y + R + 24], [x, y - R - 17]];
      const area = (a, b) => Math.max(0, Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1)) * Math.max(0, Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1));
      let pick = options[0], best = Infinity;
      for (const [cx, cy] of options) {                      // the first place with no overlap; if every place overlaps, the one that overlaps least
        const box = { x1: cx - w / 2, x2: cx + w / 2, y1: cy - hgt + 2, y2: cy + 2 };
        const out = Math.max(0, p.left - 4 - box.x1) + Math.max(0, box.x2 - p.right - 4) + Math.max(0, 14 - box.y1);   // never cut by the picture's edge
        const cost = 1e4 * out + taken.reduce((c, t) => c + area(t, box), 0) + pts.reduce((c, q) => c + area({ x1: q.x - R, x2: q.x + R, y1: q.y - R, y2: q.y + R }, box), 0);
        if (cost < best) { best = cost; pick = [cx, cy]; }
        if (cost === 0) break;
      }
      taken.push({ x1: pick[0] - w / 2, x2: pick[0] + w / 2, y1: pick[1] - hgt + 2, y2: pick[1] + 2 });
      p.svg.append(s('text', { x: pick[0], y: pick[1], 'text-anchor': 'middle', class: 'pt' }, text));
    });
  }

  const fig = (svg, caption) => h('figure', { class: 'mfig' }, svg, caption ? h('figcaption', { text: caption }) : null);

  function shape(api, m, colour, dashed = false, labelTop = false) {   // labelTop: the 수·미·공 words stay at the top of the picture (map 7 keeps its own place)          // the team block (back to front line, across the per-second mean width) and its three lines
    if (!m) return;
    const L = api.geo.L, v1 = m.vmin !== undefined ? m.vmin : m.centre_v - m.width / 2, v2 = m.vmax !== undefined ? m.vmax : m.centre_v + m.width / 2;   // per-second means
    api.rect(m.def - L / 2, m.att - L / 2, v1, v2, dashed ? 'dashed' : 'solid', colour);
    [['def', '수'], ['mid', '미'], ['att', '공']].forEach(([k, word]) => {
      api.line(m[k] - L / 2, v1, m[k] - L / 2, v2, dashed ? 'dashed' : 'solid', colour, null, k === 'def' ? 3 : 2);
      if (!dashed) api.text(m[k] - L / 2, labelTop && api.flip ? api.geo.W / 2 - 3.2 : -api.geo.W / 2 + 3.2, word, 'lt');
    });
  }

  function card(no, title, block, figures, extra) {
    const head = h('div', { class: 'phh' }, h('span', { class: 'no', text: String(no) }), h('h2', { text: title }));
    const c = h('article', { class: 'card', id: `b${no}` }, head);
    for (const f of figures || []) if (f) c.append(f);
    c.append(h('p', { class: block.judged === false && /부족|기록에 없음|판단하지/.test(block.text || '') ? 'ans nodata' : 'ans', text: block.text || '' }));
    if (block.evidence) c.append(h('p', { class: 'vcap', text: block.evidence }));
    if (extra) c.append(extra);
    return c;
  }

  const legend = items => h('div', { class: 'legend' }, ...items.map(([kind, word]) => {
    const span = h('span');
    const swatch = kind === 'ours' ? 'background:var(--dot-ours, var(--pitch));box-shadow:0 0 0 2px #fff' : kind === 'theirs' ? 'background:var(--dot-theirs, #c8cec9);box-shadow:0 0 0 1px var(--dot-theirs-ring, var(--night))' : `background:var(--${kind})`;
    span.append(kind === 'dash' ? h('u') : kind === 'line' ? h('s') : h('i', { style: swatch }), document.createTextNode(word));
    return span;
  }));

  function empty(geo, word) { const p = pitch(geo, word); p.text(0, 2, word, 'lt'); return fig(p.svg); }

  // ---- the blocks ----------------------------------------------------------------------------------------------------------------------
  function glance(r, b) {
    const list = h('ol', { class: 'rule3' }, ...b.lines.map(x => h('li', {}, h('div', {}, h('div', { text: x.text }), x.evidence ? h('div', { class: 'vcap', text: x.evidence }) : null))));
    const tl = timeline(b);
    const goalLegend = (b.goals || []).length ? legend([['chalk', '우리 골'], ['red', '상대 골']]) : null;
    return card(1, '한눈에', { text: '가장 크게 달라진 세 가지', evidence: `${b.text} · ${b.evidence}` }, [tl, goalLegend], list);
  }

  function timeline(b) {                                     // the half as one band: 초 · 중 · 후 and the goals
    const svg = s('svg', { viewBox: '0 0 360 56', role: 'img', 'aria-label': '전반을 초, 중, 후로 나눈 시간 띠와 골', class: 'mm', style: 'border-radius:0' });
    const cols = ['var(--pitch)', 'var(--pitch)', 'var(--lamp)'];
    b.stretches.forEach((st, i) => {
      svg.append(s('rect', { x: 4 + i * 118, y: 18, width: 114, height: 16, rx: 4, fill: cols[i], 'fill-opacity': '.85' }));
      svg.append(s('text', { x: 61 + i * 118, y: 30, 'text-anchor': 'middle', style: 'font:900 11px var(--body);fill:var(--night)' }, st.name));
      svg.append(s('text', { x: 61 + i * 118, y: 50, 'text-anchor': 'middle', style: 'font:700 10px var(--body);fill:var(--mute)' }, `${st.from_text}~`));
    });
    for (const g of b.goals || []) {
      const x = 4 + 350 * Math.min(1, g.at / Math.max(0.1, b.minutes));
      svg.append(s('line', { x1: x, y1: 10, x2: x, y2: 38, stroke: g.kind === 'goal_ours' ? 'var(--chalk)' : 'var(--red)', 'stroke-width': 3 }));
    }
    return svg;
  }

  function thirds(r, b, geo) {
    const flip = HalftimeFlip.flipFor(r.direction);
    if (!b.judged) return card(2, '시간대별 팀 모양', b, [empty(geo, '자료 부족')]);
    const box = h('div', { class: 'swipe' });
    let prev = null;
    const depths = [];                                       // one zoom for the three pictures so that they compare
    for (const st of b.stretches) if (st.means) { depths.push(st.means.def - geo.L / 2, st.means.att - geo.L / 2); for (const d of st.dots || []) depths.push(d.u); }
    const view = depths.length ? zoom(geo, depths) : null;
    b.stretches.forEach((st, i) => {
      const p = pitch(geo, `${st.name}반 우리 팀 평균 모양`, flip, view, 245);
      p.geo = geo;
      if (st.means) {
        shape(p, st.means, 'var(--pitch)', false, true);
        named(p, st.dots || []);
        if (prev) {
          p.line(prev.def - geo.L / 2, prev.vmax + 2, prev.def - geo.L / 2, prev.vmin - 2, 'dashed', 'var(--lamp)', null, 1.6);
          if (Math.abs(st.means.def - prev.def) >= 1) p.line(prev.def - geo.L / 2, st.means.centre_v, st.means.def - geo.L / 2, st.means.centre_v, 'dashed', 'var(--lamp)', 'am');
        }
        prev = st.means;
      } else p.text(0, 2, '자료 부족', 'lt');
      attack(p, geo);
      const head = h('div', { class: 'phh' }, h('span', { class: 'pchip' + (i === 2 ? ' y' : ''), text: `${r.word} ${st.name}` }), h('span', { class: 'ptime', text: `${st.from_text}~${st.to_text}` }));
      const cap = st.means ? `수비 ${st.means.def.toFixed(0)} m · 폭 ${st.means.width.toFixed(0)} m · 길이 ${st.means.length.toFixed(0)} m (보인 선수 기준, ${Math.round(st.usable / 60)}분/${Math.round(st.seconds / 60)}분)` : `우리 7명 이상 ${st.usable}초 / ${st.seconds}초`;
      box.append(h('figure', {}, head, p.svg, h('figcaption', { text: cap })));
    });
    const extra = h('div', {}, h('p', { class: 'vcap', text: HalftimeFlip.note(r.direction) }), legend([['ours', '점 = 자리별 평균(가운데로 모여 보임)'], ['line', '수·미·공 = 매초 잰 세 줄의 평균'], ['dash', '앞 구간 수비 줄에서 달라진 것']]));
    if (b.names) extra.append(h('p', { class: 'vcap', text: r.names_note }));
    else if (b.roles) extra.append(h('p', { class: 'vcap', text: r.role_note }));
    return card(2, '시간대별 팀 모양', b, [box], extra);
  }

  function lineChart(r, b) {
    const Wd = 360, Ht = 170, L = 30, R = 8, T = 18, B = 26;
    const svg = s('svg', { viewBox: `0 0 ${Wd} ${Ht}`, role: 'img', 'aria-label': '1분마다 수비 줄 높이', class: 'mm', style: 'background:var(--panel2)' });
    const vals = b.points.map(p => p.def), lo = Math.max(0, Math.floor((Math.min(...vals) - 3) / 5) * 5), hi = Math.ceil((Math.max(...vals) + 3) / 5) * 5;
    const X = m => L + (Wd - L - R) * (m + 0.5) / Math.max(1, b.minutes), Y = v => T + (Ht - T - B) * (1 - (v - lo) / Math.max(1, hi - lo));
    for (const v of [lo, (lo + hi) / 2, hi]) {
      svg.append(s('line', { x1: L, y1: Y(v), x2: Wd - R, y2: Y(v), stroke: 'var(--line)', 'stroke-width': 1 }));
      svg.append(s('text', { x: L - 4, y: Y(v) + 4, 'text-anchor': 'end', style: 'font:700 10px var(--body);fill:var(--mute)' }, `${Math.round(v)}`));
    }
    svg.append(s('text', { x: 2, y: 11, style: 'font:700 10px var(--body);fill:var(--mute)' }, '우리 골라인에서 m'));
    for (let m = 0; m < b.minutes - 1; m += 5) svg.append(s('text', { x: X(m) - (Wd - L - R) * 0.5 / Math.max(1, b.minutes), y: Ht - 8, 'text-anchor': 'middle', style: 'font:700 10px var(--body);fill:var(--mute)' }, `${m}분`));
    for (const mk of b.marks) {
      const x = L + (Wd - L - R) * mk.at / Math.max(1, b.minutes), goal = mk.kind.startsWith('goal');
      const colour = mk.kind === 'goal_ours' ? 'var(--chalk)' : mk.kind === 'goal_theirs' ? 'var(--red)' : 'var(--lamp)';
      svg.append(s('line', { x1: x, y1: T, x2: x, y2: Ht - B, stroke: colour, 'stroke-width': goal ? 2.4 : 1.2, 'stroke-dasharray': goal ? '' : '3 3' }));
    }
    let path = '', prev = null;
    for (const p of b.points) { path += `${prev !== null && p.minute === prev + 1 ? 'L' : 'M'}${X(p.minute).toFixed(1)} ${Y(p.def).toFixed(1)}`; prev = p.minute; }
    svg.append(s('path', { d: path, fill: 'none', stroke: 'var(--pitch)', 'stroke-width': 2.4, 'stroke-linejoin': 'round' }));
    for (const p of b.points) svg.append(s('circle', { cx: X(p.minute), cy: Y(p.def), r: 3.2, fill: 'var(--pitch)', stroke: 'var(--night)', 'stroke-width': 1 }));
    return svg;
  }

  function line(r, b, geo) {
    if (!b.judged) return card(3, '수비 줄 높이의 흐름', b, [empty(geo, '자료 부족')]);
    const kinds = new Set(b.marks.map(m => m.kind));
    const items = [['pitch', '수비 줄 높이']];
    if (kinds.has('goal_ours')) items.push(['chalk', '우리 골']);
    if (kinds.has('goal_theirs')) items.push(['red', '상대 골']);
    if ([...kinds].some(k => !k.startsWith('goal'))) items.push(['lamp', '장면 표시(점선)']);
    return card(3, '수비 줄 높이의 흐름', b, [fig(lineChart(r, b))], legend(items));
  }

  function sides(r, b, geo) {
    if (!b.judged) return card(4, '좌우 치우침', b, [empty(geo, '자료 부족')]);
    const flip = HalftimeFlip.flipFor(r.direction);
    const make = (share, colour, who) => {
      const p = pitch(geo, `${who}이 선 쪽 비율`, flip);
      if (share) share.forEach((x, k) => p.band(k, x, colour, `${['왼', '가운데', '오른'][k]} ${Math.round(x)}%`));
      else p.text(0, 2, '판단 안 함', 'lt');
      attack(p, geo);
      return fig(p.svg, who);
    };
    return card(4, '좌우 치우침', b, [h('div', { class: 'two' }, make(b.ours, 'var(--pitch)', '우리'), make(b.theirs, 'var(--red)', '상대'))],
      h('p', { class: 'vcap', text: '왼쪽과 오른쪽은 우리가 공격하는 쪽을 볼 때 기준입니다. 먼 쪽 선수는 덜 잡혀 두 팀 모두 카메라 쪽이 많게 나올 수 있습니다.' }));
  }

  function alerts(r, b, geo) {
    const figures = [], flip = HalftimeFlip.flipFor(r.direction);
    if (b.kinds.length) {
      const top = Math.max(...b.kinds.map(k => k.count));
      figures.push(h('div', { class: 'bars' }, ...b.kinds.slice(0, 5).map(k => h('div', { class: 'row' }, h('span', { text: k.name }), h('div', { class: 'bar', style: `width:${Math.round(100 * k.count / top)}%` }), h('span', { class: 'n', text: String(k.count) })))));
      for (const k of b.kinds.slice(0, 2)) {
        if (!k.moment) continue;
        const p = pitch(geo, `${k.name}의 대표 순간`, flip);
        for (const [u, v] of k.moment.theirs) p.dot(u, v, 'opp');
        for (const [u, v] of k.moment.ours) p.dot(u, v, 'us');
        attack(p, geo);
        const rated = k.ok + k.wrong ? ` · 코치 평가 도움됨 ${k.ok} · 아님 ${k.wrong}` : '';
        figures.push(fig(p.svg, `${k.name} 대표 순간 ${k.moment.at_text} · 초 ${k.stretch[0]} · 중 ${k.stretch[1]} · 후 ${k.stretch[2]}번${rated}`));
      }
    } else figures.push(empty(geo, '알림 없음'));
    return card(5, '알림으로 본 반복 문제', b, figures, b.kinds.length ? h('div', {}, legend([['ours', '굵은 테두리 우리'], ['theirs', '가는 테두리 상대']]), h('p', { class: 'vcap', text: '대표 순간 = 그 종류의 알림 중 두 팀 선수가 가장 많이 보인 순간의 위치(모델 판정). 다시보기 주소는 아직 시각을 받지 못해 넣지 않았습니다.' })) : null);
  }

  function opponent(r, b, geo) {
    const flip = HalftimeFlip.flipFor(r.direction);
    const box = h('div', { class: 'swipe' });
    let any = false;
    const depths = [];
    for (const st of b.stretches) if (st.means) depths.push(geo.L / 2 - st.means.def, geo.L / 2 - st.means.att);
    const view = depths.length ? zoom(geo, depths) : null;
    b.stretches.forEach((st, i) => {
      const p = pitch(geo, `${st.name}반 상대 팀 평균 모양`, flip, view, 245); p.geo = geo;
      if (st.means) {                                        // their lines are metres from their own goal: drawn in our frame
        any = true;
        const m = st.means, L = geo.L, v1 = m.vmin, v2 = m.vmax;
        p.rect(L / 2 - m.def, L / 2 - m.att, v1, v2, 'solid', 'var(--red)');
        [['def', '수'], ['mid', '미'], ['att', '공']].forEach(([k, w]) => { p.line(L / 2 - m[k], v1, L / 2 - m[k], v2, 'solid', 'var(--red)', null, k === 'def' ? 3 : 2); p.text(L / 2 - m[k], flip ? geo.W / 2 - 3.2 : -geo.W / 2 + 3.2, w, 'lt'); });
      } else p.text(0, 2, '판단 안 함', 'lt');
      attack(p, geo);
      const head = h('div', { class: 'phh' }, h('span', { class: 'pchip r', text: `상대 ${st.name}` }), h('span', { class: 'ptime', text: `${st.usable}초/${st.seconds}초` }));
      box.append(h('figure', {}, head, p.svg, st.means ? h('figcaption', { text: `상대 수비 줄 자기 골라인에서 ${st.means.def.toFixed(0)} m · 폭 ${st.means.width.toFixed(0)} m` }) : null));
    });
    const more = h('details', {}, h('summary', { text: '상대 팀 자세히' }));
    const list = h('ul');
    for (const item of (b.summary && b.summary.items) || []) list.append(h('li', { text: `${item.title}: ${item.text}` }));
    more.append(list);
    if (b.delta_text) more.append(h('p', { class: 'vcap', text: b.delta_text }));
    return card(6, '상대 팀', b, [any ? box : empty(geo, '판단 안 함')], more);
  }

  function next(r, b, geo) {
    const flip = b.direction < 0, figures = [];   // map 7 keeps its own turn: the direction of the second half
    for (const item of b.items || []) {
      const m = item.base, d = item.draw, L = geo.L;
      const depths = m ? [m.def - L / 2, m.att - L / 2, ...(item.dots || []).map(x => x.u)] : [0];
      if (m && d.du) depths.push(m[d.group === 'all' ? 'mid' : d.group] - L / 2 + d.du);
      const p = pitch(geo, item.text, flip, zoom(geo, depths), 300); p.geo = geo;
      if (m) {
        shape(p, m, 'var(--pitch)');
        const group = { def: 0, mid: 1, att: 2 }[d.group];
        const moved = { ...m };
        if (d.group === 'all') moved.centre_v = m.centre_v + (d.dv || 0);
        else moved[d.group] = m[d.group] + (d.du || 0);
        if (d.group === 'all') { p.rect(m.def - L / 2, m.att - L / 2, moved.centre_v - m.width / 2, moved.centre_v + m.width / 2, 'dashed', 'var(--lamp)'); p.line(m.mid - L / 2, m.centre_v, m.mid - L / 2, moved.centre_v, 'dashed', 'var(--lamp)', 'am'); }
        else {
          const v1 = m.centre_v - m.width / 2, v2 = m.centre_v + m.width / 2;
          p.line(moved[d.group] - L / 2, v1, moved[d.group] - L / 2, v2, 'dashed', 'var(--lamp)', null, 2.2);
          p.line(m[d.group] - L / 2, m.centre_v, moved[d.group] - L / 2, m.centre_v, 'dashed', 'var(--lamp)', 'am');
        }
        const ghosts = (item.dots || []).filter(dot => d.group === 'all' || dot.line === group).map(dot => [dot.u + (d.group === 'all' ? 0 : d.du || 0), dot.v + (d.group === 'all' ? d.dv || 0 : 0)]);
        named(p, item.dots || [], ghosts);
        for (const dot of item.dots || []) {
          if (d.group === 'all' || dot.line === group) p.dot(dot.u + (d.group === 'all' ? 0 : d.du || 0), dot.v + (d.group === 'all' ? d.dv || 0 : 0), 'us', '', true);
        }
      }
      attack(p, geo, '후반 우리 공격');
      figures.push(h('figure', { class: 'mfig' }, p.svg, h('figcaption', {}, h('b', { class: 'y', text: item.text }), h('br'), document.createTextNode(item.evidence))));
    }
    if (!figures.length) figures.push(empty(geo, b.text || '뚜렷한 문제 없음'));
    const extra = h('div', {}, legend([['line', '실선 = 전반 후반부 실제'], ['dash', '점선 = 권하는 자리']]), h('p', { class: 'vcap', text: b.direction_text }));
    const dots7 = (b.items || []).flatMap(i => i.dots || []);
    if (dots7.some(d => d.name)) extra.append(h('p', { class: 'vcap', text: r.names_note }));
    else if (dots7.some(d => d.role)) extra.append(h('p', { class: 'vcap', text: r.role_note }));
    return card(7, '후반에 할 일', b, figures, extra);
  }

  // the shirt colours of the match (app/team_colour_view.py) as page variables for the dots; a very dark opponent colour gets a light thin ring so that it shows on the grass
  function teamColours(c) {
    const hex = v => (typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v) ? v : null);
    const ours = hex(c && c.ours) || '#40d678', theirs = hex(c && c.theirs) || '#c8cec9';
    const lum = x => { const n = [1, 3, 5].map(i => parseInt(x.slice(i, i + 2), 16) / 255).map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * n[0] + 0.7152 * n[1] + 0.0722 * n[2]; };
    const root = document.documentElement.style;
    root.setProperty('--dot-ours', ours); root.setProperty('--dot-theirs', theirs);
    root.setProperty('--dot-theirs-ring', lum(theirs) < 0.06 ? '#cfe3d4' : '#0b1310');
  }

  function render(r) {
    teamColours(r.team_colours);
    const blocks = el('blocks'); blocks.replaceChildren();
    const b = r.blocks || {};
    el('status').textContent = r.status_text || '';
    if (b.glance && b.glance.score) el('score').textContent = `${b.glance.score.ours} : ${b.glance.score.opp}`;
    const geo = { L: r.length || 89, W: r.width || 62 };
    if (r.state === 'not_started') {                         // the analysis runs from the warm-up on: nothing is counted before "전반 시작"
      blocks.append(h('section', { class: 'state' }, h('p', { text: r.status_text || '전반 시작을 누르면 집계가 시작됩니다' })));
      el('old').hidden = true;
      return;
    }
    if (r.state === 'empty' || !b.glance || !b.glance.stretches) {
      const word = r.status_text || '아직 위치 기록이 없습니다.';
      for (const [no, title] of [[1, '한눈에'], [2, '시간대별 팀 모양'], [3, '수비 줄 높이의 흐름'], [4, '좌우 치우침'], [5, '알림으로 본 반복 문제'], [6, '상대 팀'], [7, '후반에 할 일']])
        blocks.append(card(no, title, { judged: false, text: '기록에 없음', evidence: word }, [empty(geo, '기록 없음')]));
      return;
    }
    const make = [() => glance(r, b.glance), () => thirds(r, b.thirds, geo), () => line(r, b.line, geo), () => sides(r, b.sides, geo), () => alerts(r, b.alerts, geo), () => opponent(r, b.opponent, geo), () => next(r, b.next, geo)];
    make.forEach((f, i) => {
      try { blocks.append(f()); } catch (e) { blocks.append(card(i + 1, '항목', { judged: false, text: '이 항목을 그리지 못했습니다' }, [])); }
    });
  }

  async function old(name) {                                     // the earlier text report, kept below (direction and colour checks for the second half)
    if (!name) return;
    try {
      const response = await fetch(`/api/v1/halftime/report?session=${encodeURIComponent(name)}&half=${half}`, { cache: 'no-store' });
      if (!response.ok) return;
      const r = await response.json();
      // only the two checks (direction, team colours): the older sums start with the first analysed second, warm-up included, so their numbers are not shown here
      const checks = (r.second_half || []).filter(t => /^(공격 방향 확인|팀 색 재확인)/.test(t));
      el('old-second').replaceChildren(...checks.map(t => h('li', { text: t })));
      el('old').hidden = !checks.length;
    } catch (e) { /* optional */ }
  }

  async function load(mine = generation) {
    if (mine !== generation) return;                         // another half was chosen meanwhile: this round is over
    const started = Date.now();
    el('busy').hidden = false;
    const again = (ms) => setTimeout(() => load(mine), ms);
    try {
      const response = await fetch(`/api/v1/halftime/rich?${session ? `session=${encodeURIComponent(session)}&` : ''}half=${half}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(String(response.status));
      const r = await response.json();
      if (mine !== generation) return;
      const key = `${half}|${r.end_s}|${r.state}|${r.generated_at}`;
      if (key !== lastKey) { render(r); lastKey = key; }
      el('busy').hidden = true;
      if (r.state === 'running') again(15000);
      else if (r.state === 'empty' || r.state === 'not_started') again(10000);
      if (r.state === 'final' || r.state === 'running') old(r.session);
    } catch (e) {
      if (mine !== generation) return;
      el('busy-text').textContent = '보고서를 아직 받지 못했습니다. 잠시 뒤 다시 시도합니다.';
      again(Math.max(3000, 8000 - (Date.now() - started)));
    }
  }

  // "전반" / "후반" at the top once the second half has started (the "후반 시작" mark of /api/v1/clock). The second half runs from that mark to "후반 종료"
  // (or now) with the second-half attack direction (app/halftime_rich.half_range). Opened by default: the second half after its start, else the first.
  function choose(value) {
    half = value; generation += 1; lastKey = '';
    for (const n of [1, 2]) { const b = el(`half-${n}`); b.setAttribute('aria-pressed', String(n === half)); b.classList.toggle('is-primary', n === half); }
    const next = new URLSearchParams(location.search); next.set('half', String(half));
    try { history.replaceState(null, '', `${location.pathname}?${next}`); } catch (e) { /* the address stays */ }
    el('blocks').replaceChildren(); el('old').hidden = true; el('status').textContent = '보고서 만드는 중';
    load(generation);
  }
  el('half-1').addEventListener('click', () => choose(1));
  el('half-2').addEventListener('click', () => choose(2));
  async function start() {
    let second = false;
    try {
      const clock = await fetch('/api/v1/clock', { cache: 'no-store' }).then(r => r.json());
      second = (clock.marks || []).includes('start_h2');
    } catch (e) { /* no clock: the first half only, as before */ }
    el('half-pick').hidden = !second && half !== 2;
    choose(asked === '1' || asked === '2' ? half : (second ? 2 : 1));
  }
  start();
})();
