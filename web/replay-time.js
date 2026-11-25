// Pure time arithmetic of the replay page (no page, no clock): the match time is the recorded time, the pieces laid one after another.
// A piece: {offset, duration, start}. offset = recorded seconds before it, start = wall-clock epoch of its first frame.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api; else root.ReplayTime = api;
})(typeof self !== 'undefined' ? self : this, function () {
  const GAP_MIN = 3;                     // seconds of wall-clock hole between two pieces that count as a break of the recording (file names are whole seconds)
  const END_MARGIN = 0.5;                // a jump never lands closer than this to the very end

  const total = pieces => pieces.length ? pieces[pieces.length - 1].offset + pieces[pieces.length - 1].duration : 0;
  const clamp = (t, pieces) => Math.min(Math.max(0, +t || 0), Math.max(0, total(pieces) - END_MARGIN));

  // match time -> {index, local}: the piece that holds t (a time exactly on a boundary belongs to the next piece) and the time inside it
  function locate(pieces, t) {
    if (!pieces.length) return { index: 0, local: 0 };
    t = clamp(t, pieces);
    let index = 0;
    for (let k = 0; k < pieces.length; k++) if (pieces[k].offset <= t) index = k;
    return { index, local: Math.max(0, t - pieces[index].offset) };
  }

  // piece and time inside it -> match time. The last piece may still be written (its length is an estimate), so only the others are cut at their end.
  function toGlobal(pieces, index, local) {
    if (!pieces.length) return 0;
    const p = pieces[Math.min(Math.max(0, index), pieces.length - 1)];
    const inside = Math.max(0, +local || 0);
    const last = p === pieces[pieces.length - 1];
    return p.offset + (last ? inside : Math.min(inside, p.duration));
  }

  // the breaks of the recording: [{at, seconds}], at = match time of the break (the end of the piece before it)
  function gaps(pieces) {
    const out = [];
    for (let k = 1; k < pieces.length; k++) {
      const hole = pieces[k].start - (pieces[k - 1].start + pieces[k - 1].duration);
      if (hole >= GAP_MIN) out.push({ at: pieces[k].offset, seconds: hole });
    }
    return out;
  }

  // a step of `delta` seconds from t, over any piece boundary
  const step = (pieces, t, delta) => clamp(t + delta, pieces);

  return { GAP_MIN, END_MARGIN, total, clamp, locate, toGlobal, gaps, step };
});
