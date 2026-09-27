// Once the exchange has accepted an action, a journal failure cannot undo it.
export async function executeAndJournal(execute, journal) {
  const execution = await execute();
  try {
    const response = await journal(execution);
    if (response && !response.ok) throw new Error(`Journal HTTP ${response.status}`);
    return { execution, journalPending: false };
  } catch {
    return { execution, journalPending: true };
  }
}
export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}
