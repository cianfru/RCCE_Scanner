import { ArrowUpRight, ArrowDownRight, Info, TriangleAlert, GitCompareArrows } from 'lucide-react';
import { T, col } from '../theme.js';
import { signalContext } from '../utils/signalPresentation.js';
export const CONTEXT_META = {
  bullish: {Icon:ArrowUpRight, color:'#34d399', label:'Bullish context'},
  bearish: {Icon:ArrowDownRight, color:'#cf9185', label:'Bearish context'},
  conflict:{Icon:GitCompareArrows, color:'#fb923c', label:'Conflicting evidence'},
  caution:{Icon:TriangleAlert, color:'#fbbf24', label:'Caution'},
  missing:{Icon:Info, color:T.text3, label:'Missing information'},
  info:{Icon:Info, color:T.text3, label:'Context'},
};
export default function SignalContext({ row, marketWide }) {
  const items = signalContext(row, { marketWide });
  return <div style={{display:'grid',gap:10}}>{items.length ? items.map((item,i) => {
    const {Icon,color:base,label} = CONTEXT_META[item.kind];
    const color = col(base);
    return <div key={i} style={{display:'flex',gap:8,alignItems:'flex-start',fontSize:12,lineHeight:1.55}}><Icon size={15} color={color} style={{flexShrink:0,marginTop:2}} aria-label={label}/><span><strong style={{color,display:'block',fontSize:T.textXs}}>{label}</strong>{item.text}</span></div>;
  }) : <span style={{color:T.text3}}>No additional context returned.</span>}</div>;
}
