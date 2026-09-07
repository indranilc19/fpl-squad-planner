// Vercel serverless function — runs on Vercel's servers, not the browser.
// The FPL entry/picks endpoints are personal (keyed by team ID) and can't be
// pre-fetched for everyone the way data/players.json is, so this proxies each
// request live: browser -> this same-origin function -> FPL API server-side
// (no CORS, since it's a server-to-server call) -> back to the browser.

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

    // Short cache: personal data changes with transfers/lineup, but doesn't
    // need to be truly instantaneous either.
    res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300');
    res.status(200).json({ entry, picks });
  } catch (err) {
    res.status(502).json({ error: 'Could not reach the FPL API right now. Try again shortly.' });
  }
};
