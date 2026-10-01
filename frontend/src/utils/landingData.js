// The landing payload (/api/public/landing) sends the closes most coins share once, as `t`;
// each coin's trail gets them back here, in the shape the Radar map reads.
export function hydrate(body) {
  if (!body || !Array.isArray(body.coins)) return null;
  const t = body.t || [];
  return { ...body, coins: body.coins.map(c => (c.trail && !c.trail.t ? { ...c, trail: { ...c.trail, t } } : c)) };
}
