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
    this.innerHTML = this._renderShell();
    this._bindEvents();
  }

  _renderShell() {
    return `
      <style>
        :host {
          color-scheme: light dark;
          --rflink-bg: var(--primary-background-color);
          --rflink-card: var(--card-background-color);
          --rflink-border: var(--divider-color);
          --rflink-text: var(--primary-text-color);
          --rflink-muted: var(--secondary-text-color);
          --rflink-primary: var(--primary-color);
          --rflink-surface: var(--secondary-background-color);
          --rflink-secondary: var(--secondary-text-color);
          --rflink-warn: var(--error-color);
          font-family: "Segoe UI", "Trebuchet MS", sans-serif;
        }
        .root {
          background: var(--rflink-bg);
          min-height: 100vh;
        }
        ha-top-app-bar-fixed {
          --mdc-theme-primary: var(--app-header-background-color, var(--primary-color));
          --app-header-text-color: var(--app-header-text-color, #fff);
        }
        .title-wrap {
          display: flex;
          align-items: center;
          gap: 12px;
          min-width: 0;
        }
        .title-wrap ha-icon {
          color: var(--app-header-text-color, #fff);
          --mdc-icon-size: 22px;
        }
        .title-text {
          font-size: 1.25rem;
          font-weight: 600;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .content {
          max-width: 1200px;
          margin: 0 auto;
          padding: 16px;
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          justify-content: flex-end;
          margin-bottom: 16px;
        }
        .id-filter {
          min-width: 260px;
          max-width: 420px;
          width: 100%;
        }
        button {
          border: 1px solid transparent;
          background: var(--rflink-surface);
          color: var(--rflink-text);
          border-radius: 999px;
          padding: 8px 12px;
          cursor: pointer;
          font-weight: 600;
        }
        button.primary {
          background: var(--rflink-primary);
          color: var(--text-primary-color, #fff);
        }
        button.warn {
          background: var(--rflink-warn);
          color: var(--text-primary-color, #fff);
        }
        button.subtle {
          border-color: var(--rflink-border);
          background: var(--rflink-card);
          color: var(--rflink-text);
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
        details.raw-details {
          color: var(--rflink-muted);
          font-size: 0.85rem;
        }
        details.raw-details summary {
          cursor: pointer;
          user-select: none;
          list-style: none;
        }
        details.raw-details summary::-webkit-details-marker {
          display: none;
        }
        .raw-text {
          margin-top: 6px;
          word-break: break-word;
          color: var(--rflink-text);
          font-family: monospace;
          white-space: pre-wrap;
        }
        .status {
          margin-top: 10px;
          color: var(--rflink-muted);
          min-height: 20px;
        }
      </style>
      <div class="root">
        <ha-top-app-bar-fixed>
          <div slot="title" class="title-wrap">
            <ha-icon icon="mdi:radio-tower"></ha-icon>
            <div class="title-text">RFLink Onboarding</div>
          </div>
        </ha-top-app-bar-fixed>
        <div class="content">
          <div class="actions">
            <input class="id-filter" id="id-filter" placeholder="Filter by ID/protocol/raw line" />
            <button class="primary" id="refresh">Refresh</button>
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
      </div>
    `;
  }

  _bindEvents() {
    const refreshBtn = this.querySelector("#refresh");
    const filterInput = this.querySelector("#id-filter");
    refreshBtn?.addEventListener("click", () => this._load());
    filterInput?.addEventListener("input", (event) => {
      this._idFilter = (event.target?.value || "").toLowerCase().trim();
      this._renderLists(this._pendingDevices || [], this._addedDevices || []);
    });
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
      this._pendingDevices = result.pending || [];
      this._addedDevices = result.added || [];
      this._renderLists(this._pendingDevices, this._addedDevices);
      this._setStatus(`Loaded ${this._pendingDevices.length} pending, ${this._addedDevices.length} added.`);
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

    const visiblePending = pending.filter((item) => this._matchesFilter(item));
    const visibleAdded = added.filter((item) => this._matchesFilter(item));
    const mergeTargets = [...new Set(added.map((item) => item.canonical_id).filter(Boolean))].sort();

    pendingEl.innerHTML = "";
    addedEl.innerHTML = "";

    if (visiblePending.length === 0) {
      pendingEl.innerHTML = '<div class="muted">No pending devices.</div>';
    } else {
      visiblePending.forEach((item) => pendingEl.appendChild(this._renderPending(item, mergeTargets)));
    }

    if (visibleAdded.length === 0) {
      addedEl.innerHTML = '<div class="muted">No added devices yet.</div>';
    } else {
      visibleAdded.forEach((item) => addedEl.appendChild(this._renderAdded(item)));
    }
  }

  _matchesFilter(item) {
    const filter = this._idFilter || "";
    if (!filter) {
      return true;
    }
    const haystack = [
      item.raw_device_id,
      item.canonical_id,
      item.protocol,
      item.platform,
      item.preferred_platform,
      item.last_raw_string,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(filter);
  }

  _renderPending(item, mergeTargets) {
    const wrapper = document.createElement("div");
    wrapper.className = "device";

    const defaultName = item.canonical_id || item.raw_device_id;
    const selectedPlatform = item.preferred_platform || item.platform || "light";

    wrapper.innerHTML = `
      <div class="line"><strong>${item.raw_device_id}</strong><span class="muted">${item.protocol}</span></div>
      <div class="line"><span class="muted">Detected platform: ${item.platform}</span><span class="muted">${item.last_seen || "never"}</span></div>
      <details class="raw-details">
        <summary>Raw RFLink line</summary>
        <div class="raw-text">${item.last_raw_string || "n/a"}</div>
      </details>
      <div class="row">
        <input class="canonical" list="merge-targets-${item.raw_device_id}" value="${defaultName}" placeholder="Merge target / entity base id" />
        <select class="platform">
          ${["light", "switch", "sensor", "binary_sensor"].map((p) => `<option value="${p}" ${selectedPlatform === p ? "selected" : ""}>${p}</option>`).join("")}
        </select>
      </div>
      <div class="helper">Use the same entity base id for two raw devices to merge them into one Home Assistant device.</div>
      <div class="row">
        <button class="primary add">Add / Merge</button>
        <button class="subtle test">Test</button>
        <button class="warn ignore">Ignore</button>
        <button class="subtle delete">Delete</button>
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
      <details class="raw-details">
        <summary>Raw RFLink line</summary>
        <div class="raw-text">${item.last_raw_string || "n/a"}</div>
      </details>
      <div class="row">
        <button class="subtle restore">Restore</button>
        <button class="warn ignore">Ignore</button>
        <button class="subtle delete">Delete</button>
      </div>
    `;

    wrapper.querySelector(".restore")?.addEventListener("click", async () => {
      await this._restore(item.raw_device_id);
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

  async _restore(rawDeviceId) {
    try {
      await this._hass.callWS({
        type: "rflink_streamer/onboarding/restore",
        entry_id: this._entryId,
        raw_device_id: rawDeviceId,
      });
      this._setStatus(`Restored ${rawDeviceId} to pending.`);
    } catch (err) {
      this._setStatus(`Failed to restore ${rawDeviceId}: ${err?.message || err}`);
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
