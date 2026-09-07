// Vercel serverless function — proxies personal FPL data server-side, since
// these endpoints (keyed by team ID) can't be pre-baked into a static file
// the way the shared player list can, and the FPL API has no browser CORS
// headers for a direct client-side call.

module.exports = async (req, res) => {
  const id = String(req.query.id || '').trim();

  if (!/^\d+$/.test(id)) {
    res.status(400).json({ error: 'Enter a numeric FPL team ID.' });
    return;
  }

  try {
    const entryRes = await fetch(`https://fantasy.premierleague.com/api/entry/${id}/`);
    if (!entryRes.ok) {
      res.status(404).json({ error: 'No team found with that ID.' });
      return;
    }
    const entry = await entryRes.json();
    const currentEvent = entry.current_event;

    let picks = null;
    if (currentEvent) {
      const picksRes = await fetch(
        `https://fantasy.premierleague.com/api/entry/${id}/event/${currentEvent}/picks/`
      );
      if (picksRes.ok) picks = await picksRes.json();
    }

    // Gameweek-by-gameweek score history for the season so far — powers
    // the History section. Public, no auth needed, same entry ID.
    let history = null;
    const historyRes = await fetch(`https://fantasy.premierleague.com/api/entry/${id}/history/`);
    if (historyRes.ok) history = await historyRes.json();

    res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300');
    res.status(200).json({ entry, picks, history });
  } catch (err) {
    res.status(502).json({ error: 'Could not reach the FPL API right now. Try again shortly.' });
  }
};
