const FinSounds = (function() {
  let audioCtx = null;

  function getCtx() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
  }

  async function ensureRunning() {
    const ctx = getCtx();
    if (ctx.state === 'suspended') {
      await ctx.resume();
    }
    return ctx;
  }

  function tone(ctx, freq, startTime, duration, volume, type = 'sine') {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, startTime);
    gain.gain.linearRampToValueAtTime(volume, startTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(startTime);
    osc.stop(startTime + duration);
  }

  return {
    async success() {
      const ctx = await ensureRunning();
      const now = ctx.currentTime;
      tone(ctx, 523.25, now, 0.3, 0.5);
      tone(ctx, 659.25, now + 0.12, 0.35, 0.5);
    },
    async coin() {
      const ctx = await ensureRunning();
      const now = ctx.currentTime;
      tone(ctx, 987.77, now, 0.2, 0.45, 'triangle');
      tone(ctx, 1318.51, now + 0.1, 0.3, 0.45, 'triangle');
    },
    async levelUp() {
      const ctx = await ensureRunning();
      const now = ctx.currentTime;
      tone(ctx, 523.25, now, 0.25, 0.45);
      tone(ctx, 659.25, now + 0.15, 0.25, 0.45);
      tone(ctx, 783.99, now + 0.3, 0.25, 0.45);
      tone(ctx, 1046.50, now + 0.45, 0.5, 0.5);
    },
    async error() {
      const ctx = await ensureRunning();
      const now = ctx.currentTime;
      tone(ctx, 300, now, 0.3, 0.45, 'triangle');
      tone(ctx, 220, now + 0.18, 0.35, 0.45, 'triangle');
    },
    async amo() {
      const ctx = await ensureRunning();
      const now = ctx.currentTime;
      tone(ctx, 523.25, now, 0.2, 0.4, 'triangle');
      tone(ctx, 523.25, now + 0.28, 0.2, 0.4, 'triangle');
    }
  };
})();
