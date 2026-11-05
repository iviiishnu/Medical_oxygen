// Loud repeating two-tone alarm via WebAudio (no audio file needed).
// Browsers only allow sound after a user gesture, so the UI shows an "Enable alarm sound" button.
let ctx: AudioContext | null = null;
let timer: number | null = null;

export function unlockAudio(): boolean {
  ctx ??= new AudioContext();
  void ctx.resume();
  return ctx.state !== 'suspended';
}

export function audioReady(): boolean {
  return ctx != null && ctx.state === 'running';
}

function beep(freq: number, at: number, dur: number) {
  if (!ctx) return;
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = 'square';
  o.frequency.value = freq;
  g.gain.setValueAtTime(0.0001, at);
  g.gain.exponentialRampToValueAtTime(0.35, at + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  o.connect(g).connect(ctx.destination);
  o.start(at);
  o.stop(at + dur + 0.02);
}

function burst() {
  if (!ctx) return;
  const t = ctx.currentTime + 0.02;
  [880, 660, 880, 660, 880].forEach((f, i) => beep(f, t + i * 0.2, 0.15));
}

export function setAlarm(on: boolean) {
  if (on && timer == null) {
    burst();
    timer = window.setInterval(burst, 2500);
  } else if (!on && timer != null) {
    window.clearInterval(timer);
    timer = null;
  }
}
