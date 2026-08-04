import { useEffect, useRef } from "react";

const IMG_SRC = "/sonik.jpg";
const MAX_ON_SCREEN = 7;
const SPAWN_AT_COUNT = 4;
const AVOID_RADIUS = 110;
const AVOID_STRENGTH = 88;
const MAX_DRIFT_SPEED = 50;
const CLICK_FLEE_SPEED_MIN = 135;
const CLICK_FLEE_SPEED_MAX = 195;
const CLICK_BOOST_DECAY = 1.4;

function rand(a: number, b: number) {
  return a + Math.random() * (b - a);
}

function randInt(a: number, b: number) {
  return a + Math.floor(Math.random() * (b - a + 1));
}

function clamp(x: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, x));
}

function len(x: number, y: number) {
  return Math.hypot(x, y);
}

function norm(x: number, y: number) {
  const L = len(x, y) || 1;
  return { nx: x / L, ny: y / L };
}

type Sprite = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  opacity: number;
  dw: number;
  dh: number;
  wobble: number;
  wobbleRate: number;
  clickBoostT: number;
};

function hasInteractiveAbove(clientX: number, clientY: number) {
  const stack = document.elementsFromPoint(clientX, clientY);
  for (const el of stack.slice(0, 14)) {
    if (
      el.closest(
        "a,button,input,textarea,select,label,[role=button],.top-nav",
      )
    ) {
      return true;
    }
  }
  return false;
}

function spawnSprite(w: number, h: number, iw: number, ih: number): Sprite {
  const m = 64;
  const edge = randInt(0, 3);
  let x = 0;
  let y = 0;
  let ix = 0;
  let iy = 0;
  if (edge === 0) {
    x = rand(0, w);
    y = -m;
    ix = 0;
    iy = 1;
  } else if (edge === 1) {
    x = w + m;
    y = rand(0, h);
    ix = -1;
    iy = 0;
  } else if (edge === 2) {
    x = rand(0, w);
    y = h + m;
    ix = 0;
    iy = -1;
  } else {
    x = -m;
    y = rand(0, h);
    ix = 1;
    iy = 0;
  }
  const jitter = rand(-0.52, 0.52);
  const c = Math.cos(jitter);
  const s = Math.sin(jitter);
  const rx = ix * c - iy * s;
  const ry = ix * s + iy * c;
  const speed = rand(19, 36);
  const { nx, ny } = norm(rx, ry);
  const dw = rand(17, 27);
  const dh = (ih / iw) * dw;
  return {
    x,
    y,
    vx: nx * speed,
    vy: ny * speed,
    opacity: rand(0.7, 0.8),
    dw,
    dh,
    wobble: rand(0, Math.PI * 2),
    wobbleRate: rand(0.32, 0.82),
    clickBoostT: 0,
  };
}

export default function AmbientSonics() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.decoding = "async";
    img.src = IMG_SRC;

    let sprites: Sprite[] = [];
    let mouse = { x: -9999, y: -9999 };
    let lw = 1;
    let lh = 1;
    let raf = 0;
    let last = 0;
    let running = true;

    const syncRect = () => {
      const r = wrap.getBoundingClientRect();
      lw = Math.max(1, r.width);
      lh = Math.max(1, r.height);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(lw * dpr));
      canvas.height = Math.max(1, Math.floor(lh * dpr));
      canvas.style.width = `${lw}px`;
      canvas.style.height = `${lh}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const setMouseFromEvent = (e: PointerEvent) => {
      const r = wrap.getBoundingClientRect();
      const x = e.clientX - r.left;
      const y = e.clientY - r.top;
      if (x < -40 || y < -40 || x > r.width + 40 || y > r.height + 40) {
        mouse.x = -9999;
        mouse.y = -9999;
      } else {
        mouse.x = x;
        mouse.y = y;
      }
    };

    const onMove = (e: PointerEvent) => setMouseFromEvent(e);

    const onClick = (e: PointerEvent) => {
      if (e.button !== 0) return;
      if (hasInteractiveAbove(e.clientX, e.clientY)) return;
      const r = wrap.getBoundingClientRect();
      const cx = e.clientX - r.left;
      const cy = e.clientY - r.top;
      if (cx < 0 || cy < 0 || cx > r.width || cy > r.height) return;
      const spd = rand(CLICK_FLEE_SPEED_MIN, CLICK_FLEE_SPEED_MAX);
      let hit = false;
      for (const sp of sprites) {
        const hw = sp.dw * 0.5 + 4;
        const hh = sp.dh * 0.5 + 4;
        if (Math.abs(cx - sp.x) > hw || Math.abs(cy - sp.y) > hh) continue;
        const { nx, ny } = norm(sp.x - cx, sp.y - cy);
        sp.vx = nx * spd;
        sp.vy = ny * spd;
        sp.clickBoostT = CLICK_BOOST_DECAY;
        hit = true;
      }
      if (hit) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    const loop = (t: number) => {
      if (!running) return;
      if (last === 0) last = t;
      const dt = clamp((t - last) * 0.001, 0, 0.048);
      last = t;

      const W = lw;
      const H = lh;
      ctx.clearRect(0, 0, W, H);

      if (img.complete && img.naturalWidth > 0) {
        const iw = img.naturalWidth;
        const ih = img.naturalHeight;

        for (let i = sprites.length - 1; i >= 0; i--) {
          const sp = sprites[i]!;

          if (sp.clickBoostT > 0) {
            sp.clickBoostT = Math.max(0, sp.clickBoostT - dt);
          }

          const rdx = sp.x - mouse.x;
          const rdy = sp.y - mouse.y;
          const d = len(rdx, rdy);
          if (d < AVOID_RADIUS && d > 0.5) {
            const push = (1 - d / AVOID_RADIUS) * AVOID_STRENGTH * dt;
            const { nx, ny } = norm(rdx, rdy);
            sp.vx += nx * push;
            sp.vy += ny * push;
          }

          sp.wobble += sp.wobbleRate * dt;
          const wx = Math.sin(sp.wobble) * 9 * dt;
          const wy = Math.cos(sp.wobble * 0.88) * 7 * dt;
          sp.x += (sp.vx + wx) * dt;
          sp.y += (sp.vy + wy) * dt;

          const cap =
            sp.clickBoostT > 0
              ? Math.max(MAX_DRIFT_SPEED * 3.4, CLICK_FLEE_SPEED_MAX * 1.08)
              : MAX_DRIFT_SPEED;
          const spd = len(sp.vx, sp.vy);
          if (spd > cap) {
            const k = cap / spd;
            sp.vx *= k;
            sp.vy *= k;
          }

          const margin = 90;
          if (
            sp.x < -margin ||
            sp.x > W + margin ||
            sp.y < -margin ||
            sp.y > H + margin
          ) {
            sprites.splice(i, 1);
          }
        }

        if (sprites.length === SPAWN_AT_COUNT) {
          const add = randInt(1, 3);
          for (let k = 0; k < add && sprites.length < MAX_ON_SCREEN; k++) {
            sprites.push(spawnSprite(W, H, iw, ih));
          }
        }

        for (const sp of sprites) {
          ctx.globalAlpha = sp.opacity;
          ctx.drawImage(img, sp.x - sp.dw * 0.5, sp.y - sp.dh * 0.5, sp.dw, sp.dh);
        }
        ctx.globalAlpha = 1;
      }

      raf = requestAnimationFrame(loop);
    };

    const ro = new ResizeObserver(() => syncRect());
    ro.observe(wrap);
    syncRect();

    const start = () => {
      const W = lw;
      const H = lh;
      const iw = img.naturalWidth;
      const ih = img.naturalHeight;
      if (iw <= 0) return;
      const n = randInt(5, 7);
      sprites = [];
      for (let i = 0; i < n; i++) {
        sprites.push(spawnSprite(W, H, iw, ih));
      }
      last = 0;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(loop);
    };

    img.onload = start;
    if (img.complete && img.naturalWidth > 0) start();

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerdown", onClick, true);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onClick, true);
    };
  }, []);

  return (
    <div ref={wrapRef} className="ambient-sonics">
      <canvas ref={canvasRef} className="ambient-sonics-canvas" aria-hidden />
    </div>
  );
}
