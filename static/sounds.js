const FinSounds = (function() {
  let audioCtx = null;

  function getCtx() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function tone(freq, startTime, duration, volume, type = 'sine') {
    const ctx = getCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, startTime);
    gain.gain.linearRampToValueAtTime(volume, startTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(startTime);
    osc.stop(startTime + duration);
  }

  return {
    success() {
      const ctx = getCtx();
      const now = ctx.currentTime;
      tone(523.25, now, 0.18, 0.15);
      tone(659.25, now + 0.08, 0.22, 0.15);
    },
    coin() {
      const ctx = getCtx();
      const now = ctx.currentTime;
      tone(987.77, now, 0.10, 0.12, 'triangle');
      tone(1318.51, now + 0.06, 0.18, 0.12, 'triangle');
    },
    levelUp() {
      const ctx = getCtx();
      const now = ctx.currentTime;
      tone(523.25, now, 0.15, 0.15);
      tone(659.25, now + 0.1, 0.15, 0.15);
      tone(783.99, now + 0.2, 0.15, 0.15);
      tone(1046.50, now + 0.3, 0.35, 0.18);
    },
    error() {
      const ctx = getCtx();
      const now = ctx.currentTime;
      tone(220, now, 0.18, 0.12, 'triangle');
      tone(196, now + 0.12, 0.22, 0.12, 'triangle');
    },
    amo() {
      const ctx = getCtx();
      const now = ctx.currentTime;
      tone(440, now, 0.12, 0.1, 'triangle');
      tone(440, now + 0.18, 0.12, 0.1, 'triangle');
    }
  };
})();
