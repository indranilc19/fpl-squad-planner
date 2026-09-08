const FPL_ANALYSIS = (() => {
  const POSITIONS = ['GK', 'DEF', 'MID', 'FWD'];

  function load() {
    return fetch('data/analysis.json', { cache: 'no-store' }).then(r => {
      if (!r.ok) throw new Error('Analysis dataset unavailable');
      return r.json();
    });
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>\"']/g, c => ({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', '\"':'&quot;', "'":'&#39;'
    }[c]));
  }

  function fixtureClass(diff) {
    return diff <= 2 ? 'easy' : diff === 3 ? 'medium' : 'hard';
  }

  function renderFixture(f) {
    const title = `${f.opponent} ${f.home ? 'Home' : 'Away'} · FDR ${f.difficulty} · historical ${Number(f.historical_ppg ?? 0).toFixed(1)} pts/match · ${f.historical_matches || 0} meeting${f.historical_matches === 1 ? '' : 's'}`;
    return `<span class="analysis-fixture ${fixtureClass(Number(f.difficulty))}" title="${escapeHtml(title)}"><b>GW${f.gw}</b> ${escapeHtml(f.opponent)} <strong>${f.home ? 'H' : 'A'}</strong><small>${Number(f.historical_ppg ?? 0).toFixed(1)}</small></span>`;
  }

  function render(container, dataset, onSelect) {
    if (!container) return;
    const players = dataset.players || [];
    const quota = dataset.top30_quota || { GK: 4, DEF: 10, MID: 10, FWD: 6 };
    const byPos = POSITIONS.reduce((acc, pos) => {
      acc[pos] = players.filter(p => p.position === pos);
      return acc;
    }, {});

    container.innerHTML = `
      <div class="analysis-card">
        <div class="analysis-head">
          <div>
            <h2>Top 30 — Fixture-aware Historical Analysis</h2>
            <p>Position-balanced shortlist, with the <strong>next five fixtures</strong> and each player's historical performance against those opponents.</p>
          </div>
          <div class="analysis-meta">${escapeHtml(dataset.historical_seasons?.join(' · ') || '')}</div>
        </div>
        <div class="ratio-bar">
          ${POSITIONS.map(pos => `<span><b>${pos}</b> ${quota[pos] || 0}</span>`).join('')}
        </div>
        <div class="analysis-note">
          <strong>How fixture context works:</strong> each player's score now includes the current FPL difficulty of the next five matches <em>and</em> their historical GW points against those exact opponents. Home/away is explicitly separated, with small venue samples shrunk toward the broader opponent record.
        </div>
        <div class="analysis-legend">
          <span><b>H/A</b> = home/away</span>
          <span><b>FDR</b> = current fixture difficulty (1 easiest → 5 hardest)</span>
          <span><b>number</b> inside fixture = historical FPL pts/match vs that opponent/venue</span>
        </div>
        ${POSITIONS.map(pos => `
          <section class="analysis-role">
            <div class="analysis-role-title"><h3>${pos}</h3><span>${byPos[pos].length} players</span></div>
            <div class="analysis-table-wrap">
              <table class="analysis-table">
                <thead><tr>
                  <th>Rank</th><th>Player</th><th>Team</th><th>£m</th><th>Score</th><th>Form</th><th>Next 5 fixtures</th><th>Hist matchup</th><th>FDR</th><th>Confidence</th><th>Reasoning snapshot</th>
                </tr></thead>
                <tbody>
                  ${byPos[pos].map(p => `
                    <tr data-analysis-player="${p.id}">
                      <td class="rank">#${p.position_rank}</td>
                      <td><button class="analysis-player" data-analysis-select="${p.id}">${escapeHtml(p.web_name || p.second_name)}</button></td>
                      <td>${escapeHtml(p.team)}</td>
                      <td>${Number(p.price ?? 0).toFixed(1)}</td>
                      <td><strong>${Number(p.score ?? 0).toFixed(1)}</strong></td>
                      <td>${Number(p.form ?? 0).toFixed(1)}</td>
                      <td><div class="analysis-fixtures">${(p.next_fixtures || []).map(renderFixture).join('') || '<span class="notice">No upcoming fixtures</span>'}</div></td>
                      <td><strong>${Number(p.matchup_ppg ?? 0).toFixed(1)}</strong><div class="analysis-mini">pts/match</div></td>
                      <td>${Number(p.fixture_avg ?? 3).toFixed(2)}</td>
                      <td><span class="confidence ${String(p.confidence || '').toLowerCase()}">${escapeHtml(p.confidence)}</span></td>
                      <td><div class="reasons">${(p.reasons || []).map(r => `<span>${escapeHtml(r)}</span>`).join('')}</div></td>
                    </tr>`).join('')}
                </tbody>
              </table>
            </div>
          </section>`).join('')}
        <details class="analysis-method">
          <summary>How the engine scores players</summary>
          <p>The next five fixtures are not just a generic FDR average. For every fixture, the engine looks at the player's historical GW records against that opponent, then checks whether those historical meetings were at home or away. The five fixture-specific historical averages are combined into a matchup signal.</p>
          <p>Venue-specific history is Bayesian-shrunk toward the player's broader record against that opponent, so a single old home/away meeting cannot overpower a larger sample. The matchup signal is then ranked within position and given the largest single weight in the fixture-aware model.</p>
          <p>Historical seasons are weighted 50% 2024–25, 30% 2023–24 and 20% 2022–23. 2024–25 GW22–38 are excluded from matchup history because the source dataset documents incorrect total_points values for those gameweeks. Historical xP/ep fields are excluded because they may contain lookahead information.</p>
          <p>Generated: ${escapeHtml(dataset.generated_at || 'unknown')}</p>
          ${(dataset.warnings || []).length ? `<p><strong>Data warnings:</strong> ${dataset.warnings.map(escapeHtml).join(' · ')}</p>` : ''}
        </details>
      </div>`;

    container.querySelectorAll('[data-analysis-select]').forEach(btn => {
      btn.addEventListener('click', () => {
        const player = players.find(p => String(p.id) === String(btn.dataset.analysisSelect));
        if (player && typeof onSelect === 'function') onSelect(player);
      });
    });
  }

  return { load, render };
})();

// Auto-load the configured FPL manager's current selection into the planner.
(() => {
  const DEFAULT_TEAM_ID = '2160927';
  const AUTO_KEY = 'fpl-squad-planner:auto-team:v1';

  function clickWhenReady(selector, timeout = 15000) {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = () => {
        const el = document.querySelector(selector);
        if (el) return resolve(el);
        if (Date.now() - started > timeout) return reject(new Error(`Timed out waiting for ${selector}`));
        setTimeout(tick, 100);
      };
      tick();
    });
  }

  async function loadConfiguredTeam() {
    try {
      const myTeamNav = await clickWhenReady('[data-view="myteam"]');
      myTeamNav.click();
      const input = await clickWhenReady('#teamId');
      input.value = DEFAULT_TEAM_ID;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      const loadButton = await clickWhenReady('#loadTeam');
      loadButton.click();
      const loadInto = await clickWhenReady('#loadInto', 20000);
      loadInto.click();
      sessionStorage.setItem(AUTO_KEY, DEFAULT_TEAM_ID);
    } catch (err) {
      console.warn('[FPL Squad Planner] Automatic team load skipped:', err.message);
    }
  }

  if (!sessionStorage.getItem(AUTO_KEY)) {
    window.addEventListener('load', () => setTimeout(loadConfiguredTeam, 150));
  }
})();
