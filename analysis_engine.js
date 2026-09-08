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
            <h2>Top 30 — Historical + Current Analysis</h2>
            <p>Position-balanced shortlist using the legal FPL squad ratio <strong>2:5:5:3</strong>.</p>
          </div>
          <div class="analysis-meta">${escapeHtml(dataset.historical_seasons?.join(' · ') || '')}</div>
        </div>
        <div class="ratio-bar">
          ${POSITIONS.map(pos => `<span><b>${pos}</b> ${quota[pos] || 0}</span>`).join('')}
        </div>
        <div class="analysis-note">
          Scores are transparent decision-support scores, not official FPL projections. The engine uses historical performance, current form, value, next-five fixture difficulty, minutes profile and availability.
        </div>
        ${POSITIONS.map(pos => `
          <section class="analysis-role">
            <div class="analysis-role-title"><h3>${pos}</h3><span>${byPos[pos].length} players</span></div>
            <div class="analysis-table-wrap">
              <table class="analysis-table">
                <thead><tr>
                  <th>Rank</th><th>Player</th><th>Team</th><th>£m</th><th>Score</th><th>Form</th><th>Hist pts</th><th>Next 5 FDR</th><th>Confidence</th><th>Reasoning snapshot</th>
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
                      <td>${Number(p.historical_points ?? 0).toFixed(0)}</td>
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
          <p>Features are ranked within each position, then combined using role-specific weights. Historical seasons are weighted 50% 2024–25, 30% 2023–24 and 20% 2022–23 when available. Missing historical seasons reduce confidence rather than creating synthetic values.</p>
          <p>FPL's legal squad ratio is preserved by taking 4 GK, 10 DEF, 10 MID and 6 FWD for the Top 30 shortlist. The engine intentionally avoids the historical dataset's scraped xP/ep fields because the source repository documents possible lookahead bias.</p>
          <p>Generated: ${escapeHtml(dataset.generated_at || 'unknown')}</p>
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
// The FPL endpoint returns the current gameweek picks, so after GW3 this is the
// squad selected for the current/post-GW3 gameweek rather than a hard-coded XI.
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
