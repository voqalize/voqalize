/**
 * The voice ribbon: the logo's V as a live band in the Voice Gradient. It is the one
 * gradient element per view. Amplitude follows the voice state; `intro()` grows it
 * in from flat once on load.
 */
const STOPS = ['#FD873F', '#FD6E43', '#FD5446', '#FD394A', '#F92158', '#ED0B65', '#D1056C', '#AC0162'];

export interface Ribbon { set(amp: number): void; pulse(): void }

export function mountRibbon(canvas: HTMLCanvasElement, startAmp = 8): Ribbon {
  const ctx = canvas.getContext('2d')!;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let amp = reduced ? startAmp : 0, target = startAmp, t = 0, w = 0, h = 0, reveal = reduced ? 1 : 0;
  const fit = () => {
    const r = canvas.getBoundingClientRect(), d = devicePixelRatio || 1;
    w = r.width; h = r.height; canvas.width = Math.round(w * d); canvas.height = Math.round(h * d); ctx.setTransform(d, 0, 0, d, 0, 0);
  };
  new ResizeObserver(fit).observe(canvas); fit();
  const y = (x: number, k: number) => {
    const env = Math.sin((Math.PI * x) / w);
    return h / 2 + env * amp * (Math.sin(x * 0.018 + t * 2.2 + k * 0.9) * 0.7 + Math.sin(x * 0.041 - t * 3.1 + k) * 0.3);
  };
  const frame = () => {
    if (w && canvas.isConnected) {
      if (!reduced) t += 0.016;
      amp += (target - amp) * 0.08;
      reveal = Math.min(1, reveal + 0.02);
      ctx.clearRect(0, 0, w, h);
      const g = ctx.createLinearGradient(0, 0, w, 0);
      STOPS.forEach((c, i) => g.addColorStop(i / (STOPS.length - 1), c));
      const x0 = (w / 2) * (1 - reveal), x1 = w - x0;
      ctx.beginPath();
      for (let x = x0; x <= x1; x += 3) ctx.lineTo(x, y(x, 0) - 2.5 * Math.sin((Math.PI * x) / w));
      for (let x = x1; x >= x0; x -= 3) ctx.lineTo(x, y(x, 1.3) + 2.5 * Math.sin((Math.PI * x) / w));
      ctx.closePath(); ctx.fillStyle = g; ctx.globalAlpha = 0.92; ctx.fill();
      ctx.globalAlpha = 0.45; ctx.strokeStyle = g; ctx.lineWidth = 1.2;
      for (const k of [2.4, 3.3]) { ctx.beginPath(); for (let x = x0; x <= x1; x += 3) ctx.lineTo(x, y(x, k)); ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  return {
    set(v) { target = v; },
    pulse() { amp = target + 10 + Math.random() * 12; },
  };
}
