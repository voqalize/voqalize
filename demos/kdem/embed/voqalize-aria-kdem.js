/*
  Voqalize · Aria for karnatakadigital.in
  Plain JavaScript: paste into any "Custom JavaScript" box as it is. For an HTML box
  (Elementor Pro → Custom Code, Location: end of body), put it inside a script tag.
  Nothing downloads until a visitor clicks "Talk to Aria", except Aria's picture
  for the button. A call carries on when the visitor moves to another page.
  Remove the snippet to remove Aria.
*/
(function () {
  if (window.__vqAria) return; // pasted twice, or loaded by two plugins: run once
  window.__vqAria = true;

  // ── 1. Configuration (filled in by Voqalize) ─────────────────────────────
  const VQ = {
    agentId: "06ac5fe2-54d1-79b1-8000-c77b136e76ef",
    publishableKey: "pk_live_eJOBDwN-zWHGqb9OPTYXeO5WPWzQhoYnlfRBnfR1tSY", // works only on karnatakadigital.in
    character: "tara",                                // female avatar; voice (Gauri) is set by Voqalize
    api: "https://app.dev.voqalize.com/api/v1/sessions.connect", // dev hosting for the pilot
  };
  // Exact versions, from jsDelivr. The transport imports the same pipecat URLs,
  // so the page holds one copy of each.
  const LIBS = {
    client: "https://cdn.jsdelivr.net/npm/@pipecat-ai/client-js@1.13.1/+esm",
    transport: "https://cdn.jsdelivr.net/npm/@voqalize/client-transport@0.3.0/+esm",
    avatar: "https://cdn.jsdelivr.net/npm/@voqalize/avatar@0.5.6/+esm",
  };
  // Where @voqalize/client-transport keeps a live call for the next page.
  const SAVED_CALL = "voqalize-client-transport:call";
  const MUTED = "vq-aria:muted";

  function boot() {
    // ── 2. Styles, scoped to #vq-aria ────────────────────────────────────────
    const style = document.createElement("style");
    style.textContent = `
      #vq-aria { position: fixed; left: 20px; bottom: 20px; z-index: 2147483000;
        font: 15px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #1b1b1f; }
      #vq-aria * { box-sizing: border-box; }
      #vq-aria .vq-launch { display: flex; align-items: center; gap: 10px; padding: 6px 18px 6px 6px;
        border: 0; border-radius: 999px; background: #0b4f8a; color: #fff; font-family: inherit;
        font-size: 15px; font-weight: 600; line-height: 1; box-shadow: 0 6px 20px rgba(0,0,0,.18); cursor: pointer; }
      #vq-aria .vq-pic { width: 44px; height: 44px; border-radius: 50%; background: rgba(255,255,255,.18);
        display: grid; place-items: center; overflow: hidden; }
      #vq-aria .vq-pic img { width: 100%; height: 100%; object-fit: cover; }
      #vq-aria .vq-panel { width: 320px; max-width: calc(100vw - 24px); border-radius: 16px; background: #fff;
        box-shadow: 0 12px 40px rgba(0,0,0,.22); overflow: hidden; }
      #vq-aria .vq-face { height: 300px; background: #e8eef5; }
      #vq-aria .vq-status { padding: 10px 14px 0; font-size: 13px; color: #55575f; min-height: 28px; }
      #vq-aria .vq-links { padding: 0 14px; display: grid; gap: 6px; }
      #vq-aria .vq-links a { display: block; padding: 8px 10px; border-radius: 8px; background: #eef4fa;
        color: #0b4f8a; font-weight: 600; text-decoration: none; }
      #vq-aria .vq-bar { display: flex; gap: 8px; padding: 12px 14px 14px; }
      #vq-aria .vq-bar button { flex: 1; padding: 9px; border-radius: 8px; border: 1px solid #c9ccd3;
        background: #fff; color: #1b1b1f; font-family: inherit; font-size: 14px; font-weight: 600;
        line-height: 1; cursor: pointer; }
      #vq-aria .vq-bar .vq-end { background: #b3261e; border-color: #b3261e; color: #fff; }
      #vq-aria [hidden] { display: none !important; }
      /* Bottom-left, clear of the site's own chat on the right; on phones, above its strip. */
      @media (max-width: 480px) { #vq-aria { left: 12px; bottom: 96px; } #vq-aria .vq-face { height: 240px; } }
    `;
    document.head.appendChild(style);

    // ── 3. The launcher and panel ────────────────────────────────────────────
    const root = document.createElement("div");
    root.id = "vq-aria";
    root.innerHTML = `
      <button class="vq-launch" type="button" aria-label="Talk to Aria, KDEM's voice assistant">
        <span class="vq-pic"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z"/></svg></span>
        <span class="vq-label">Talk to Aria</span>
      </button>
      <div class="vq-panel" role="dialog" aria-label="Aria, KDEM assistant" hidden>
        <div class="vq-face"></div>
        <div class="vq-status" aria-live="polite"></div>
        <div class="vq-links"></div>
        <div class="vq-bar">
          <button class="vq-mute" type="button" aria-pressed="false">Mute</button>
          <button class="vq-end" type="button">End</button>
        </div>
        <audio autoplay></audio>
      </div>`;
    document.body.appendChild(root);

    const $ = (s) => root.querySelector(s);
    const launch = $(".vq-launch"), panel = $(".vq-panel"), face = $(".vq-face");
    const statusEl = $(".vq-status"), links = $(".vq-links"), audio = $("audio");
    const muteBtn = $(".vq-mute"), endBtn = $(".vq-end"), label = $(".vq-label"), pic = $(".vq-pic");

    let libs = null, media = null, transport = null, client = null, avatar = null;
    let busy = false, muted = false;
    const say = (text) => { statusEl.textContent = text; };
    const store = {
      get: (k) => { try { return sessionStorage.getItem(k); } catch { return null; } },
      set: (k, v) => { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch {} },
    };

    // The libraries, once per page. One media manager for the page's life: it
    // owns the audio element, routes the speaker and re-attaches Aria's voice
    // if the browser stops playing it.
    async function load() {
      if (libs) return libs;
      const [c, t, a] = await Promise.all([import(LIBS.client), import(LIBS.transport), import(LIBS.avatar)]);
      libs = { PipecatClient: c.PipecatClient, createVoqalizeTransport: t.createVoqalizeTransport, createAvatar: a.createAvatar };
      media = new t.VoqalizeMediaManager();
      media.bindOutputElement(audio);
      return libs;
    }

    function setMuted(next) {
      muted = next;
      store.set(MUTED, muted ? "1" : null);
      muteBtn.textContent = muted ? "Unmute" : "Mute";
      muteBtn.setAttribute("aria-pressed", String(muted));
    }

    // The page the visitor is on, for Aria. Sent on every (re)connect, so after
    // a page load she knows where the conversation has moved to.
    function reportPage() {
      try { client?.sendUIEvent("page_viewed", { path: location.pathname, title: document.title }); } catch {}
    }

    // ── 4. Start a call, or carry one over from the last page ────────────────
    async function start(rejoin) {
      if (busy || client) return;
      busy = true;
      launch.hidden = true;
      panel.hidden = false;
      label.textContent = "Talk to Aria";
      say(rejoin ? "Reconnecting…" : "Connecting…");
      links.replaceChildren();

      try {
        const { PipecatClient, createVoqalizeTransport, createAvatar } = await load();
        transport = createVoqalizeTransport({ mediaManager: media, keepAcrossPageLoads: true });
        if (rejoin && !transport.hasLiveCall) throw new Error("no call to rejoin");

        const next = new PipecatClient({
          transport,
          enableMic: true, // also what lets the browser play Aria on a page nobody has tapped yet
          enableCam: false,
          callbacks: {
            onTransportStateChanged: (state) => {
              if (client !== next) return;
              if (state === "ready") { say("Listening. Just talk."); if (muted) next.enableMic(false); }
              if (state === "disconnected") stop(false);
            },
            onBotReady: () => { if (client === next) reportPage(); },
            onBotStartedSpeaking: () => say("Aria is speaking…"),
            onBotStoppedSpeaking: () => say(muted ? "Muted." : "Listening. Just talk."),
            // Aria can offer a KDEM page as a link card; it opens in a new tab
            // so the conversation keeps going here.
            onUICommand: ({ command, payload }) => {
              if (command !== "show_link" || !payload?.url) return;
              const url = new URL(payload.url, location.origin);
              if (!/(^|\.)karnatakadigital\.in$/.test(url.hostname)) return;
              const a = document.createElement("a");
              a.href = url.href; a.target = "_blank"; a.rel = "noopener";
              a.textContent = payload.title || url.pathname;
              links.prepend(a);
              while (links.children.length > 3) links.lastChild.remove();
            },
          },
        });
        client = next;

        // Mount the face before connecting, so it is ready for Aria's first word.
        avatar = createAvatar({ mount: face, client: next, character: VQ.character });

        if (rejoin) {
          // The same call, from the params the last page saved: no new session.
          await next.connect();
        } else {
          const started = await next.startBot({
            endpoint: VQ.api,
            headers: new Headers({ Authorization: `Bearer ${VQ.publishableKey}` }),
            requestData: {
              agent_id: VQ.agentId,
              init: { surface: "kdem-web", page: location.pathname, lang: document.documentElement.lang || "en" },
            },
          });
          await next.connect(withRealHeaders(started));
        }
      } catch (error) {
        if (!rejoin) console.warn("[Voqalize] could not start Aria:", error);
        await stop(false);
        if (!rejoin) label.textContent = "Aria is unavailable. Try again";
      } finally {
        busy = false;
      }
    }

    // The session's connection details arrive as JSON; pipecat needs real Headers.
    function withRealHeaders(p) {
      return {
        ...p,
        webrtc_request_params: {
          ...p.webrtc_request_params,
          headers: new Headers(p.webrtc_request_params?.headers ?? {}),
        },
      };
    }

    // ── 5. End, mute and clean up ────────────────────────────────────────────
    // End (endCall=true) tells Voqalize the call is over at once, so the next
    // page does not dial back. A dropped call just tidies up.
    async function stop(endCall) {
      const live = client;
      client = null;
      if (endCall && live) { try { await live.disconnectBot(); } catch {} }
      avatar?.destroy(); avatar = null;
      setMuted(false);
      panel.hidden = true;
      launch.hidden = false;
      await live?.disconnect().catch(() => {});
    }

    launch.addEventListener("click", () => start(false));
    endBtn.addEventListener("click", () => stop(true));
    muteBtn.addEventListener("click", () => {
      if (!client) return;
      setMuted(!muted);
      client.enableMic(!muted);
      say(muted ? "Muted." : "Listening. Just talk.");
    });
    // No hang-up when the page goes away: that is what lets the call carry on
    // to the next page. A page restored from the back/forward cache has lost its
    // connection, so it reloads and rejoins properly.
    addEventListener("pageshow", (e) => { if (e.persisted && store.get(SAVED_CALL)) location.reload(); });

    // Aria's picture on the button, fetched once the page has settled.
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 1500));
    idle(() => {
      import(LIBS.avatar)
        .then((a) => a.listCharacters())
        .then((all) => {
          const still = all.find((c) => c.name === VQ.character)?.still;
          if (!still) return;
          const img = new Image();
          img.alt = "";
          img.onload = () => pic.replaceChildren(img);
          img.src = still;
        })
        .catch(() => {});
    });

    // A call that was live on the last page carries on here.
    muted = store.get(MUTED) === "1";
    if (store.get(SAVED_CALL)) start(true);
  }

  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
