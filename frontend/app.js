
const messages = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const trace = document.querySelector("#trace");
const overview = document.querySelector("#overview");
const deviceGrid = document.querySelector("#deviceGrid");
const simSummary = document.querySelector("#simSummary");


async function loadSimulator() {
  try {
    const res = await fetch("/api/simulator");
    if (!res.ok) throw new Error("Simulator request failed");
    renderSimulator(await res.json());
  } catch (error) {
    console.error("Simulator load failed:", error);
    deviceGrid.innerHTML = '<p class="error">Simulator unavailable. Check the server.</p>';
  }
}

function renderSimulator(state) {
  simSummary.innerHTML = `
    <div class="sim-stat"><span>Projected daily energy</span><strong>${state.total_projected_daily_kwh} kWh</strong></div>
    <div class="sim-stat"><span>Estimated daily cost</span><strong>₹${state.projected_daily_cost}</strong></div>
    <div class="sim-stat"><span>Accumulated simulated energy</span><strong>${state.accumulated_energy_kwh} kWh</strong></div>
    <div class="sim-stat"><span>Accumulated simulated cost</span><strong>₹${state.accumulated_cost}</strong></div>
    <div class="sim-stat"><span>Simulated time</span><strong>${state.simulated_time_label}</strong></div>
    <div class="sim-stat"><span>30-day total (incl. fixed charge)</span><strong>₹${state.projected_monthly_total_cost}</strong></div>
    <div class="sim-stat"><span>Tariff</span><strong>₹${state.tariff.rate_per_kwh}/kWh</strong></div>
  `;
  const alertBox = document.querySelector("#simAlerts");
  const alertCount = document.querySelector("#alertCount");
  const alerts = state.alerts || [];
  const currentAlertIds = new Set(alerts.map(alert => alert.id));
  // Treat alerts already active when the page opens as existing history: show them
  // as text, but do not speak them. Only incidents appearing after the first load
  // are announced automatically.
  const newlyActive = knownAlertIds === null
    ? []
    : alerts.filter(alert => !knownAlertIds.has(alert.id));
  if (newlyActive.length && alertVoiceEnabled && voiceEnabled) {
    const spoken = newlyActive.map(alert =>
      `Energy alert. ${alert.appliance}. ${alert.severity} usage warning. ` +
      `${alert.message} Estimated extra cost ${alert.estimated_additional_cost_day} rupees per day.`
    ).join(' ');
    speakAlert(spoken);
  }
  knownAlertIds = currentAlertIds;
  alertCount.textContent = `${alerts.length} active`;
  alertCount.className = `status ${alerts.length ? "on" : "off"}`;
  alertBox.innerHTML = alerts.length ? alerts.map(alert => `
    <article class="alert-item ${alert.severity}">
      <strong>${alert.appliance}: High energy usage detected.</strong>
      <p>${alert.appliance} is using more energy than its baseline.</p>
      <small>Baseline: ${alert.baseline_kwh_day} kWh/day · Projected: ${alert.observed_kwh_day} kWh/day · Extra cost: ₹${alert.estimated_additional_cost_day}/day</small>
    </article>`).join("") : '<p class="no-alert">No appliance is currently above its configured baseline threshold.</p>';
  const opportunities = state.savings_opportunities || [];
  document.querySelector("#savingsList").innerHTML = opportunities.length ? opportunities.map(item => `
    <article class="saving-item"><strong>Review ${item.name} usage</strong><p>${item.additional_kwh} extra kWh/day above baseline.</p><b>Up to ₹${item.estimated_additional_cost}/day savings.</b></article>`).join("") : '<p class="no-alert">No above-baseline savings opportunity detected.</p>';

  deviceGrid.innerHTML = state.devices.map(device => `
    <article class="device-card">
      <div class="device-top">
        <div><span class="device-room">${device.room}</span><h3>${device.name}</h3></div>
        <span class="status ${device.is_on ? "on" : "off"}">${device.is_on ? "Running" : "Off"}</span>
      </div>
      <p class="device-power">${device.power_kw} kW rated power</p>
      <label class="switch-row">
        <span>Device power</span>
        <input type="checkbox" class="device-toggle" data-id="${device.id}" ${device.is_on ? "checked" : ""} aria-label="Switch ${device.name} ${device.is_on ? "off" : "on"}">
      </label>
      <label class="hours-row" for="hours-${device.id}">
        <span>Scheduled hours/day</span><strong>${device.scheduled_hours} h</strong>
      </label>
      <input id="hours-${device.id}" class="hours-input" type="range" min="0" max="24" step="0.5" value="${device.scheduled_hours}" data-id="${device.id}">
      <div class="device-metrics">
        <div><span>Projected energy</span><strong>${device.projected_daily_kwh} kWh/day</strong></div>
        <div><span>Projected cost</span><strong>₹${device.estimated_daily_cost}/day</strong></div>
      </div>
      ${device.additional_kwh > 0 ? `<p class="device-warning">Above baseline by ${device.additional_kwh} kWh/day (estimated +₹${device.estimated_additional_cost}/day)</p>` : ""}
    </article>
  `).join("");

  deviceGrid.querySelectorAll(".device-toggle").forEach(control => {
    control.addEventListener("change", async () => {
      await updateSimulator({id: control.dataset.id, is_on: control.checked});
    });
  });
  deviceGrid.querySelectorAll(".hours-input").forEach(control => {
    const label = deviceGrid.querySelector(`label[for="hours-${control.dataset.id}"] strong`);
    control.addEventListener("input", () => { if (label) label.textContent = `${control.value} h`; });
    control.addEventListener("change", async () => {
      await updateSimulator({id: control.dataset.id, scheduled_hours: Number(control.value)});
    });
  });
}

async function updateSimulator(payload) {
  try {
    const result = await post("/api/simulator/update", payload);
    renderSimulator(result);
    await loadOverview();
  } catch (error) {
    console.error("Simulator update failed:", error);
    addMessage("assistant", "Could not update the virtual appliance. Please try again.");
    await loadSimulator();
  }
}

document.querySelector("#simAdvanceBtn").addEventListener("click", async () => {
  const button = document.querySelector("#simAdvanceBtn");
  button.disabled = true;
  try {
    const result = await post("/api/simulator/advance", { minutes: 60 });
    renderSimulator(result);
    await loadOverview();
  } catch (error) {
    console.error("Could not advance simulation:", error);
    addMessage("assistant", "Could not advance simulated time. Check the server output.");
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#simResetBtn").addEventListener("click", async () => {
  try {
    const result = await post("/api/simulator/reset");
    renderSimulator(result);
    await loadOverview();
  } catch (error) {
    console.error("Simulator reset failed:", error);
    addMessage("assistant", "Could not reset the virtual home.");
  }
});


// Voice settings
const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition;

let recognition = null;
let isListening = false;
let voiceEnabled = true;
let alertVoiceEnabled = true;
let knownAlertIds = null;

// Create voice controls without requiring changes to HTML.
const micButton = document.createElement("button");
micButton.type = "button";
micButton.id = "micBtn";
micButton.textContent = "🎙️ Speak";
micButton.setAttribute("aria-label", "Start voice input");

const voiceButton = document.createElement("button");
voiceButton.type = "button";
voiceButton.id = "voiceToggleBtn";
voiceButton.textContent = "🔊 Voice on";
voiceButton.setAttribute("aria-pressed", "true");

const alertVoiceButton = document.createElement("button");
alertVoiceButton.type = "button";
alertVoiceButton.id = "alertVoiceToggleBtn";
alertVoiceButton.textContent = "🔔 Alerts spoken";
alertVoiceButton.setAttribute("aria-pressed", "true");

const readAlertsButton = document.createElement("button");
readAlertsButton.type = "button";
readAlertsButton.id = "readAlertsBtn";
readAlertsButton.textContent = "▶ Read active alerts";

const voiceStatus = document.createElement("span");
voiceStatus.id = "voiceStatus";
voiceStatus.setAttribute("role", "status");
voiceStatus.setAttribute("aria-live", "polite");
voiceStatus.textContent = SpeechRecognition
  ? "Voice input ready."
  : "Voice input unavailable. You can type instead.";

const submitButton = form.querySelector('button[type="submit"]');

if (submitButton) {
  form.insertBefore(micButton, submitButton);
  form.insertBefore(voiceButton, submitButton);
  form.insertBefore(alertVoiceButton, submitButton);
  form.insertBefore(readAlertsButton, submitButton);
  form.appendChild(voiceStatus);
} else {
  form.append(micButton, voiceButton, alertVoiceButton, readAlertsButton, voiceStatus);
}

micButton.disabled = !SpeechRecognition;

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function speakText(text, interrupt = true) {
  if (!("speechSynthesis" in window)) {
    voiceStatus.textContent = "Speech output is unavailable in this browser.";
    return;
  }
  if (interrupt) window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-IN";
  utterance.rate = 1;
  utterance.onerror = () => {
    voiceStatus.textContent = "Speech output failed; text remains available.";
  };
  window.speechSynthesis.speak(utterance);
}

function speak(text) {
  if (!voiceEnabled) return;
  speakText(text, true);
}

function speakAlert(text) {
  if (!voiceEnabled || !alertVoiceEnabled) return;
  // Alerts interrupt a long answer so the warning is heard promptly.
  speakText(text, true);
}

function activeAlertSpeech() {
  const items = [...document.querySelectorAll("#simAlerts .alert-item")];
  if (!items.length) return "There are no active energy alerts.";
  return "Active energy alerts. " + items.map(item => item.innerText.replace(/\s+/g, " ")).join(". ");
}

async function post(url, body = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function chat(message) {
  addMessage("user", message);

  try {
    const result = await post("/api/chat", { message });

    addMessage("assistant", result.reply);
    const traceJson = result.trace && result.trace.length
      ? JSON.stringify(result.trace, null, 2)
      : "No tool calls were recorded for this response.";
    const traceLabel = result.engine === "simulator_fallback"
      ? "DETERMINISTIC SIMULATOR FALLBACK — Ollama/MCP unavailable; these are direct local simulator-tool calls.\n\n"
      : result.engine === "ollama_mcp"
        ? "LIVE OLLAMA + MCP TOOL TRACE\n\n"
        : "SIMULATOR TOOL TRACE\n\n";
    trace.textContent = traceLabel + traceJson;

    speak(result.reply);
    await loadOverview();
  } catch (error) {
    console.error("Billie chat error:", error);
    const message =
      "Sorry, I could not reach Billie. Please check that the server is running and try again.";

    addMessage("assistant", message);
    voiceStatus.textContent = "Chat request failed.";
    speak(message);
  }
}

async function loadOverview() {
  try {
    const res = await fetch("/api/overview");
    if (!res.ok) throw new Error("Overview request failed");

    const data = await res.json();
    const comparison = data.bill.comparison || {};
    const activeAlerts = data.alerts.active || [];

    overview.innerHTML = `
      <div class="metric"><b>Today</b>${data.usage.total_kwh_today} kWh modeled usage</div>
      <div class="metric"><b>Household appliances</b>${data.usage.readings.length} modeled appliance readings available</div>
      <div class="metric"><b>Simulated bill vs baseline</b>₹${comparison.current_amount} projected vs ₹${comparison.previous_amount} baseline, difference ₹${comparison.difference}<small>30-day estimate · synthetic simulator data</small></div>
      <div class="metric"><b>Active energy alerts</b>${activeAlerts.length} current simulator alert${activeAlerts.length === 1 ? "" : "s"}</div>
    `;
  } catch (error) {
    console.error("Billie overview error:", error);
  }
}

// Set up browser speech recognition when supported.
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    isListening = true;
    micButton.textContent = "🎙️ Listening...";
    voiceStatus.textContent = "Listening. Speak now.";
  };

  recognition.onresult = async (event) => {
    const transcript = event.results[0][0].transcript.trim();

    if (!transcript) {
      voiceStatus.textContent = "No speech detected. Please try again.";
      return;
    }

    input.value = transcript;
    voiceStatus.textContent = `Heard: "${transcript}"`;

    await chat(transcript);
  };

  recognition.onerror = (event) => {
    const messages = {
      "not-allowed": "Microphone permission denied. You can type instead.",
      "no-speech": "No speech detected. Please try again.",
      "audio-capture": "No microphone was detected.",
      "network": "Speech recognition network error. You can type instead.",
    };

    voiceStatus.textContent =
      messages[event.error] || `Voice input error: ${event.error}`;
  };

  recognition.onend = () => {
    isListening = false;
    micButton.textContent = "🎙️ Speak";
  };
}

micButton.addEventListener("click", () => {
  if (!recognition) return;

  if (isListening) {
    recognition.stop();
    return;
  }

  // Avoid reading a previous answer while capturing new speech.
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }

  try {
    recognition.start();
  } catch (error) {
    console.error("Could not start speech recognition:", error);
    voiceStatus.textContent =
      "Could not start the microphone. Please try again or type instead.";
  }
});

voiceButton.addEventListener("click", () => {
  voiceEnabled = !voiceEnabled;

  voiceButton.textContent = voiceEnabled ? "🔊 Voice on" : "🔇 Voice off";
  voiceButton.setAttribute("aria-pressed", String(voiceEnabled));

  if (!voiceEnabled && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }

  voiceStatus.textContent = voiceEnabled
    ? "Spoken responses enabled."
    : "Spoken responses disabled. Text replies remain available.";
});

alertVoiceButton.addEventListener("click", () => {
  alertVoiceEnabled = !alertVoiceEnabled;
  alertVoiceButton.textContent = alertVoiceEnabled ? "🔔 Alerts spoken" : "🔕 Alerts muted";
  alertVoiceButton.setAttribute("aria-pressed", String(alertVoiceEnabled));
  voiceStatus.textContent = alertVoiceEnabled
    ? "New energy alerts will be spoken aloud."
    : "Automatic spoken alerts muted; visual alerts remain available.";
});

readAlertsButton.addEventListener("click", () => {
  if (!voiceEnabled) {
    voiceStatus.textContent = "Turn Voice on first to hear alerts.";
    return;
  }
  speakAlert(activeAlertSpeech());
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  await chat(message);
});

document.querySelector("#resetBtn").addEventListener("click", async () => {
  try {
    await post("/api/demo/reset");

    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }

    messages.innerHTML = "";
    trace.textContent = "Demo state reset.";
    addMessage("assistant", "Demo state reset. Synthetic data is ready.");
    voiceStatus.textContent = "Demo reset complete.";

    await loadOverview();
  } catch (error) {
    console.error("Demo reset failed:", error);
    addMessage("assistant", "Could not reset the demo. Please try again.");
  }
});

document.querySelector("#evalBtn").addEventListener("click", () =>
  chat("Evaluate household appliance usage and alert policy")
);

document.querySelector("#worsenBtn").addEventListener("click", async () => {
  try {
    await post("/api/demo/worsen");
    await chat("Re-evaluate household appliance usage after simulated worsening");
  } catch (error) {
    console.error("Could not worsen demo usage:", error);
    addMessage("assistant", "Could not update demo usage. Please try again.");
  }
});

// The button click is the user's explicit confirmation of this
// specific simulated action. The backend must still validate it.
document.querySelector("#actionBtn").addEventListener("click", () =>
  chat("I want to adjust an appliance routine")
);

addMessage(
  "assistant",
  "Hi, I'm Billie. Ask me about your modeled electricity usage or bill. You can type or use the microphone. I can explain findings and demonstrate simulated actions; I do not control real appliances."
);

loadOverview();
loadSimulator();


/* Quick prompts use the same chat path as typed questions. */
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", async () => { await chat(button.dataset.prompt); });
});


// Automatic background monitoring: new alert incidents are detected without
// requiring the user to press "Read active alerts". Stable alert IDs ensure
// an active incident is announced once, not repeatedly on each poll.
const ALERT_POLL_INTERVAL_MS = 5000;
setInterval(() => {
  if (document.visibilityState === "visible") {
    // Refresh overview as well as simulator: active alerts are rendered from
    // /api/overview, so polling only the simulator misses new alert incidents.
    loadOverview();
    loadSimulator();
  }
}, ALERT_POLL_INTERVAL_MS);
