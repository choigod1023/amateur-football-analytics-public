/* Detect an unchanged source timestamp; this does not measure end-to-end delay. */
(function (root) {
  class TimestampWatch {
    constructor(maxUnchangedMs = 10000) { this.maxUnchangedMs = maxUnchangedMs; this.reset(); }
    reset() { this.last = null; this.changedAt = null; }
    check(timestamp, nowMs) {
      if (typeof timestamp !== 'string' || !timestamp.trim()) { this.reset(); return 'unknown'; }
      if (timestamp !== this.last) { this.last = timestamp; this.changedAt = nowMs; return 'updating'; }
      return nowMs - this.changedAt >= this.maxUnchangedMs ? 'stale' : 'updating';
    }
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { TimestampWatch };
  else root.TimestampWatch = TimestampWatch;
})(typeof window !== 'undefined' ? window : globalThis);
