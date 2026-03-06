import { useRef, useEffect } from "react";

export default function SparklineCell({ data, width = 60, height = 24 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data || data.length < 2) return;

    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    const last = data[data.length - 1];
    const first = data[0];
    const color = last >= first ? "#34d399" : "#f87171";

    const padding = 2;
    const drawWidth = width - padding * 2;
    const drawHeight = height - padding * 2;

    // Draw gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, color + "20");
    gradient.addColorStop(1, color + "00");

    ctx.beginPath();
    ctx.moveTo(padding, padding + drawHeight - ((data[0] - min) / range) * drawHeight);

    for (let i = 0; i < data.length; i++) {
      const x = padding + (i / (data.length - 1)) * drawWidth;
      const y = padding + drawHeight - ((data[i] - min) / range) * drawHeight;
      ctx.lineTo(x, y);
    }

    // Close for fill
    ctx.lineTo(padding + drawWidth, padding + drawHeight);
    ctx.lineTo(padding, padding + drawHeight);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw line
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const x = padding + (i / (data.length - 1)) * drawWidth;
      const y = padding + drawHeight - ((data[i] - min) / range) * drawHeight;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    // Draw endpoint dot
    const lastX = padding + drawWidth;
    const lastY = padding + drawHeight - ((last - min) / range) * drawHeight;
    ctx.beginPath();
    ctx.arc(lastX, lastY, 1.5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }, [data, width, height]);

  if (!data || data.length < 2) {
    return (
      <span style={{ color: "#3f3f46", fontFamily: "monospace", fontSize: 10 }}>
        {"\u2014"}
      </span>
    );
  }

  return (
    <canvas
      ref={canvasRef}
      style={{
        width,
        height,
        display: "block",
      }}
    />
  );
}
