/**
 * Aura Bank L1-support demo UI.
 *
 * An Aura-branded clone (indigo chrome, the Aura Mobile product voice) whose Help &
 * Support centre is driven by the voice assistant: it opens the right article and
 * plays Aura's official how-to video MUTED, jumped to the exact second, while the
 * on-screen step list highlights in sync (by playback position) and the assistant
 * narrates in English.
 *
 * All navigation is React state via `useAura()` so the live call survives screen
 * changes. Branding is self-contained inline styles (the console ships its own
 * blue theme; the Aura indigo lives only under `.aura-root`).
 */

import { useEffect, useRef, type ReactNode } from 'react';
import { useAura } from './store';
import { CATEGORIES, articlesIn, getArticle, getVideo, heroArticles } from './kb';
import type { Article, CategoryId } from './types';
import {
  AccountPicker,
  ApplyPage,
  AuthDialog,
  BalancePage,
  CalculatorPage,
  CardControlsPage,
  CardPicker,
  ChecklistPage,
  ComparePage,
  ForexCardPage,
  LocatorPage,
  SendToPhoneToast,
  SessionBadge,
  Spotlight,
  StatementPage,
  TicketCard,
} from './tools';

// ── Aura brand palette ────────────────────────────────────────────────────────
const PRIMARY = '#4F46E5';
const PRIMARY_DARK = '#3730A3';
const ACCENT = '#8B5CF6';
const INK = '#1A1620';
const MUTED = '#6E6470';
const BORDER = '#E6E2F2';
const PAPER = '#FFFFFF';
const NAV = ['Accounts', 'Deposits', 'Cards', 'Forex', 'Loans', 'Investments', 'Insurance', 'Payments'];

// ── The angular Aura "A" mark (approximation) ───────────────────────────────────
function AuraMark({ size = 34 }: { size?: number }) {
  return (
    <span
      aria-hidden
      style={{
        display: 'inline-flex',
        width: size,
        height: size,
        background: PRIMARY,
        borderRadius: 4,
        alignItems: 'center',
        justifyContent: 'center',
        flex: 'none',
      }}
    >
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 24 24" fill="none">
        <path d="M12 3 L21 21 L15.5 21 L12 12.5 L8.5 21 L3 21 Z" fill="#fff" />
        <path d="M12 3 L15 9 L9 9 Z" fill={PRIMARY} />
      </svg>
    </span>
  );
}

function Logo() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9 }}>
      <AuraMark />
      <span className="aura-wordmark" style={{ color: '#fff', fontWeight: 800, letterSpacing: 1, fontSize: 18 }}>
        AURA BANK
      </span>
    </span>
  );
}

// ── Header ──────────────────────────────────────────────────────────────────
// The voice control lands in the product's own navigation row (`presence`, handed
// down by AuraAssistant) — bank chrome, not a floating widget. The header is
// sticky, so the affordance stays reachable anywhere on the page, phone included.
function Header({ presence }: { presence?: ReactNode }) {
  const { openHome, openHelpCenter } = useAura();
  return (
    <header style={{ position: 'sticky', top: 0, zIndex: 40 }}>
      <div
        className="aura-topbar"
        style={{
          background: PRIMARY,
          color: '#fff',
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 24,
        }}
      >
        <button onClick={openHome} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
          <Logo />
        </button>
        <div className="aura-personas" style={{ display: 'flex', gap: 22, fontSize: 13.5, fontWeight: 600, opacity: 0.95 }}>
          {['Personal', 'Business', 'NRI', 'Priority', 'Corporate'].map((t) => (
            <span key={t} style={{ opacity: t === 'Personal' ? 1 : 0.8 }}>
              {t}
            </span>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 18, fontSize: 13.5 }}>
          <button
            onClick={openHelpCenter}
            className="aura-hdr-link"
            style={{ background: 'none', border: 'none', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 13.5 }}
          >
            Support
          </button>
          <span className="aura-hdr-link" style={{ opacity: 0.85 }}>
            Lodge a Complaint
          </span>
          <span
            className="aura-login"
            style={{
              border: '1px solid rgba(255,255,255,.6)',
              borderRadius: 8,
              padding: '6px 14px',
              fontWeight: 700,
            }}
          >
            Login
          </span>
        </div>
      </div>
      <nav
        className="aura-navrow"
        style={{
          background: PAPER,
          borderBottom: `1px solid ${BORDER}`,
          padding: '11px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 18,
          fontSize: 14,
          fontWeight: 700,
          color: INK,
        }}
      >
        {/* The product nav scrolls on its own, so the help link and the voice
            control can never be pushed off a narrow screen. */}
        <div className="aura-navscroll" style={{ display: 'flex', gap: 26, flex: 1, minWidth: 0, overflowX: 'auto' }}>
          {NAV.map((t) => (
            <span key={t} style={{ whiteSpace: 'nowrap', cursor: 'default' }}>
              {t}
            </span>
          ))}
        </div>
        <button
          onClick={openHelpCenter}
          className="aura-nav-help"
          style={{
            background: 'none',
            border: 'none',
            color: PRIMARY,
            fontWeight: 800,
            cursor: 'pointer',
            fontSize: 14,
            whiteSpace: 'nowrap',
            flex: 'none',
            padding: 0,
          }}
        >
          Help & Support
        </button>
        {presence}
      </nav>
    </header>
  );
}

// ── tiny markdown renderer (## / lists / > / ** / `code`) ───────────────────────
function inline(text: string, key: number): ReactNode {
  // Split on **bold** and `code`, keep delimiters.
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**'))
          return (
            <strong key={`${key}-${i}`} style={{ color: INK }}>
              {p.slice(2, -2)}
            </strong>
          );
        if (p.startsWith('`') && p.endsWith('`'))
          return (
            <code
              key={`${key}-${i}`}
              style={{ background: '#EFEFFA', padding: '1px 5px', borderRadius: 4, fontSize: 12.5 }}
            >
              {p.slice(1, -1)}
            </code>
          );
        return <span key={`${key}-${i}`}>{p}</span>;
      })}
    </>
  );
}

function Markdown({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);
  return (
    <div style={{ color: '#3A3340', fontSize: 14.5, lineHeight: 1.7 }}>
      {blocks.map((block, i) => {
        const lines = block.split('\n');
        if (lines[0].startsWith('## '))
          return (
            <h3 key={i} style={{ color: PRIMARY, fontSize: 16, fontWeight: 800, margin: '18px 0 8px' }}>
              {inline(lines[0].slice(3), i)}
            </h3>
          );
        if (lines.every((l) => /^\d+\.\s/.test(l)))
          return (
            <ol key={i} style={{ margin: '6px 0', paddingLeft: 22 }}>
              {lines.map((l, j) => (
                <li key={j} style={{ marginBottom: 5 }}>
                  {inline(l.replace(/^\d+\.\s/, ''), j)}
                </li>
              ))}
            </ol>
          );
        if (lines.every((l) => l.startsWith('- ')))
          return (
            <ul key={i} style={{ margin: '6px 0', paddingLeft: 22 }}>
              {lines.map((l, j) => (
                <li key={j} style={{ marginBottom: 5 }}>
                  {inline(l.slice(2), j)}
                </li>
              ))}
            </ul>
          );
        if (lines[0].startsWith('> '))
          return (
            <blockquote
              key={i}
              style={{
                borderLeft: `3px solid ${ACCENT}`,
                background: '#EEF0FE',
                margin: '12px 0',
                padding: '10px 14px',
                borderRadius: '0 8px 8px 0',
                color: '#5A4150',
                fontSize: 13.5,
              }}
            >
              {inline(lines.map((l) => l.replace(/^>\s?/, '')).join(' '), i)}
            </blockquote>
          );
        return (
          <p key={i} style={{ margin: '8px 0' }}>
            {inline(block, i)}
          </p>
        );
      })}
    </div>
  );
}

// ── Home ──────────────────────────────────────────────────────────────────────
function HomePage() {
  const { openHelpCenter, openArticle } = useAura();
  return (
    <div>
      <section
        className="aura-hero"
        style={{
          background: 'linear-gradient(135deg,#ECEBFB 0%, #F2F1FC 55%, #FFFFFF 100%)',
          padding: '56px 24px 64px',
        }}
      >
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <h1 className="aura-hero-h1" style={{ fontSize: 44, lineHeight: 1.1, margin: 0, color: INK, fontWeight: 800 }}>
            <span style={{ color: PRIMARY, fontStyle: 'italic' }}>Banking,</span> answered.
            <br />
            <span style={{ color: PRIMARY, fontStyle: 'italic' }}>Instant help,</span> anytime.
          </h1>
          <p className="aura-hero-p" style={{ fontSize: 18, color: MUTED, marginTop: 14 }}>
            Voice support that doesn’t just tell you — it shows you.
          </p>
          <button
            onClick={openHelpCenter}
            style={{
              marginTop: 24,
              background: PRIMARY,
              color: '#fff',
              border: 'none',
              borderRadius: 10,
              padding: '13px 26px',
              fontWeight: 800,
              fontSize: 15,
              cursor: 'pointer',
            }}
          >
            Visit Help &amp; Support
          </button>
        </div>
      </section>

      <section className="aura-page" style={{ maxWidth: 1100, margin: '0 auto', padding: '40px 24px' }}>
        <h2 style={{ fontSize: 22, color: INK, fontWeight: 800, marginBottom: 4 }}>Popular help topics</h2>
        <p style={{ color: MUTED, marginTop: 0, marginBottom: 20, fontSize: 14 }}>
          Ask a question by voice — the assistant pulls up the right video and walks you through it.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 16 }}>
          {heroArticles().map((a) => (
            <button
              key={a.id}
              onClick={() => openArticle(a.id)}
              style={{
                textAlign: 'left',
                background: PAPER,
                border: `1px solid ${BORDER}`,
                borderRadius: 14,
                padding: 18,
                cursor: 'pointer',
                boxShadow: '0 2px 10px rgba(79,70,229,.05)',
              }}
            >
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                {a.video && (
                  <span
                    className="aura-tiny"
                    style={{
                      fontSize: 10.5,
                      fontWeight: 800,
                      color: ACCENT,
                      background: '#EEF0FE',
                      borderRadius: 20,
                      padding: '2px 9px',
                    }}
                  >
                    ▶ VIDEO
                  </span>
                )}
              </div>
              <div style={{ fontSize: 15.5, fontWeight: 700, color: INK, lineHeight: 1.35 }}>{a.title_en}</div>
              <div style={{ fontSize: 13, color: MUTED, marginTop: 8, lineHeight: 1.5 }}>
                {CATEGORIES.find((c) => c.id === a.category)?.title}
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

// ── Help Center ─────────────────────────────────────────────────────────────
const QUICK_TOOLS: { label: string; sub: string; run: (s: ReturnType<typeof useAura>) => void }[] = [
  { label: 'EMI Calculator', sub: 'Loan EMI', run: (s) => s.runCalculator('emi', { principal: 500000, annual_rate: 10.5, tenure_months: 60 }) },
  { label: 'FD Calculator', sub: 'Maturity value', run: (s) => s.runCalculator('fd', { principal: 100000, annual_rate: 7.1, tenure_months: 60 }) },
  { label: 'Loan Eligibility', sub: 'How much can I borrow', run: (s) => s.runCalculator('eligibility', { monthly_income: 90000, existing_emi: 0, annual_rate: 10.5, tenure_months: 60 }) },
  { label: 'Open an Account', sub: 'Start online', run: (s) => s.startApplication('savings') },
];

function HelpCenterPage() {
  const store = useAura();
  const { openCategory, openArticle } = store;
  return (
    <div className="aura-page" style={{ maxWidth: 1100, margin: '0 auto', padding: '36px 24px' }}>
      <h1 className="aura-h1" style={{ fontSize: 30, color: INK, fontWeight: 800, margin: '0 0 6px' }}>
        Help &amp; Support
      </h1>
      <p style={{ color: MUTED, marginTop: 0, fontSize: 15 }}>
        Choose a topic, or just ask our voice assistant — it’ll pull up the right how-to video.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 16, marginTop: 22 }}>
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            onClick={() => openCategory(c.id)}
            style={{
              textAlign: 'left',
              background: PAPER,
              border: `1px solid ${BORDER}`,
              borderRadius: 14,
              padding: 20,
              cursor: 'pointer',
            }}
          >
            <div style={{ fontSize: 17, fontWeight: 800, color: PRIMARY }}>{c.title}</div>
            <div style={{ fontSize: 13.5, color: MUTED, marginTop: 8, lineHeight: 1.5 }}>{c.blurb}</div>
            <div style={{ fontSize: 12, color: MUTED, marginTop: 10 }}>
              {articlesIn(c.id).length} article{articlesIn(c.id).length === 1 ? '' : 's'}
            </div>
          </button>
        ))}
      </div>

      <h2 style={{ fontSize: 18, color: INK, fontWeight: 800, margin: '30px 0 10px' }}>Quick tools</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(200px,1fr))', gap: 12 }}>
        {QUICK_TOOLS.map((t) => (
          <button
            key={t.label}
            onClick={() => t.run(store)}
            style={{ textAlign: 'left', background: '#EEF0FE', border: `1px solid ${BORDER}`, borderRadius: 12, padding: '13px 15px', cursor: 'pointer' }}
          >
            <div style={{ fontSize: 14.5, fontWeight: 800, color: PRIMARY }}>{t.label}</div>
            <div style={{ fontSize: 12.5, color: MUTED, marginTop: 2 }}>{t.sub}</div>
          </button>
        ))}
      </div>

      <h2 style={{ fontSize: 18, color: INK, fontWeight: 800, margin: '30px 0 10px' }}>Most asked</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {heroArticles().map((a) => (
          <button
            key={a.id}
            onClick={() => openArticle(a.id)}
            style={{
              textAlign: 'left',
              background: PAPER,
              border: `1px solid ${BORDER}`,
              borderRadius: 10,
              padding: '12px 16px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            {a.video && <span style={{ color: ACCENT, fontSize: 12 }}>▶</span>}
            <span style={{ fontSize: 14.5, fontWeight: 600, color: INK }}>{a.title_en}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Category ──────────────────────────────────────────────────────────────────
function CategoryPage({ category }: { category: CategoryId }) {
  const { openArticle, openHelpCenter } = useAura();
  const cat = CATEGORIES.find((c) => c.id === category);
  return (
    <div className="aura-page" style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px' }}>
      <Breadcrumb items={[{ label: 'Help & Support', onClick: openHelpCenter }, { label: cat?.title ?? category }]} />
      <h1 style={{ fontSize: 26, color: INK, fontWeight: 800, margin: '6px 0 16px' }}>{cat?.title}</h1>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {articlesIn(category).map((a) => (
          <button
            key={a.id}
            onClick={() => openArticle(a.id)}
            style={{
              textAlign: 'left',
              background: PAPER,
              border: `1px solid ${BORDER}`,
              borderRadius: 12,
              padding: 16,
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: INK }}>{a.title_en}</span>
              {a.video && (
                <span className="aura-tiny" style={{ fontSize: 10, fontWeight: 800, color: ACCENT, background: '#EEF0FE', borderRadius: 20, padding: '2px 8px' }}>
                  ▶ VIDEO
                </span>
              )}
              {a.needs_login && (
                <span className="aura-tiny" style={{ fontSize: 10, fontWeight: 700, color: MUTED, border: `1px solid ${BORDER}`, borderRadius: 20, padding: '2px 8px' }}>
                  login needed
                </span>
              )}
            </div>
            <div style={{ fontSize: 13, color: MUTED, marginTop: 5 }}>{a.tags.slice(0, 3).join(' · ')}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function Breadcrumb({ items }: { items: { label: string; onClick?: () => void }[] }) {
  return (
    <div style={{ fontSize: 13, color: MUTED, marginBottom: 6 }}>
      {items.map((it, i) => (
        <span key={i}>
          {it.onClick ? (
            <button onClick={it.onClick} style={{ background: 'none', border: 'none', color: PRIMARY, cursor: 'pointer', fontSize: 13, padding: 0 }}>
              {it.label}
            </button>
          ) : (
            <span>{it.label}</span>
          )}
          {i < items.length - 1 && <span style={{ margin: '0 7px' }}>/</span>}
        </span>
      ))}
    </div>
  );
}

// ── YouTube player (muted, agent-driven) ────────────────────────────────────
let ytReady: Promise<void> | null = null;
function loadYT(): Promise<void> {
  if (ytReady) return ytReady;
  ytReady = new Promise<void>((resolve) => {
    const w = window as unknown as { YT?: { Player?: unknown }; onYouTubeIframeAPIReady?: () => void };
    if (w.YT && w.YT.Player) {
      resolve();
      return;
    }
    const prev = w.onYouTubeIframeAPIReady;
    w.onYouTubeIframeAPIReady = () => {
      prev?.();
      resolve();
    };
    const tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(tag);
  });
  return ytReady;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
// The hero player — large, in the main content column. Muted, agent-driven, with
// a lower-third caption overlay that names the step the muted video is showing.
function VideoStage() {
  const { videoId, videoCmd, currentStep, playing, setPlaybackTime, pauseVideo, resumeVideo } = useAura();
  const video = getVideo(videoId ?? undefined);
  const playerRef = useRef<any>(null);
  const readyRef = useRef(false);
  const lastNonce = useRef(0);
  const pendingRef = useRef<typeof videoCmd>(null);

  const applyCmd = (cmd: NonNullable<typeof videoCmd>) => {
    const p = playerRef.current;
    if (!p) return;
    try {
      p.mute();
      if (cmd.action === 'play' && cmd.videoId) p.loadVideoById({ videoId: cmd.videoId, startSeconds: cmd.startSec ?? 0 });
      else if (cmd.action === 'seek') {
        p.seekTo(cmd.startSec ?? 0, true);
        p.playVideo();
      } else if (cmd.action === 'pause') p.pauseVideo();
      else if (cmd.action === 'resume') p.playVideo();
      p.mute();
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    let cancelled = false;
    loadYT().then(() => {
      if (cancelled) return;
      const YT = (window as any).YT;
      playerRef.current = new YT.Player('aura-yt-player', {
        playerVars: { mute: 1, rel: 0, modestbranding: 1, playsinline: 1, controls: 1 },
        events: {
          onReady: () => {
            readyRef.current = true;
            const p = playerRef.current;
            p.mute();
            if (pendingRef.current) {
              applyCmd(pendingRef.current);
              pendingRef.current = null;
            } else if (video) {
              p.cueVideoById({ videoId: video.youtube_id, startSeconds: video.default_start });
            }
          },
        },
      });
    });
    return () => {
      cancelled = true;
      try {
        playerRef.current?.destroy();
      } catch {
        /* ignore */
      }
      playerRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!readyRef.current || !video) return;
    try {
      playerRef.current.cueVideoById({ videoId: video.youtube_id, startSeconds: video.default_start });
      playerRef.current.mute();
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  useEffect(() => {
    if (!videoCmd || videoCmd.nonce === lastNonce.current) return;
    lastNonce.current = videoCmd.nonce;
    if (!readyRef.current) {
      pendingRef.current = videoCmd;
      return;
    }
    applyCmd(videoCmd);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoCmd]);

  useEffect(() => {
    const t = window.setInterval(() => {
      const p = playerRef.current;
      if (p && readyRef.current && typeof p.getCurrentTime === 'function') {
        try {
          setPlaybackTime(p.getCurrentTime());
        } catch {
          /* ignore */
        }
      }
    }, 500);
    return () => window.clearInterval(t);
  }, [setPlaybackTime]);

  const ch = video?.chapters[currentStep];

  return (
    <div>
      <div
        style={{
          position: 'relative',
          background: '#000',
          borderRadius: 16,
          overflow: 'hidden',
          aspectRatio: '16 / 9',
          boxShadow: '0 14px 40px rgba(26,22,32,.22)',
        }}
      >
        <div id="aura-yt-player" style={{ width: '100%', height: '100%' }} />
        {/* Lower-third caption — names the step the muted video is showing now. */}
        {ch && (
          <div
            key={currentStep}
            className="aura-cap-enter"
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: 0,
              padding: '34px 18px 16px',
              background: 'linear-gradient(transparent, rgba(0,0,0,.78))',
              color: '#fff',
              pointerEvents: 'none',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <span
              style={{
                flex: 'none',
                width: 30,
                height: 30,
                borderRadius: '50%',
                background: ACCENT,
                color: '#fff',
                fontSize: 14,
                fontWeight: 800,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 0 4px rgba(139,92,246,.35)',
              }}
            >
              {currentStep + 1}
            </span>
            <span style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: 17, fontWeight: 800, lineHeight: 1.2, textShadow: '0 1px 6px rgba(0,0,0,.6)' }}>{ch.label}</span>
            </span>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '12px 4px 0' }}>
        <span style={{ fontSize: 12.5, fontWeight: 800, color: playing ? ACCENT : MUTED }}>
          {playing ? '● PLAYING (muted)' : '❚❚ Paused'}
        </span>
        {video?.channel && <span style={{ fontSize: 12, color: MUTED }}>· {video.channel}</span>}
        <div style={{ marginLeft: 'auto' }}>
          <SmallBtn onClick={() => (playing ? pauseVideo() : resumeVideo())}>{playing ? 'Pause' : 'Play'}</SmallBtn>
        </div>
      </div>
    </div>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// The step rail — the active step pulses and auto-scrolls into view as the agent
// narrates / the muted video plays.
function StepList() {
  const { videoId, currentStep, seekVideo } = useAura();
  const video = getVideo(videoId ?? undefined);
  const activeRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [currentStep]);

  if (!video) return null;
  return (
    <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
      {video.chapters.map((chapter, i) => {
        const active = i === currentStep;
        return (
          <li key={i} ref={active ? activeRef : undefined}>
            <button
              className={active ? 'aura-step-active' : undefined}
              onClick={() => (active ? undefined : seekVideo(chapter.start))}
              style={{
                width: '100%',
                textAlign: 'left',
                display: 'flex',
                gap: 11,
                alignItems: 'flex-start',
                background: active ? '#EEF0FE' : PAPER,
                border: `2px solid ${active ? ACCENT : BORDER}`,
                borderRadius: 12,
                padding: '11px 13px',
                cursor: 'pointer',
                transition: 'background .15s, border-color .15s',
              }}
            >
              <span
                style={{
                  flex: 'none',
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: active ? ACCENT : '#E7E5F6',
                  color: active ? '#fff' : MUTED,
                  fontSize: 12.5,
                  fontWeight: 800,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {i + 1}
              </span>
              <span style={{ flex: 1 }}>
                <span style={{ fontSize: 14, fontWeight: active ? 800 : 600, color: active ? PRIMARY : INK }}>
                  {chapter.label}
                </span>
              </span>
              <span style={{ flex: 'none', fontSize: 11, color: MUTED, fontVariantNumeric: 'tabular-nums', marginTop: 2 }}>
                {fmt(chapter.start)}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function SmallBtn({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        fontSize: 12,
        fontWeight: 700,
        color: PRIMARY,
        background: PAPER,
        border: `1px solid ${BORDER}`,
        borderRadius: 8,
        padding: '4px 12px',
        cursor: 'pointer',
      }}
    >
      {children}
    </button>
  );
}

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60);
  return `${m}:${ss.toString().padStart(2, '0')}`;
}

// ── Article ─────────────────────────────────────────────────────────────────
function RelatedAndBody({ article }: { article: Article }) {
  const { openArticle } = useAura();
  return (
    <>
      <Markdown text={article.body} />
      {article.related.length > 0 && (
        <div style={{ marginTop: 24, borderTop: `1px solid ${BORDER}`, paddingTop: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: MUTED, textTransform: 'uppercase', letterSpacing: 0.5 }}>Related</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {article.related
              .map((id) => getArticle(id))
              .filter((a): a is Article => Boolean(a))
              .map((a) => (
                <button
                  key={a.id}
                  onClick={() => openArticle(a.id)}
                  style={{ fontSize: 13, color: PRIMARY, background: '#EEF0FE', border: 'none', borderRadius: 8, padding: '6px 12px', cursor: 'pointer', fontWeight: 600 }}
                >
                  {a.title_en}
                </button>
              ))}
          </div>
        </div>
      )}
    </>
  );
}

function ArticlePage({ article }: { article: Article }) {
  const { openHelpCenter, openCategory } = useAura();
  const cat = CATEGORIES.find((c) => c.id === article.category);
  const hasVideo = Boolean(article.video && getVideo(article.video));

  return (
    <div className="aura-page" style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 24px 60px' }}>
      <Breadcrumb
        items={[
          { label: 'Help & Support', onClick: openHelpCenter },
          { label: cat?.title ?? article.category, onClick: () => openCategory(article.category) },
          { label: article.title_en ?? article.title },
        ]}
      />
      <h1 className="aura-h1" style={{ fontSize: 28, color: INK, fontWeight: 800, margin: '4px 0 18px', lineHeight: 1.2 }}>
        {article.title_en}
      </h1>

      {hasVideo ? (
        <>
          {/* Video is the hero: large in the main column, step rail alongside.
              On a phone the rail drops below the (fluid 16:9) player. */}
          <div
            className="aura-two-col"
            style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.7fr) minmax(290px,1fr)', gap: 24, alignItems: 'start' }}
          >
            <VideoStage />
            <div className="aura-sticky-rail" style={{ position: 'sticky', top: 96, display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: MUTED, textTransform: 'uppercase', letterSpacing: 0.5 }}>Steps</div>
              <StepList />
              {article.needs_login && (
                <div style={{ fontSize: 12.5, color: '#8A5A00', background: '#FFF6E0', border: '1px solid #F2E2B0', borderRadius: 10, padding: '10px 12px', lineHeight: 1.5 }}>
                  Account-specific — you’ll do the actual download on your own login. I’m just showing you the way.
                </div>
              )}
            </div>
          </div>
          <article style={{ maxWidth: 760, marginTop: 28 }}>
            <RelatedAndBody article={article} />
          </article>
        </>
      ) : (
        <article style={{ maxWidth: 760 }}>
          <RelatedAndBody article={article} />
        </article>
      )}
    </div>
  );
}

// ── Contact overlay ───────────────────────────────────────────────────────────
function ContactPanel() {
  const { contactOpen, contactTopic, closeContact } = useAura();
  if (!contactOpen) return null;
  return (
    <div
      className="aura-dock"
      style={{
        position: 'fixed',
        right: 24,
        bottom: 110,
        zIndex: 1100,
        width: 300,
        background: PAPER,
        border: `1px solid ${BORDER}`,
        borderRadius: 14,
        boxShadow: '0 16px 40px rgba(26,22,32,.22)',
        overflow: 'hidden',
      }}
    >
      <div style={{ background: PRIMARY, color: '#fff', padding: '11px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 800, fontSize: 13.5 }}>Contact Aura Bank</span>
        <button onClick={closeContact} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 14 }}>
          ✕
        </button>
      </div>
      <div style={{ padding: 14, fontSize: 13.5, color: INK }}>
        {contactTopic && <div style={{ color: MUTED, fontSize: 12.5, marginBottom: 10 }}>For: {contactTopic}</div>}
        <Row label="24×7 Retail / Cards" value="1860-200-0100" />
        <Row label="Alternate" value="1860-200-0200" />
        <Row label="Report lost card (24×7)" value="+91 22 2000 0200" />
        <div style={{ marginTop: 10, fontSize: 11.5, color: MUTED }}>
          Aura will never ask for your OTP, PIN, or password.
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: `1px solid ${BORDER}` }}>
      <span style={{ color: MUTED, fontSize: 12.5 }}>{label}</span>
      <span style={{ fontWeight: 800, color: PRIMARY }}>{value}</span>
    </div>
  );
}

// ── Root ──────────────────────────────────────────────────────────────────────
export function AuraApp({ presence }: { presence?: ReactNode }) {
  const { screen, category, articleId } = useAura();
  const article = articleId ? getArticle(articleId) : undefined;
  return (
    <div
      className="aura-root"
      style={{ position: 'absolute', inset: 0, overflowY: 'auto', overflowX: 'hidden', background: '#F8F8FD', fontFamily: 'Inter, system-ui, sans-serif', color: INK }}
    >
      <style>{`
        @keyframes auraPulse {
          0% { box-shadow: 0 0 0 0 rgba(139,92,246,.45); }
          70% { box-shadow: 0 0 0 9px rgba(139,92,246,0); }
          100% { box-shadow: 0 0 0 0 rgba(139,92,246,0); }
        }
        .aura-step-active { animation: auraPulse 1.7s ease-out infinite; }
        @keyframes auraCapIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .aura-cap-enter { animation: auraCapIn .35s ease-out; }

        /* The product nav scrolls without showing a bar (it holds the voice
           control's row, so a scrollbar would read as chrome). */
        .aura-navscroll { scrollbar-width: none; -ms-overflow-style: none; }
        .aura-navscroll::-webkit-scrollbar { display: none; }

        /* ── Phone (≤640px) ────────────────────────────────────────────────
           This demo's geometry is inline styles, so every override here is
           !important by necessity. Desktop (>640px) is untouched: the rules
           below only ever fire on a narrow viewport. The shape of the pass:
           the header sheds its desktop-only links, every two-column grid
           stacks, sticky rails go static, and fixed docks span the width. */
        @media (max-width: 640px) {
          .aura-topbar { padding: 10px 14px !important; gap: 12px !important; }
          .aura-personas, .aura-hdr-link, .aura-login { display: none !important; }
          .aura-wordmark { font-size: 15px !important; letter-spacing: .5px !important; }
          .aura-navrow { padding: 9px 14px !important; gap: 12px !important; }
          /* The eight decorative product links are the first thing a phone
             sheds — on a 390px row they only ever showed a clipped word and a
             half behind the two controls that actually do something. */
          .aura-navscroll { display: none !important; }
          .aura-nav-help { font-size: 13px !important; margin-right: auto !important; }

          /* One column everywhere: article video + step rail, calculator +
             result card, forex benefits + lead form. */
          .aura-two-col { grid-template-columns: minmax(0, 1fr) !important; gap: 16px !important; }
          .aura-sticky-rail { position: static !important; }

          .aura-page { padding: 20px 14px 44px !important; }
          .aura-hero { padding: 34px 14px 38px !important; }
          .aura-hero-h1 { font-size: 29px !important; }
          .aura-hero-p { font-size: 15px !important; }
          .aura-h1 { font-size: 22px !important; }

          /* Docked overlays span the viewport instead of a 300px card that
             would sit half off-screen. */
          .aura-dock {
            left: 12px !important;
            right: 12px !important;
            bottom: 16px !important;
            width: auto !important;
            max-width: none !important;
          }
          .aura-toast { left: 12px !important; right: 12px !important; max-width: none !important; }
          /* Sits over the top bar, whose desktop-only links are hidden here —
             so it never lands on the voice control a row below. */
          .aura-badge { right: 12px !important; font-size: 11.5px !important; padding: 5px 10px !important; }

          /* Nothing under 11px on a phone. */
          .aura-tiny { font-size: 11px !important; }
        }
      `}</style>
      <Header presence={presence} />
      {screen === 'home' && <HomePage />}
      {screen === 'help' && <HelpCenterPage />}
      {screen === 'category' && category && <CategoryPage category={category} />}
      {screen === 'article' && article && <ArticlePage article={article} />}
      {screen === 'article' && !article && <HelpCenterPage />}
      {screen === 'calculator' && <CalculatorPage />}
      {screen === 'apply' && <ApplyPage />}
      {screen === 'compare' && <ComparePage />}
      {screen === 'locator' && <LocatorPage />}
      {screen === 'checklist' && <ChecklistPage />}
      {screen === 'balance' && <BalancePage />}
      {screen === 'statement' && <StatementPage />}
      {screen === 'card_controls' && <CardControlsPage />}
      {screen === 'forex' && <ForexCardPage />}
      <ContactPanel />
      <SendToPhoneToast />
      <TicketCard />
      <SessionBadge />
      <AuthDialog />
      <AccountPicker />
      <CardPicker />
      <Spotlight />
    </div>
  );
}
