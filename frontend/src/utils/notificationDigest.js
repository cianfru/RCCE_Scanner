const severityRank = {critical:0, high:1, medium:2, low:3, positive:2};
// Plain titles for anomaly codes; value-aware where the code hides the direction.
const TYPE_TITLES = {
  OI_SURGE: v => v < 0 ? 'Open interest drop' : 'Open interest jump',
  CVD_EXTREME: 'Taker flow extreme',
  VOLUME_SPIKE: 'Volume spike',
  EXTREME_FUNDING: 'Funding extreme',
  LSR_EXTREME: 'Long/short ratio extreme',
  VPIN_TOXIC: 'Order flow imbalance',
};
function typeTitle(item) {
  const code = item.anomaly_type || item.type;
  const t = TYPE_TITLES[code];
  if (t) return typeof t === 'function' ? t(Number(item.current_value) || 0) : t;
  return code?.replaceAll('_',' ').toLowerCase();
}
export function notificationDigest({warnings=[], anomalies=[], setups=[], opportunities=[], insights=[]}, dismissed=new Set()) {
  const items = [
    ...warnings.map(x=>({...x,key:`warn:${x.type}:${x.symbol}`,category:'Position risk',rank:0})),
    ...setups.map(x=>({...x,key:`setup:${x.type}:${x.symbol}`,category:'Setup',rank:1})),
    ...opportunities.map(x=>({...x,key:`opp:${x.type}:${x.symbol}`,category:'Setup',rank:1})),
    ...anomalies.map(x=>({...x,key:`anom:${x.dedup_key}`,category:'Market change',rank:x.severity==='critical' ? 0.5 : 2})),
    ...insights.map(x=>({...x,category:'Research',rank:3})),
  ].filter(x=>!dismissed.has(x.key));
  const groups = new Map();
  for (const item of items) {
    const key = `${item.category}:${item.symbol || item.key}`;
    const text = String(item.detail || item.context || item.message || item.title || item.type || 'Market update').trim();
    const title = String(item.title || typeTitle(item) || 'Research update').replace(/^\[Agent\]\s*/, '');
    const summary = item.anomaly_type ? text.split('|')[0].replace(/\s*\(z=.*?\)/g,'').trim() : text;
    const entry = {...item, title, text, summary, priority:item.rank*10+(severityRank[item.severity] ?? 3)};
    if (!groups.has(key)) groups.set(key,{key, ...entry, entries:[], keys:[]});
    const group=groups.get(key);
    group.entries.push(entry); group.keys.push(item.key);
    if (entry.priority < group.priority) Object.assign(group,{priority:entry.priority,title,category:item.category});
  }
  for (const group of groups.values()) group.entries.sort((a,b)=>a.priority-b.priority);
  return [...groups.values()].sort((a,b)=>a.priority-b.priority || (Number(b.timestamp)||0)-(Number(a.timestamp)||0));
}
