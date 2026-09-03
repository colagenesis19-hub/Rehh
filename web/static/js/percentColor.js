// web/static/js/percentColor.js
// Input p: 0..100
function percentToHexColor(p) {
  p = Math.max(0, Math.min(100, Number(p) || 0));
  const r = Math.round(255 * (1 - p / 100));
  const g = Math.round(255 * (p / 100));
  const b = 0;
  function toHex(v) {
    return ('0' + v.toString(16)).slice(-2);
  }
  return '#' + toHex(r) + toHex(g) + toHex(b);
}

if (typeof module !== 'undefined') module.exports = { percentToHexColor };
