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
    return `<span class="analysis-fixture ${fixtureClass(Number(f.difficulty))}" title="${escapeHtml(title)}"><b>GW${f.gw}</b><span>${escapeHtml(f.opponent)}</span><strong>${f.home ? 'H' : 'A'}</strong><small>${Number(f.historical_ppg ?? 0).toFixed(1)}</small></span>`;
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
          <strong>How fixture context works:</strong> each player's score includes current FPL difficulty for the next five matches and historical GW points against those exact opponents. Home/away is explicitly separated, with small venue samples shrunk toward the broader opponent record.
        </div>
        <div class="analysis-legend">
          <span><b>H/A</b> = home/away</span>
          <span><b>FDR</b> = current fixture difficulty (1 easiest → 5 hardest)</span>
          <span><b>number</b> = historical FPL pts/match vs that opponent/venue</span>
        </div>
        ${POSITIONS.map(pos => `
          <section class="analysis-role">
            <div class="analysis-role-title"><h3>${pos}</h3><span>${byPos[pos].length} players</span></div>
            <div class="analysis-table-wrap">
              <table class="analysis-table">
                <colgroup><col class="c-rank"><col class="c-player"><col class="c-team"><col class="c-price"><col class="c-score"><col class="c-form"><col class="c-fixtures"><col class="c-matchup"><col class="c-fdr"><col class="c-confidence"><col class="c-reason"></colgroup>
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

// Planner enhancements: five rolling team scenarios + a 1–5 GW transfer/hold plan.
(() => {
  const PLANS_KEY = 'fpl-squad-planner:team-plans:v1';
  const TRANSFERS_KEY = 'fpl-squad-planner:transfer-plan:v1';
  const SQUAD_KEY = 'fpl-squad-planner:v2';
  const META_KEY = 'fpl-squad-planner:meta:v2';
  const PLAN_COUNT = 5;
  let lastGw = null;

  const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); } catch (_) { return fallback; } };
  const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {} };
  const squad = () => read(SQUAD_KEY, []);
  const meta = () => read(META_KEY, {});
  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const gw = () => { const m = (document.querySelector('.gw-label')?.textContent || '').match(/\d+/); return Number(m?.[0]) || lastGw || 1; };
  const getPlans = () => { const raw = read(PLANS_KEY, []); return Array.from({length:PLAN_COUNT}, (_,i) => raw[i] || {squad:[],cap:null,vice:null,formation:'4-4-2'}); };
  const getTransfers = () => { const x = read(TRANSFERS_KEY, {horizon:1,weeks:{}}); return {horizon:Math.min(5,Math.max(1,Number(x.horizon)||1)),weeks:x.weeks||{}}; };
  const pName = id => (window.__FPL_PLANNER_PLAYERS || []).find(p => Number(p.id) === Number(id))?.second_name || `#${id}`;
  const toast = text => { const t=document.getElementById('toast'); if(!t)return; t.textContent=text; t.classList.remove('hidden'); clearTimeout(window.__planToast); window.__planToast=setTimeout(()=>t.classList.add('hidden'),2200); };

  function ensurePlans() {
    const p = getPlans();
    if (!p[0].squad.length && squad().length) { p[0] = {...p[0], squad:squad(), ...meta(), savedGw:gw()}; write(PLANS_KEY,p); }
    return p;
  }

  function savePlan(i) {
    const p=ensurePlans(); p[i]={squad:squad(),...meta(),savedGw:gw()}; write(PLANS_KEY,p); renderHub(); toast(`Saved Team Plan ${i+1}`);
  }
  function loadPlan(i) {
    const p=ensurePlans()[i]; if(!p.squad?.length){toast(`Team Plan ${i+1} is empty`);return;}
    write(SQUAD_KEY,p.squad); write(META_KEY,{formation:p.formation||'4-4-2',cap:p.cap||null,vice:p.vice||null}); location.reload();
  }
  function copyPlan(i) {
    const p=ensurePlans(), j=i+1; if(j>=PLAN_COUNT)return; p[j]={...p[i],squad:[...(p[i].squad||[])],savedGw:gw()+1}; write(PLANS_KEY,p); renderHub(); toast(`Copied Plan ${i+1} → ${j+1}`);
  }

  function renderHub() {
    const main=document.getElementById('main'), toolbar=main?.querySelector('.toolbar');
    if(!main||!toolbar||!main.querySelector('#prev'))return;
    let hub=main.querySelector('#plannerPlanHub'); if(!hub){hub=document.createElement('section');hub.id='plannerPlanHub';hub.className='planner-plan-hub';toolbar.insertAdjacentElement('afterend',hub);}
    const base=gw(); lastGw=base; const plans=ensurePlans(), tr=getTransfers();
    const weeks=Array.from({length:tr.horizon},(_,i)=>base+i);
    const outOptions=squad().map(id=>`<option value="${id}">${esc(pName(id))}</option>`).join('');
    const inOptions=(window.__FPL_PLANNER_PLAYERS||[]).slice().sort((a,b)=>String(a.second_name).localeCompare(String(b.second_name))).map(p=>`<option value="${p.id}">${esc(p.second_name)}${p.team_name?' · '+esc(p.team_name):''}</option>`).join('');
    const planned=weeks.filter(g=>(tr.weeks[String(g)]||{}).action==='plan').length;

    hub.innerHTML=`<div class="planner-plan-head"><div><strong>Team scenarios</strong><span>Five saved squads, rolling from the current GW. Plan 1 = GW${base}, Plan 2 = GW${base+1} … Plan 5 = GW${base+4}.</span></div><div class="planner-horizon"><label>Transfer horizon</label><select id="transferHorizon">${[1,2,3,4,5].map(n=>`<option value="${n}" ${n===tr.horizon?'selected':''}>${n} GW${n===1?'':'s'}</option>`).join('')}</select></div></div>
      <div class="planner-plan-grid">${plans.map((p,i)=>{const count=p.squad?.length||0;return `<article class="planner-plan-slot ${i===0?'current':''}"><div class="plan-slot-top"><div><b>Plan ${i+1}</b><span>GW${base+i}</span></div><em>${count}/15</em></div><div class="plan-slot-state">${count?`${esc(pName(p.squad[0]))}${count>1?' + '+(count-1)+' more':''}`:'Empty — save a scenario here'}</div><div class="plan-slot-actions"><button class="btn" data-plan-save="${i}">Save current</button><button class="btn" data-plan-load="${i}" ${count?'':'disabled'}>Load</button><button class="btn" data-plan-copy="${i}" ${count&&i<4?'':'disabled'}>Copy →</button></div></article>`;}).join('')}</div>
      <div class="transfer-planner"><div class="transfer-plan-head"><div><strong>Transfer / Hold plan</strong><span>Select 1–5 gameweeks, then decide whether to hold or plan a transfer for each week. This is a planning layer — it does not change your live FPL account.</span></div><button class="btn" id="clearTransferPlan">Clear</button></div><div class="transfer-plan-rows">${weeks.map(g=>{const w=tr.weeks[String(g)]||{action:'hold',out:'',in:''};return `<div class="transfer-week" data-transfer-week="${g}"><div class="transfer-week-label"><b>GW${g}</b><span>${g===base?'Current':'Future'}</span></div><select class="transfer-action" data-transfer-action="${g}"><option value="hold" ${w.action==='hold'?'selected':''}>Hold</option><option value="plan" ${w.action==='plan'?'selected':''}>Plan transfer</option></select><select class="transfer-out" ${w.action==='plan'?'':'disabled'}><option value="">Player OUT</option>${outOptions}</select><select class="transfer-in" ${w.action==='plan'?'':'disabled'}><option value="">Player IN</option>${inOptions}</select></div>`;}).join('')}</div><div class="transfer-plan-foot"><span>${planned} planned · ${weeks.length-planned} hold</span><button class="btn primary" id="saveTransferPlan">Save transfer plan</button></div></div>`;

    hub.querySelector('#transferHorizon')?.addEventListener('change',e=>{const x=getTransfers();x.horizon=Number(e.target.value);write(TRANSFERS_KEY,x);renderHub();});
    hub.querySelectorAll('[data-plan-save]').forEach(b=>b.onclick=()=>savePlan(Number(b.dataset.planSave)));
    hub.querySelectorAll('[data-plan-load]').forEach(b=>b.onclick=()=>loadPlan(Number(b.dataset.planLoad)));
    hub.querySelectorAll('[data-plan-copy]').forEach(b=>b.onclick=()=>copyPlan(Number(b.dataset.planCopy)));
    hub.querySelectorAll('.transfer-action').forEach(a=>a.onchange=e=>{const row=e.target.closest('.transfer-week');const on=e.target.value==='plan';row.querySelector('.transfer-out').disabled=!on;row.querySelector('.transfer-in').disabled=!on;});
    hub.querySelector('#clearTransferPlan')?.addEventListener('click',()=>{write(TRANSFERS_KEY,{horizon:tr.horizon,weeks:{}});renderHub();toast('Transfer plan cleared');});
    hub.querySelector('#saveTransferPlan')?.addEventListener('click',()=>{const weeksOut={};hub.querySelectorAll('.transfer-week').forEach(row=>{const g=row.dataset.transferWeek;weeksOut[g]={action:row.querySelector('.transfer-action').value,out:row.querySelector('.transfer-out').value,in:row.querySelector('.transfer-in').value};});write(TRANSFERS_KEY,{horizon:Number(hub.querySelector('#transferHorizon').value),weeks:weeksOut});toast('Transfer / hold plan saved');});
  }

  function injectStyles(){
    if(document.getElementById('fpl-enhancement-style'))return;
    const style=document.createElement('style');style.id='fpl-enhancement-style';style.textContent=`
      .analysis-table{min-width:1450px;table-layout:fixed}.analysis-table .c-rank{width:58px}.analysis-table .c-player{width:125px}.analysis-table .c-team{width:52px}.analysis-table .c-price{width:48px}.analysis-table .c-score{width:58px}.analysis-table .c-form{width:52px}.analysis-table .c-fixtures{width:350px}.analysis-table .c-matchup{width:82px}.analysis-table .c-fdr{width:52px}.analysis-table .c-confidence{width:82px}.analysis-table .c-reason{width:260px}.analysis-table th,.analysis-table td{padding:8px 9px;white-space:nowrap}.analysis-table td:nth-child(7),.analysis-table td:last-child{white-space:normal}.analysis-fixtures{display:flex;gap:5px;min-width:330px;overflow:hidden}.analysis-fixture{display:grid;grid-template-columns:auto 1fr auto;grid-template-rows:auto auto;align-items:center;column-gap:4px;min-width:62px;max-width:70px;padding:5px 6px;border-radius:6px;font-size:8px;line-height:1.15;border:1px solid transparent;flex:0 0 62px}.analysis-fixture span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.analysis-fixture small{grid-column:1/-1;margin-top:2px;font-size:8px;font-weight:800}.analysis-fixture.easy{border-color:#bbf7d0}.analysis-fixture.medium{border-color:#fde68a}.analysis-fixture.hard{border-color:#fecaca}.analysis-mini{font-size:8px;color:#94a3b8;margin-top:2px}.reasons{max-width:245px;gap:3px}.reasons span{font-size:8px}.planner-plan-hub{background:#fff;border:1px solid var(--line);border-radius:13px;padding:14px;margin:0 0 14px}.planner-plan-head,.transfer-plan-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.planner-plan-head strong,.transfer-plan-head strong{font-size:13px}.planner-plan-head span,.transfer-plan-head span{display:block;color:var(--muted);font-size:10px;margin-top:3px;line-height:1.4}.planner-horizon{display:flex;align-items:center;gap:7px;font-size:10px;font-weight:800}.planner-horizon select{border:1px solid var(--line);border-radius:8px;padding:7px 9px;background:#fff;font-size:11px;font-weight:800}.planner-plan-grid{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:7px;margin-top:12px}.planner-plan-slot{border:1px solid var(--line);border-radius:9px;padding:9px;background:#fafafa;min-width:0}.planner-plan-slot.current{border-color:#bfdbfe;background:#f8fbff}.plan-slot-top{display:flex;justify-content:space-between;gap:7px;align-items:flex-start}.plan-slot-top b{font-size:10px}.plan-slot-top span{display:inline-block;margin-left:5px;color:var(--blue);font-size:9px;font-weight:800}.plan-slot-top em{font-style:normal;font-size:9px;color:var(--muted)}.plan-slot-state{font-size:9px;color:#475569;min-height:30px;margin:7px 0;line-height:1.35}.plan-slot-actions{display:flex;gap:4px;flex-wrap:wrap}.plan-slot-actions .btn{font-size:8px;padding:6px 7px}.transfer-planner{margin-top:14px;border-top:1px solid var(--line);padding-top:13px}.transfer-plan-rows{display:grid;gap:6px;margin-top:10px}.transfer-week{display:grid;grid-template-columns:70px 145px minmax(130px,1fr) minmax(130px,1fr);gap:6px;align-items:center}.transfer-week-label b{font-size:10px}.transfer-week-label span{display:block;font-size:8px;color:var(--muted);margin-top:2px}.transfer-week select{width:100%;border:1px solid var(--line);background:#fff;border-radius:7px;padding:7px 8px;font-size:9px;min-width:0}.transfer-week select:disabled{background:#f8fafc;color:#94a3b8}.transfer-plan-foot{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:10px}.transfer-plan-foot span{font-size:9px;color:var(--muted)}@media(max-width:900px){.planner-plan-grid{grid-template-columns:repeat(2,minmax(150px,1fr))}.planner-plan-head,.transfer-plan-head{flex-direction:column}.transfer-week{grid-template-columns:65px 1fr 1fr}.analysis-table{min-width:1320px}}@media(max-width:560px){.planner-plan-grid{grid-template-columns:1fr}.transfer-week{grid-template-columns:60px 1fr}.transfer-week .transfer-out,.transfer-week .transfer-in{grid-column:2}.analysis-table{min-width:1200px}.analysis-fixtures{min-width:300px}}
    `;document.head.appendChild(style);
  }

  function watch(){
    injectStyles();
    const main=document.getElementById('main');if(!main)return;
    const observer=new MutationObserver(()=>{if(main.querySelector('.toolbar #prev')&&!main.querySelector('#plannerPlanHub'))renderHub();});
    observer.observe(main,{childList:true,subtree:true});
    setTimeout(()=>{if(main.querySelector('.toolbar #prev'))renderHub();},300);
  }

  fetch('data/players.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(data=>{if(!data)return;window.__FPL_PLANNER_PLAYERS=(data.players||[]).map(p=>({...p,team_name:(data.teams||[]).find(t=>t.id===p.team)?.short_name||''}));}).catch(()=>{});
  if(document.readyState==='loading')window.addEventListener('DOMContentLoaded',watch,{once:true});else watch();
})();
