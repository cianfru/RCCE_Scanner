import { rangeRuler } from '../utils/chartPresentation.js';
// Lightweight Charts v5 series primitive; redraws with pan, zoom, and price scale.
export default class RangeRuler {
  constructor({reference, percentage, lastIndex, horizon}) {
    this.range = rangeRuler(reference, percentage);
    this.percentage = percentage;
    this.lastIndex = lastIndex;
    this.horizon = horizon;
    this.view = {zOrder:()=> 'top', renderer:()=> ({draw:target=>this.draw(target)})};
  }
  attached({chart, series, requestUpdate}) {this.chart=chart; this.series=series; requestUpdate();}
  detached() {this.chart=null;this.series=null;}
  updateAllViews() {}
  paneViews() {return [this.view];}
  draw(target) {
    if (!this.chart || !this.series || !this.range) return;
    // The library accepts integer logical indices; derive candle edges from centres.
    const lastX = this.chart.timeScale().logicalToCoordinate(this.lastIndex);
    const nextX = this.chart.timeScale().logicalToCoordinate(this.lastIndex + 1);
    if (lastX == null || nextX == null) return;
    const halfBar = (nextX - lastX) / 2;
    const x1 = nextX - halfBar;
    const x2 = nextX + halfBar;
    const top = this.series.priceToCoordinate(this.range.top);
    const bottom = this.series.priceToCoordinate(this.range.bottom);
    if ([x1,x2,top,bottom].some(v=>v == null || !Number.isFinite(v))) return;
    target.useMediaCoordinateSpace(({context:ctx,mediaSize})=>{
      if (x2 < 0 || x1 > mediaSize.width) return;
      ctx.save();
      ctx.fillStyle='rgba(145,185,232,0.07)';ctx.fillRect(x1,top,x2-x1,bottom-top);
      ctx.strokeStyle='rgba(145,185,232,0.65)';ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(x1,top);ctx.lineTo(x2,top);ctx.moveTo((x1+x2)/2,top);ctx.lineTo((x1+x2)/2,bottom);ctx.moveTo(x1,bottom);ctx.lineTo(x2,bottom);ctx.stroke();
      // Label in the empty space right of the last candle, centred on the ruler, so it
      // never covers price. Falls back to the left of the ruler when there is no room.
      const lines=[`${this.percentage.toFixed(2)}%`, `range ${this.horizon}`];
      ctx.font='600 11px sans-serif';
      const w1=ctx.measureText(lines[0]).width;
      ctx.font='10px sans-serif';
      const width=Math.max(w1, ctx.measureText(lines[1]).width)+12;
      const height=30;
      const mid=(top+bottom)/2;
      let x=x2+6;
      if (x+width > mediaSize.width-2) x=x1-6-width;
      const y=Math.max(2,Math.min(mediaSize.height-height-2,mid-height/2));
      ctx.fillStyle='rgba(9,22,25,0.9)';ctx.fillRect(x,y,width,height);
      ctx.strokeStyle='rgba(145,185,232,0.35)';ctx.strokeRect(x+0.5,y+0.5,width-1,height-1);
      ctx.fillStyle='#bfdbfe';ctx.font='600 11px sans-serif';ctx.fillText(lines[0],x+6,y+13);
      ctx.fillStyle='rgba(191,219,254,0.75)';ctx.font='10px sans-serif';ctx.fillText(lines[1],x+6,y+25);
      ctx.restore();
    });
  }
}
