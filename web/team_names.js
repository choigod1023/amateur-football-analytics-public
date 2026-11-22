// Team names on a screen from the team colour profile the coach chose on /team-select.
// Elements marked data-team-name="A" or "B" (B = own team, A = opponent, as in every tracking file) get "우리 팀(파란색 옷)" / "상대 팀(...)".
// Without a profile, or when the request fails, the text written in the page stays (the old "B (어두운 옷)"). This script changes only the words shown to the coach, never a value.
(function () {
  function apply(profile) {
    if (!profile || !profile.own_colour) return;
    var words = { B: '우리 팀(' + profile.own_colour + ' 옷)', A: '상대 팀(' + profile.opponent_colour + ' 옷)' };
    var nodes = document.querySelectorAll('[data-team-name]');
    for (var i = 0; i < nodes.length; i++) {
      var letter = nodes[i].getAttribute('data-team-name');
      if (words[letter]) nodes[i].textContent = words[letter];
    }
  }
  function run() {
    fetch('/api/v1/team-select', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) { if (data) apply(data.profile); })
      .catch(function () {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
