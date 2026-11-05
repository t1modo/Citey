// Citation field: a slowly drifting network of papers. Every few seconds a
// citing paper draws an arc to "your paper" (the focal node), a pulse rides
// the arc, and the focal node flares when it lands. Fully procedural.

struct Params {
  time: f32,
  aspect: f32,   // width / height
  px: f32,       // one device pixel in normalized units (1 / height)
  intensity: f32,
  columns: vec2f, // x of the first year column and the column step, in uv (0..1)
}
@group(0) @binding(0) var<uniform> params: Params;

// Papers are laid out on a timeline: COLS publication years, ROWS papers each.
// Column FOCAL holds "your paper"; citations only come from later years.
const COLS: u32 = 8u;
const ROWS: u32 = 5u;
const N: u32 = 40u;
const FOCAL: u32 = 1u;
const PERIOD: f32 = 2.4;
const TRAVEL: f32 = 1.5;     // seconds for a pulse to cross its arc
const LINGER: f32 = 2.6;     // seconds the drawn arc stays visible after landing
const INK = vec3f(0.047, 0.051, 0.063);
const PAPER = vec3f(0.91, 0.886, 0.84);
const SIGNAL = vec3f(1.0, 0.416, 0.239);

fn hash11(n: f32) -> f32 { return fract(sin(n * 127.1) * 43758.5453); }
fn hash21(n: f32) -> vec2f {
  return fract(sin(vec2f(n * 127.1, n * 311.7)) * vec2f(43758.5453, 22578.1459));
}
fn grain(p: vec2f, t: f32) -> f32 {
  return fract(sin(dot(p, vec2f(12.9898, 78.233)) + t) * 43758.5453);
}

fn col_x(c: f32) -> f32 {
  return (params.columns.x + c * params.columns.y - 0.5) * params.aspect;
}

fn focus_pos() -> vec2f { return vec2f(col_x(f32(FOCAL)), 0.04); }

// Node i sits near its year column, drifting slowly. i = row * COLS + column.
fn node(i: u32, t: f32) -> vec2f {
  if (i == 2u * COLS + FOCAL) { return focus_pos(); }
  let fi = f32(i);
  let c = f32(i % COLS);
  let r = f32(i / COLS);
  let h = hash21(fi + 1.7);
  let jitter = (h.x - 0.5) * params.columns.y * params.aspect * 0.4;
  let y = ((r + 0.5) / f32(ROWS) - 0.5) * 0.78 + (h.y - 0.5) * 0.11;
  var p = vec2f(col_x(c) + jitter, y);
  p += 0.008 * vec2f(sin(t * 0.13 + fi * 2.1), cos(t * 0.11 + fi * 1.3));
  return p;
}

fn seg_dist(p: vec2f, a: vec2f, b: vec2f) -> f32 {
  let pa = p - a;
  let ba = b - a;
  let h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
  return length(pa - ba * h);
}

fn bez(a: vec2f, c: vec2f, b: vec2f, s: f32) -> vec2f {
  let m = 1.0 - s;
  return m * m * a + 2.0 * m * s * c + s * s * b;
}

@fragment fn fs_main(@location(0) uv: vec2f) -> @location(0) vec4f {
  let t = params.time;
  let px = params.px;
  let p = (uv - vec2f(0.5)) * vec2f(params.aspect, 1.0);
  let f = focus_pos();

  var col = INK;
  // faint warm light around the focal paper, and a vignette
  col += SIGNAL * 0.035 * exp(-length(p - f) * 3.2);
  col *= 1.0 - 0.35 * smoothstep(0.35, 1.0, length(p / vec2f(params.aspect, 1.0)));

  // year rules: faint vertical hairlines, dashed
  var rules = 0.0;
  for (var c = 0u; c < COLS; c++) {
    let d = abs(p.x - col_x(f32(c)));
    let dash = step(0.5, fract(uv.y * 90.0));
    rules = max(rules, (1.0 - smoothstep(0.0, px, d)) * dash * 0.07);
  }
  col = mix(col, PAPER, rules);

  // background citations: every paper cites one or two from earlier years
  var net = 0.0;
  for (var i = 0u; i < N; i++) {
    let c = i % COLS;
    if (c == 0u) { continue; }
    let a = node(i, t);
    let back = 1u + u32(hash11(f32(i) + 3.3) * 2.0);           // 1 or 2 years back
    let r = i32(i / COLS) + i32(hash11(f32(i) + 7.7) * 3.0) - 1; // same row or a neighbour
    let row = u32(clamp(r, 0, i32(ROWS) - 1));
    let j = row * COLS + (c - min(back, c));
    let d = seg_dist(p, a, node(j, t));
    net = max(net, (1.0 - smoothstep(0.0, 1.1 * px, d)) * 0.075);
  }
  col = mix(col, PAPER, net);

  // nodes
  for (var i = 0u; i < N; i++) {
    let c = node(i, t);
    let r = (1.4 + 1.6 * hash11(f32(i) + 9.0)) * px;
    let d = length(p - c);
    let dot = 1.0 - smoothstep(r - px, r + px, d);
    col = mix(col, PAPER, dot * 0.55);
  }

  // citation events
  let epoch = floor(t / PERIOD);
  var flare = 0.0;
  for (var k = 0; k < 3; k++) {
    let e = epoch - f32(k);
    let age = t - e * PERIOD;
    if (age < 0.0 || age > TRAVEL + LINGER) { continue; }
    // a newer paper (a later year than yours) cites you
    let sc = FOCAL + 2u + u32(hash11(e + 0.31) * f32(COLS - FOCAL - 2u)) % (COLS - FOCAL - 2u);
    let sr = u32(hash11(e + 0.77) * f32(ROWS)) % ROWS;
    let src = node(sr * COLS + sc, t);
    let mid = (src + f) * 0.5;
    let nrm = normalize(vec2f(-(f - src).y, (f - src).x));
    let ctrl = mid + nrm * (0.18 + 0.12 * hash11(e + 5.0)) * sign(hash11(e + 2.0) - 0.5);
    let prog = clamp(age / TRAVEL, 0.0, 1.0);
    let ease = 1.0 - pow(1.0 - prog, 3.0);
    let fade = 1.0 - smoothstep(TRAVEL, TRAVEL + LINGER, age);

    // drawn portion of the arc, brighter toward the head
    var dmin = 1e3;
    var along = 0.0;
    let STEPS = 14;
    var prev = src;
    for (var s = 1; s <= STEPS; s++) {
      let u = ease * f32(s) / f32(STEPS);
      let q = bez(src, ctrl, f, u);
      let d = seg_dist(p, prev, q);
      if (d < dmin) { dmin = d; along = f32(s) / f32(STEPS); }
      prev = q;
    }
    let line = 1.0 - smoothstep(0.4 * px, 1.6 * px, dmin);
    col = mix(col, SIGNAL, line * fade * (0.25 + 0.6 * along));

    // the pulse head, while travelling
    if (prog < 1.0) {
      let head = bez(src, ctrl, f, ease);
      let hd = length(p - head);
      col += SIGNAL * (exp(-hd / (2.5 * px)) * 0.9 + exp(-hd / (14.0 * px)) * 0.18);
    } else {
      // landed: ripple out from the focal paper
      let since = age - TRAVEL;
      let rr = since * 0.11;
      let ring = 1.0 - smoothstep(0.0, 1.5 * px, abs(length(p - f) - rr));
      col = mix(col, SIGNAL, ring * (1.0 - smoothstep(0.0, 1.4, since)) * 0.6);
      flare = max(flare, 1.0 - smoothstep(0.0, 0.9, since));
    }
    // source paper lights up
    let sd = length(p - src);
    col = mix(col, SIGNAL, (1.0 - smoothstep(2.0 * px, 3.5 * px, sd)) * fade);
  }

  // focal paper: ring + core
  let fd = length(p - f);
  let ringR = 10.0 * px;
  let ring = 1.0 - smoothstep(0.0, 1.3 * px, abs(fd - ringR));
  col = mix(col, PAPER, ring * 0.8);
  let core = 1.0 - smoothstep(3.0 * px, 4.5 * px, fd);
  col = mix(col, mix(PAPER, SIGNAL, flare), core);
  col += SIGNAL * flare * 0.35 * exp(-fd / (18.0 * px));

  // film grain keeps the dark field from banding
  col += (grain(uv * 1000.0, fract(t) * 10.0) - 0.5) * 0.022;
  col = mix(INK, col, params.intensity);
  return vec4f(col, 1.0);
}
