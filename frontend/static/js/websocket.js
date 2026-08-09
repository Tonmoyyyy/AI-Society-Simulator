/**
 * Connects to /ws/feed and dispatches a `asim:ws-message` CustomEvent with
 * the parsed payload for pages to listen to. Also drives the nav pulse
 * indicator (live/not-live) so it reflects a real connection, not a fake
 * always-on animation.
 */
const AsimSocket = (() => {
  let socket = null;
  let reconnectTimer = null;

  function setPulse(live) {
    document.querySelectorAll(".sim-pulse").forEach((el) => {
      el.classList.toggle("live", live);
      const label = el.querySelector(".pulse-label");
      if (label) label.textContent = live ? "Live" : "Offline";
    });
  }

  function connect() {
    try {
      socket = new WebSocket(window.ASIM_CONFIG.WS_URL);
    } catch (_) {
      setPulse(false);
      return;
    }

    socket.onopen = () => setPulse(true);
    socket.onclose = () => {
      setPulse(false);
      reconnectTimer = setTimeout(connect, 4000);
    };
    socket.onerror = () => {
      setPulse(false);
    };
    socket.onmessage = (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch (_) {
        return;
      }
      document.dispatchEvent(new CustomEvent("asim:ws-message", { detail: payload }));
    };
  }

  function init() {
    connect();
    window.addEventListener("beforeunload", () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) socket.close();
    });
  }

  return { init };
})();
