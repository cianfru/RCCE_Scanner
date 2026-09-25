import { col } from '../theme.js';
import TrendChart from './TrendChart.jsx';
export default function SparklineCell({ data, width = 72, height = 28 }) {
  const rising = data?.[data.length - 1] >= data?.[0];
  return <div style={{width, flexShrink:0}}><TrendChart data={data} height={height} compact color={rising ? col('#97FCE4') : col('#cf9185')} label={`Recent price trend, ${rising ? 'rising' : 'falling'}`}/></div>;
}
