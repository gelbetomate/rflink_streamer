class RFLinkStreamerOnboarding extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._entryId) {
      const panelConfig = this._panel?.config || {};
      this._entryId = panelConfig.entry_id;
    }
    if (!this._initialized) {
      this._initialized = true;
      this._load();
    }
  }

  set panel(panel) {
    this._panel = panel;
    this._entryId = panel?.config?.entry_id || this._entryId;
  }

  connectedCallback() {
    this.style.display = "block";
    this.style.padding = "16px";
    this.style.maxWidth = "1200px";
    this.style.margin = "0 auto";
    this.innerHTML = this._renderShell();
    this._bindEvents();
  }

  _renderShell() {
    return `
      <style>
        :host {
          color-scheme: light dark;
          --rflink-bg: linear-gradient(135deg, color-mix(in srgb, var(--primary-color) 10%, transparent), transparent 40%), var(--primary-background-color);
          --rflink-card: var(--card-background-color);
          --rflink-border: var(--divider-color);
          --rflink-text: var(--primary-text-color);
          --rflink-muted: var(--secondary-text-color);
          --rflink-primary: var(--primary-color);
          --rflink-primary-2: var(--accent-color);
          --rflink-warn: var(--error-color);
          font-family: "Segoe UI", "Trebuchet MS", sans-serif;
        }
        .root {
          background: var(--rflink-bg);
          border: 1px solid var(--rflink-border);
          border-radius: 18px;
          padding: 16px;
          box-shadow: var(--ha-card-box-shadow, none);
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 16px;
        }
        .title {
          font-size: 1.4rem;
          font-weight: 700;
          letter-spacing: 0.02em;
        }
        .subtitle {
          color: var(--rflink-muted);
          font-size: 0.92rem;
        }
        .actions {
          display: flex;
          gap: 8px;
        }
        button {
          border: 1px solid var(--rflink-border);
          background: var(--secondary-background-color);
          color: var(--rflink-text);
          border-radius: 10px;
          padding: 8px 12px;
          cursor: pointer;
          font-weight: 600;
        }
        button.primary {
          border-color: var(--rflink-primary);
          background: linear-gradient(90deg, var(--rflink-primary), var(--rflink-primary-2));
          color: #fff;
        }
        button.warn {
          border-color: var(--rflink-warn);
          color: var(--rflink-warn);
        }
        .grid {
          display: grid;
          gap: 12px;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        }
        .card {
          background: var(--rflink-card);
          border: 1px solid var(--rflink-border);
          border-radius: 12px;
          padding: 12px;
        }
        .card h3 {
          margin: 0 0 10px;
          font-size: 1.05rem;
        }
        .list {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-height: 58vh;
          overflow: auto;
          padding-right: 2px;
        }
        .device {
          border: 1px solid var(--rflink-border);
          border-radius: 10px;
          padding: 10px;
          background: var(--secondary-background-color);
          display: grid;
          gap: 8px;
        }
        .line {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          font-size: 0.92rem;
        }
        .muted {
          color: var(--rflink-muted);
        }
        .row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        input, select {
          border: 1px solid var(--rflink-border);
          border-radius: 8px;
          padding: 7px 8px;
          font-size: 0.9rem;
          min-width: 120px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        .helper {
          color: var(--rflink-muted);
          font-size: 0.85rem;
          margin-top: -2px;
        }
        .status {
          margin-top: 10px;
          color: var(--rflink-muted);
          min-height: 20px;
        }
      </style>
      <div class="root">
        <div class="header">
          <div>
            <div class="title">RFLink Device Onboarding</div>
            <div class="subtitle">Review discovered devices, test incoming payload, and add entities without using options flow.</div>
          </div>
          <div class="actions">
            <button id="toggle-sidebar">Hide Sidebar Entry</button>
            <button class="primary" id="refresh">Refresh</button>
          </div>
        </div>
        <div class="grid">
          <section class="card">
            <h3>Pending Devices</h3>
            <div id="pending" class="list"></div>
          </section>
          <section class="card">
            <h3>Added Devices</h3>
            <div id="added" class="list"></div>
          </section>
        </div>
        <div id="status" class="status"></div>
      </div>
    `;
  }

  _bindEvents() {
    const refreshBtn = this.querySelector("#refresh");
    const toggleSidebarBtn = this.querySelector("#toggle-sidebar");
    refreshBtn?.addEventListener("click", () => this._load());
    toggleSidebarBtn?.addEventListener("click", () => this._toggleSidebar());
  }

  async _load() {
    if (!this._hass || !this._entryId) {
      this._setStatus("Missing Home Assistant context or entry id.");
      return;
    }

    try {
      const result = await this._hass.callWS({
        type: "rflink_streamer/onboarding/list",
        entry_id: this._entryId,
      });
      this._sidebarEnabled = !!result.sidebar_enabled;
      this._renderSidebarButton();
      this._renderLists(result.pending || [], result.added || []);
      this._setStatus(`Loaded ${result.pending.length} pending, ${result.added.length} added.`);
    } catch (err) {
      this._setStatus(`Failed to load devices: ${err?.message || err}`);
    }
  }

  _renderLists(pending, added) {
    const pendingEl = this.querySelector("#pending");
    const addedEl = this.querySelector("#added");
    if (!pendingEl || !addedEl) {
      return;
    }

    const mergeTargets = [...new Set(added.map((item) => item.canonical_id).filter(Boolean))].sort();

    pendingEl.innerHTML = "";
    addedEl.innerHTML = "";

    if (pending.length === 0) {
      pendingEl.innerHTML = '<div class="muted">No pending devices.</div>';
    } else {
      pending.forEach((item) => pendingEl.appendChild(this._renderPending(item, mergeTargets)));
    }

    if (added.length === 0) {
      addedEl.innerHTML = '<div class="muted">No added devices yet.</div>';
    } else {
      added.forEach((item) => addedEl.appendChild(this._renderAdded(item)));
    }
  }

  _renderSidebarButton() {
    const button = this.querySelector("#toggle-sidebar");
    if (!button) {
      return;
    }
    button.textContent = this._sidebarEnabled ? "Hide Sidebar Entry" : "Show Sidebar Entry";
  }

  _renderPending(item, mergeTargets) {
    const wrapper = document.createElement("div");
    wrapper.className = "device";

    const defaultName = item.canonical_id || item.raw_device_id;
    const selectedPlatform = item.preferred_platform || item.platform || "light";

    wrapper.innerHTML = `
      <div class="line"><strong>${item.raw_device_id}</strong><span class="muted">${item.protocol}</span></div>
      <div class="line"><span class="muted">Detected platform: ${item.platform}</span><span class="muted">${item.last_seen || "never"}</span></div>
      <div class="row">
        <input class="canonical" list="merge-targets-${item.raw_device_id}" value="${defaultName}" placeholder="Merge target / entity base id" />
        <select class="platform">
          ${["light", "switch", "sensor", "binary_sensor"].map((p) => `<option value="${p}" ${selectedPlatform === p ? "selected" : ""}>${p}</option>`).join("")}
        </select>
      </div>
      <div class="helper">Use the same entity base id for two raw devices to merge them into one Home Assistant device.</div>
      <div class="row">
        <button class="primary add">Add / Merge</button>
        <button class="test">Test</button>
        <button class="warn ignore">Ignore</button>
        <button class="delete">Delete</button>
      </div>
      <div class="muted result"></div>
    `;

    let dataList = wrapper.querySelector(`#merge-targets-${item.raw_device_id}`);
    if (!dataList) {
      dataList = document.createElement("datalist");
      dataList.id = `merge-targets-${item.raw_device_id}`;
      mergeTargets.forEach((target) => {
        const option = document.createElement("option");
        option.value = target;
        dataList.appendChild(option);
      });
      wrapper.appendChild(dataList);
    }

    wrapper.querySelector(".add")?.addEventListener("click", async () => {
      const canonical = wrapper.querySelector(".canonical")?.value?.trim();
      const platform = wrapper.querySelector(".platform")?.value;
      await this._add(item.raw_device_id, canonical, platform);
      await this._load();
    });

    wrapper.querySelector(".ignore")?.addEventListener("click", async () => {
      await this._ignore(item.raw_device_id);
      await this._load();
    });

    wrapper.querySelector(".delete")?.addEventListener("click", async () => {
      await this._delete(item.raw_device_id);
      await this._load();
    });

    wrapper.querySelector(".test")?.addEventListener("click", async () => {
      const resultEl = wrapper.querySelector(".result");
      const details = await this._test(item.raw_device_id);
      if (resultEl) {
        resultEl.textContent = details;
      }
    });

    return wrapper;
  }

  _renderAdded(item) {
    const wrapper = document.createElement("div");
    wrapper.className = "device";
    wrapper.innerHTML = `
      <div class="line"><strong>${item.canonical_id}</strong><span class="muted">${item.preferred_platform || item.platform}</span></div>
      <div class="line"><span class="muted">Raw: ${item.raw_device_id}</span><span class="muted">${item.protocol}</span></div>
      <div class="line"><span class="muted">Last seen: ${item.last_seen || "never"}</span></div>
      <div class="row">
        <button class="warn ignore">Ignore</button>
        <button class="delete">Delete</button>
      </div>
    `;

    wrapper.querySelector(".ignore")?.addEventListener("click", async () => {
      await this._ignore(item.raw_device_id);
      await this._load();
    });

    wrapper.querySelector(".delete")?.addEventListener("click", async () => {
      await this._delete(item.raw_device_id);
      await this._load();
    });

    return wrapper;
  }

  async _add(rawDeviceId, canonicalId, platform) {
    try {
      await this._hass.callWS({
        type: "rflink_streamer/onboarding/add",
        entry_id: this._entryId,
        raw_device_id: rawDeviceId,
        canonical_id: canonicalId,
        platform,
      });
      this._setStatus(`Added ${rawDeviceId}.`);
    } catch (err) {
      this._setStatus(`Failed to add ${rawDeviceId}: ${err?.message || err}`);
    }
  }

  async _ignore(rawDeviceId) {
    try {
      await this._hass.callWS({
        type: "rflink_streamer/onboarding/ignore",
        entry_id: this._entryId,
        raw_device_id: rawDeviceId,
      });
      this._setStatus(`Ignored ${rawDeviceId}.`);
    } catch (err) {
      this._setStatus(`Failed to ignore ${rawDeviceId}: ${err?.message || err}`);
    }
  }

  async _delete(rawDeviceId) {
    try {
      await this._hass.callWS({
        type: "rflink_streamer/onboarding/delete",
        entry_id: this._entryId,
        raw_device_id: rawDeviceId,
      });
      this._setStatus(`Deleted ${rawDeviceId}.`);
    } catch (err) {
      this._setStatus(`Failed to delete ${rawDeviceId}: ${err?.message || err}`);
    }
  }

  async _toggleSidebar() {
    try {
      const enabled = !this._sidebarEnabled;
      const result = await this._hass.callWS({
        type: "rflink_streamer/onboarding/set_sidebar",
        entry_id: this._entryId,
        enabled,
      });
      this._sidebarEnabled = !!result.sidebar_enabled;
      this._renderSidebarButton();
      this._setStatus(this._sidebarEnabled ? "Sidebar entry enabled." : "Sidebar entry hidden.");
    } catch (err) {
      this._setStatus(`Failed to toggle sidebar entry: ${err?.message || err}`);
    }
  }

  async _test(rawDeviceId) {
    try {
      const payload = await this._hass.callWS({
        type: "rflink_streamer/onboarding/test",
        entry_id: this._entryId,
        raw_device_id: rawDeviceId,
      });
      const state = payload.state === undefined || payload.state === null ? "n/a" : JSON.stringify(payload.state);
      const measurements = Object.keys(payload.measurements || {});
      return `State: ${state}. Measurements: ${measurements.join(", ") || "none"}.`;
    } catch (err) {
      return `No recent payload: ${err?.message || err}`;
    }
  }

  _setStatus(text) {
    const status = this.querySelector("#status");
    if (status) {
      status.textContent = text;
    }
  }
}

customElements.define("rflink-streamer-onboarding", RFLinkStreamerOnboarding);
