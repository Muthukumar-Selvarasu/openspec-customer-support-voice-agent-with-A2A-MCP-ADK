/* Voice client for the cascade.
 *
 * Mic at 16 kHz, energy VAD, binary PCM to /voice/ws.
 * Server audio is 24 kHz PCM and is queued for playback.
 * A clear utterance while the agent is speaking stops playback and sends
 * {"type":"interrupt"}.
 *
 * Pipeline events go to the page's renderEvent(). The page provides USER, col,
 * el, scroll, md, addAssistant, renderEvent, and setStatus.
 */
(function () {
  const VAD_RMS = 0.02;
  const BARGE_RMS = 0.12;
  const ONSET_FRAMES = 2;
  const BARGE_FRAMES = 3;
  const END_SILENCE_MS = 1500;
  const PTT_RELEASE_TAIL_MS = 1000;
  const PLAYBACK_GRACE_MS = 400;
  const PREROLL_FRAMES = 3;
  const FRAME = 2048;
  const CAPTURE_RATE = 16000;
  const PLAY_RATE = 24000;

  let ws = null;
  let captureCtx = null;
  let playCtx = null;
  let stream = null;
  let proc = null;
  let voiceOn = false;
  let speaking = false;
  let pttActive = false;
  let pttDownAt = 0;
  let pttReleased = false;
  let pttPaused = false;
  let pttTailTimer = null;
  let micPressHeld = false;
  let tabHeld = false;
  let startingVoice = null;
  let agentSpeaking = false;
  let turnRunning = false;
  let ignoreAudio = false;
  let muted = false;
  let frames = [];
  let preroll = [];
  let silentFrames = 0;
  let onsetCount = 0;
  let playCursor = 0;
  let activeSources = [];
  let lastPlayStart = 0;
  let node = null;
  let userBubble = null;

  const inwrap = document.querySelector(".inwrap");
  if (!inwrap) return;

  const micSvg = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" style="vertical-align:middle" aria-hidden="true"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>';
  const holdBtn = document.createElement("button");
  holdBtn.type = "button";
  holdBtn.id = "hold";
  holdBtn.className = "vbtn";
  holdBtn.textContent = "Mute";
  holdBtn.title = "Mute microphone";
  holdBtn.style.display = "none";
  inwrap.insertBefore(holdBtn, document.getElementById("send"));

  const micBtn = document.createElement("button");
  micBtn.type = "button";
  micBtn.id = "mic";
  micBtn.className = "vbtn";
  micBtn.innerHTML = micSvg;
  micBtn.title = "Click and hold to speak with the Agent (or hold Tab)";
  inwrap.insertBefore(micBtn, document.getElementById("send"));

  const status = document.getElementById("voiceStatus");
  if (status && status.parentNode && !document.getElementById("pttHint")) {
    const pttHint = document.createElement("div");
    pttHint.id = "pttHint";
    pttHint.className = "hint";
    pttHint.innerHTML = "🎙 <strong>Click and hold the Mic button</strong> (or hold <code>Tab</code>) to speak with the Agent — release when done.";
    status.parentNode.insertBefore(pttHint, status.nextSibling);
  }

  function sendDemoMode() {
    if (ws && ws.readyState === 1 && typeof demoMode === "function") {
      ws.send(JSON.stringify({ type: "mode", mode: demoMode() }));
    }
  }
  window.csSendDemoMode = sendDemoMode;

  function sendGuardrails() {
    if (ws && ws.readyState === 1 && typeof judgeEnabled === "function" && typeof maskEnabled === "function") {
      ws.send(JSON.stringify({ type: "guardrails", judge: judgeEnabled(), mask: maskEnabled() }));
    }
  }
  window.csSendGuardrails = sendGuardrails;

  function setVoiceStatus(text) {
    status.textContent = text ? "🎙 " + text : "";
    micBtn.classList.toggle("live", voiceOn && !pttPaused && !pttTailTimer);
  }

  function now() {
    return typeof performance !== "undefined" ? performance.now() : Date.now();
  }

  function playChunk(buf) {
    if (!playCtx) return;
    const i16 = new Int16Array(buf);
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
    const audio = playCtx.createBuffer(1, f32.length, PLAY_RATE);
    audio.getChannelData(0).set(f32);
    const src = playCtx.createBufferSource();
    src.buffer = audio;
    src.connect(playCtx.destination);
    if (playCursor < playCtx.currentTime) playCursor = playCtx.currentTime + 0.05;
    src.start(playCursor);
    playCursor += audio.duration;
    if (!agentSpeaking) lastPlayStart = now();
    agentSpeaking = true;
    activeSources.push(src);
    src.onended = () => {
      activeSources = activeSources.filter((item) => item !== src);
      if (!activeSources.length) {
        agentSpeaking = false;
        if (voiceOn) setVoiceStatus(pttPaused ? "" : "listening…");
      }
    };
    setVoiceStatus("speaking…");
  }

  function stopPlayback() {
    activeSources.forEach((src) => {
      try { src.stop(); } catch (err) { /* already stopped */ }
    });
    activeSources = [];
    playCursor = 0;
    agentSpeaking = false;
  }

  function floatToPcm(f32) {
    const i16 = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
      i16[i] = Math.max(-32768, Math.min(32767, f32[i] * 32768));
    }
    return i16;
  }

  function rmsOf(f32) {
    let sum = 0;
    for (let i = 0; i < f32.length; i++) sum += f32[i] * f32[i];
    return Math.sqrt(sum / f32.length);
  }

  function sendInterrupt() {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "interrupt" }));
  }

  function bargeIn() {
    if (!agentSpeaking) return;
    stopPlayback();
    sendInterrupt();
  }

  function downsample(f32, fromRate, toRate) {
    if (!fromRate || fromRate === toRate) return f32;
    const ratio = fromRate / toRate;
    const length = Math.floor(f32.length / ratio);
    const out = new Float32Array(length);
    for (let i = 0; i < length; i++) {
      const index = i * ratio;
      const left = Math.floor(index);
      const frac = index - left;
      const right = Math.min(left + 1, f32.length - 1);
      out[i] = f32[left] * (1 - frac) + f32[right] * frac;
    }
    return out;
  }

  function sendFrame(i16) {
    if (!speaking || !ws || ws.readyState !== 1 || !i16 || !i16.length) return;
    ws.send(i16.buffer);
  }

  function endUtterance(commit) {
    speaking = false;
    if (typeof pttActive !== "undefined") pttActive = false;
    frames = [];
    silentFrames = 0;
    if (ws && ws.readyState === 1) {
      const payload = commit ? { type: "utterance_end", commit: true } : { type: "utterance_end" };
      if (commit && typeof turnRunning !== "undefined") turnRunning = true;
      ws.send(JSON.stringify(payload));
      setVoiceStatus("transcribing…");
      return;
    }
    if (voiceOn) setVoiceStatus(agentSpeaking ? "speaking…" : "listening…");
  }

  function clearPttTail() {
    if (typeof pttTailTimer !== "undefined" && pttTailTimer) {
      clearTimeout(pttTailTimer);
      pttTailTimer = null;
    }
  }

  function finishPttRelease() {
    if (typeof pttTailTimer !== "undefined") pttTailTimer = null;
    if (typeof pttPaused !== "undefined") pttPaused = true;
    if (speaking) {
      endUtterance(true);
    } else {
      setVoiceStatus("");
    }
  }

  function beginPtt() {
    if (muted) return;
    clearPttTail();
    if (typeof pttPaused !== "undefined") pttPaused = false;
    if (typeof ignoreAudio !== "undefined") ignoreAudio = true;
    pttActive = true;
    pttDownAt = now();
    bargeIn();
    if (!agentSpeaking && typeof turnRunning !== "undefined" && turnRunning) {
      sendInterrupt();
    }
    if (
      typeof node !== "undefined" &&
      node &&
      typeof bubbleHasAnswer === "function" &&
      bubbleHasAnswer(node.querySelector(".bubble"))
    ) {
      finishSpinningSteps(node);
      userBubble = null;
      node = null;
    }
    if (!speaking) {
      speaking = true;
      frames = preroll.slice();
      preroll = [];
      for (const frame of frames) sendFrame(frame);
      silentFrames = 0;
      onsetCount = 0;
    }
    setVoiceStatus("listening… (release to send)");
  }

  function releasePtt() {
    if (!pttActive) return;
    pttActive = false;
    pttReleased = true;
    clearPttTail();
    const tailMs = typeof PTT_RELEASE_TAIL_MS !== "undefined" ? PTT_RELEASE_TAIL_MS : 0;
    if (speaking && tailMs > 0) {
      pttTailTimer = setTimeout(finishPttRelease, tailMs);
      setVoiceStatus("transcribing…");
      return;
    }
    finishPttRelease();
  }

  function onFrame(f32) {
    if (muted || (typeof pttPaused !== "undefined" && pttPaused) || !captureCtx) return;
    const frameMs = (f32.length / captureCtx.sampleRate) * 1000;
    const speech = downsample(f32, captureCtx.sampleRate, CAPTURE_RATE);
    if (!speech.length) return;
    const rms = rmsOf(speech);
    const i16 = floatToPcm(speech);
    const held =
      (typeof pttActive !== "undefined" && pttActive) ||
      (typeof pttTailTimer !== "undefined" && !!pttTailTimer);

    if (!speaking) {
      preroll.push(i16);
      if (preroll.length > PREROLL_FRAMES) preroll.shift();
      if (!held) {
        if (agentSpeaking && now() - lastPlayStart < PLAYBACK_GRACE_MS) return;
        const threshold = agentSpeaking ? BARGE_RMS : VAD_RMS;
        const needed = agentSpeaking ? BARGE_FRAMES : ONSET_FRAMES;
        onsetCount = rms > threshold ? onsetCount + 1 : 0;
        if (onsetCount < needed) return;
      }
      bargeIn();
      speaking = true;
      frames = preroll.slice();
      preroll = [];
      for (const frame of frames) sendFrame(frame);
      silentFrames = 0;
      onsetCount = ONSET_FRAMES;
      setVoiceStatus("listening… (speech)");
      return;
    }

    frames.push(i16);
    sendFrame(i16);
    if (rms > VAD_RMS) {
      onsetCount += 1;
      silentFrames = 0;
      return;
    }
    if (held || onsetCount < ONSET_FRAMES) {
      silentFrames = 0;
      return;
    }
    silentFrames += 1;
    const silenceMs = silentFrames * frameMs;
    if (silenceMs >= END_SILENCE_MS) {
      if (typeof pttPaused !== "undefined") pttPaused = true;
      endUtterance(true);
    }
  }

  async function startCapture() {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    captureCtx = new AudioCtx();
    if (captureCtx.state === "suspended") await captureCtx.resume();
    const source = captureCtx.createMediaStreamSource(stream);
    proc = captureCtx.createScriptProcessor(FRAME, 1, 1);
    proc.onaudioprocess = (event) => {
      if (voiceOn) onFrame(event.inputBuffer.getChannelData(0));
    };
    source.connect(proc);
    const sink = captureCtx.createGain();
    sink.gain.value = 0;
    proc.connect(sink);
    sink.connect(captureCtx.destination);
  }

  function stopCapture() {
    if (proc) {
      try { proc.disconnect(); } catch (err) { /* already disconnected */ }
      proc = null;
    }
    if (captureCtx) {
      try { captureCtx.close(); } catch (err) { /* already closed */ }
      captureCtx = null;
    }
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
    speaking = false;
    frames = [];
    preroll = [];
    onsetCount = 0;
  }

  function ensureUserBubble() {
    if (!userBubble) {
      const message = el('<div class="msg user"><div class="role">You<span class="chan">voice</span></div><div class="bubble"></div></div>');
      col.appendChild(message);
      userBubble = message.querySelector(".bubble");
    }
    return userBubble;
  }

  function ensureNode() {
    if (!node) {
      ensureUserBubble();
      node = addAssistant("voice");
      setStatus(node, "Listening");
    }
    return node;
  }

  function bubbleHasAnswer(bubble) {
    return !!(bubble && !bubble.querySelector(".typing") && bubble.textContent.trim());
  }

  function finishSpinningSteps(target) {
    if (!target || typeof target.querySelectorAll !== "function") return;
    target.querySelectorAll(".step").forEach((step) => {
      if (!step || typeof step.querySelector !== "function") return;
      const spin = step.querySelector(".spin");
      if (!spin) return;
      spin.outerHTML = '<span class="ic ok">✓</span>';
      const state = step.querySelector(".state");
      if (state && state.textContent === "running…") state.textContent = "passed";
    });
  }

  function dropUnansweredTurn() {
    if (!node) return;
    const bubble = node.querySelector(".bubble");
    if (bubbleHasAnswer(bubble)) {
      finishSpinningSteps(node);
      userBubble = null;
      node = null;
      return;
    }
    node.remove();
    node = null;
  }

  function onTurnEnd(data) {
    if (typeof turnRunning !== "undefined") turnRunning = false;
    if (data.reason === "empty") {
      dropUnansweredTurn();
      return;
    }
    if (data.reason === "interrupted") {
      if (!node) return;
      const bubble = node.querySelector(".bubble");
      // Keep a reply that already arrived. The next utterance gets its own bubble.
      if (bubbleHasAnswer(bubble)) {
        finishSpinningSteps(node);
        userBubble = null;
        node = null;
        return;
      }
      node.querySelectorAll('.step:not([data-key="stt"])').forEach((step) => step.remove());
      const pill = node.querySelector(".pill");
      if (pill) pill.textContent = node.querySelectorAll(".step").length;
      if (bubble) bubble.innerHTML = '<span class="typing"><span class="spin"></span>Listening…</span>';
      return;
    }
    userBubble = null;
    node = null;
  }

  function onMessage(event) {
    if (event.data instanceof ArrayBuffer) {
      if (ignoreAudio || pttActive || speaking) return;
      playChunk(event.data);
      return;
    }
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (err) {
      return;
    }
    switch (data.type) {
      case "partial_transcript":
        ensureUserBubble().textContent = data.text;
        if (pttActive || (speaking && !pttTailTimer)) setVoiceStatus("listening…");
        scroll();
        break;
      case "processing":
        turnRunning = true;
        ignoreAudio = false;
        ensureNode();
        if (typeof demoMode !== "function" || demoMode() !== "quick") {
          setStatus(node, "Running the pipeline");
        }
        setVoiceStatus("thinking…");
        break;
      case "response_text":
        ignoreAudio = false;
        ensureNode().querySelector(".bubble").innerHTML = md(data.text || "");
        userBubble = null;
        scroll();
        break;
      case "blocked":
        turnRunning = false;
        ensureNode().classList.add("blocked");
        node.querySelector(".bubble").textContent = data.response;
        scroll();
        break;
      case "final":
        renderEvent(ensureNode(), data);
        break;
      case "timing":
      case "cost":
        break;
      case "error":
        turnRunning = false;
        if (/not logged in/i.test(data.message || data.error || "")) {
          if (typeof forgetShopper === "function") forgetShopper();
          location.reload();
          return;
        }
        ensureNode().querySelector(".bubble").textContent = "Voice error: " + (data.message || data.error);
        scroll();
        break;
      case "turn_end":
        onTurnEnd(data);
        if (voiceOn && !agentSpeaking && !speaking && !pttActive) {
          setVoiceStatus(pttPaused ? "" : "listening…");
        }
        break;
      default:
        if ((data.type === "stage" || data.type === "step") && data.key === "stt") ensureNode();
        if (node) renderEvent(node, data);
    }
  }

  async function startVoice(opts) {
    if (typeof USER === "undefined" || !USER) {
      alert("Sign in first, then use voice.");
      return;
    }
    if (startingVoice) return startingVoice;
    const pttMode = !!(opts && opts.ptt);
    startingVoice = (async () => {
      window.csVoiceOn = true;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      playCtx = new AudioCtx();
      if (playCtx.state === "suspended") await playCtx.resume();
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/voice/ws?user_id=${encodeURIComponent(USER)}`);
      ws.binaryType = "arraybuffer";
      ws.onmessage = onMessage;
      ws.onclose = () => { if (voiceOn) stopVoice(); };
      await new Promise((resolve, reject) => {
        ws.onopen = resolve;
        ws.onerror = reject;
      });
      sendDemoMode();
      sendGuardrails();
      await startCapture();
      voiceOn = true;
      muted = false;
      pttPaused = pttMode;
      const chips = document.getElementById("chips");
      if (chips) chips.remove();
      holdBtn.style.display = "none";
      setVoiceStatus(pttMode ? "" : "listening…");
    })();
    try {
      await startingVoice;
    } finally {
      startingVoice = null;
    }
  }

  function stopVoice() {
    clearPttTail();
    voiceOn = false;
    window.csVoiceOn = false;
    muted = false;
    pttActive = false;
    pttPaused = false;
    micPressHeld = false;
    tabHeld = false;
    turnRunning = false;
    ignoreAudio = false;
    stopCapture();
    stopPlayback();
    if (playCtx) {
      try { playCtx.close(); } catch (err) { /* already closed */ }
      playCtx = null;
    }
    if (ws) {
      try { ws.close(); } catch (err) { /* already closed */ }
      ws = null;
    }
    holdBtn.style.display = "none";
    holdBtn.textContent = "Mute";
    holdBtn.title = "Mute microphone";
    holdBtn.classList.remove("on");
    dropUnansweredTurn();
    setVoiceStatus("");
  }

  function toggleHold() {
    if (!voiceOn) return;
    muted = !muted;
    if (muted) {
      speaking = false;
      frames = [];
      preroll = [];
      onsetCount = 0;
      holdBtn.textContent = "Unmute";
      holdBtn.title = "Unmute microphone";
      holdBtn.classList.add("on");
      setVoiceStatus("muted");
      return;
    }
    holdBtn.textContent = "Mute";
    holdBtn.title = "Mute microphone";
    holdBtn.classList.remove("on");
    setVoiceStatus(agentSpeaking ? "speaking…" : (pttPaused ? "" : "listening…"));
  }

  function onMicPressStart(event) {
    if (event && event.type === "touchstart" && typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    if (typeof USER === "undefined" || !USER) return;
    micPressHeld = true;
    pttDownAt = now();
    holdBtn.style.display = "none";
    if (voiceOn) {
      beginPtt();
      return;
    }
    startVoice({ ptt: true })
      .then(() => {
        if (micPressHeld) {
          beginPtt();
        } else {
          beginPtt();
          releasePtt();
        }
      })
      .catch((err) => {
        stopVoice();
        alert("Could not start voice: " + (err && err.message ? err.message : err));
      });
  }

  function onMicPressEnd() {
    if (!micPressHeld && !pttActive) return;
    micPressHeld = false;
    holdBtn.style.display = "none";
    if (pttActive) {
      releasePtt();
      return;
    }
    pttPaused = true;
    speaking = false;
    setVoiceStatus("");
  }

  micBtn.onmousedown = onMicPressStart;
  micBtn.onmouseup = onMicPressEnd;
  micBtn.ontouchstart = onMicPressStart;
  micBtn.ontouchend = onMicPressEnd;
  micBtn.ontouchcancel = onMicPressEnd;
  window.addEventListener("mouseup", () => {
    if (micPressHeld || pttActive) onMicPressEnd();
  });
  micBtn.onclick = () => {
    holdBtn.style.display = "none";
    if (pttReleased) {
      pttReleased = false;
      return;
    }
    if (pttActive || speaking || !pttPaused) {
      micPressHeld = false;
      pttPaused = true;
      if (pttActive) {
        releasePtt();
      } else if (speaking) {
        endUtterance(true);
      } else {
        setVoiceStatus("");
      }
    }
  };
  window.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    if (typeof USER === "undefined" || !USER) return;
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (!tabHeld && (tag === "INPUT" || tag === "TEXTAREA")) return;
    event.preventDefault();
    if (event.repeat) return;
    tabHeld = true;
    if (!voiceOn) {
      startVoice({ ptt: true })
        .then(() => {
          if (tabHeld) {
            beginPtt();
          } else {
            pttActive = false;
            pttPaused = true;
            speaking = false;
            setVoiceStatus("");
          }
        })
        .catch(() => stopVoice());
      return;
    }
    beginPtt();
  });
  window.addEventListener("keyup", (event) => {
    if (event.key !== "Tab") return;
    tabHeld = false;
    if (!pttActive) return;
    event.preventDefault();
    holdBtn.style.display = "none";
    releasePtt();
  });
  holdBtn.onclick = toggleHold;
  window.addEventListener("cs:logout", () => {
    try { stopVoice(); } catch (err) { /* page is going away */ }
  });
})();
