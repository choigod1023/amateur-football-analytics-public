/* Display colours only: choosing a colour does not change team classification. */
(function (root) {
  const defaults = Object.freeze({home: '#c5e773', away: '#f1ae82'});
  const normalize = value => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : null;
  function rgb(hex) { const color = normalize(hex); return color ? [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)) : null; }
  function similar(home, away) {
    const a = rgb(home), b = rgb(away);
    if (!a || !b) return false;
    return Math.hypot(...a.map((value, i) => value - b[i])) < 85;
  }
  function foreground(hex) {
    const c = rgb(hex);
    if (!c) return '#101614';
    const lum = c.map(v => { const x = v / 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2] > 0.179 ? '#111811' : '#ffffff';
  }
  function resolveColors(settings, server) {
    const home = normalize(settings?.home), away = normalize(settings?.away);
    if (settings?.mode === 'manual' && home && away) return {home, away, source:'manual', similar:similar(home,away)};
    const remoteHome = normalize(server?.home), remoteAway = normalize(server?.away);
    if (remoteHome && remoteAway) return {home:remoteHome,away:remoteAway,source:'server',similar:similar(remoteHome,remoteAway)};
    return {...defaults,source:'default',similar:false};
  }
  const api = {defaults, normalize, similar, foreground, resolveColors};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.TeamColors = api;
})(typeof window !== 'undefined' ? window : globalThis);
