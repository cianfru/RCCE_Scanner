import { useId } from 'react';

// Preserve every sample: no smoothing or interpolation of market observations.
export default function TrendChart({ data, color = '#97FCE4', label = 'Recent trend', height = 64, compact = false }) {
  const id = useId().replace(/:/g, '');
  if (!data || data.length < 2 || data.some(v => !Number.isFinite(v))) return <span>—</span>;
  const width = 240, pad = 5, min = Math.min(...data), max = Math.max(...data);
  const range = max - min;
  const points = data.map((v, i) => [pad + i * (width - pad * 2) / (data.length - 1), range ? height - pad - (v - min) / range * (height - pad * 2) : height / 2]);
  const line = points.map(([x,y],i) => `${i ? 'L' : 'M'}${x},${y}`).join(' ');
  return <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label} style={{ width:'100%', height, display:'block' }}>
    <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".16"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
    {!compact && [0.25,0.75].map(y => <line key={y} x1="0" x2={width} y1={height*y} y2={height*y} stroke="currentColor" opacity=".08" vectorEffect="non-scaling-stroke"/>)}
    <path d={`${line} L${width-pad},${height} L${pad},${height} Z`} fill={`url(#${id})`}/>
    <path d={line} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke"/>
  </svg>;
}
