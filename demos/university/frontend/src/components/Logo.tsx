/** Anvaya's mark: a banyan leaf inside two interlaced arcs, the disciplines it joins. */
export function Mark({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden className="mark">
      <circle cx="20" cy="20" r="19.5" fill="var(--ink)" />
      <path d="M6.5 25.5a14 14 0 0 1 27 0" fill="none" stroke="var(--paper)" strokeOpacity=".35" strokeWidth="1.3" />
      <path d="M9.5 29a11 11 0 0 1 21 0" fill="none" stroke="var(--paper)" strokeOpacity=".2" strokeWidth="1.3" />
      <path d="M20 6.5c7.6 5 8.6 15.2 0 24.5-8.6-9.3-7.6-19.5 0-24.5Z" fill="var(--marigold)" />
      <path d="M20 11v24.5" stroke="var(--ink)" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M20 16.5l3.6-3M20 21l-3.8-3.2M20 25.3l3.6-3" stroke="var(--ink)" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="wordmark">
      <Mark />
      <span className="wordmark-text">
        <span className="wordmark-name">Anvaya</span>
        <span className="wordmark-sub">University</span>
      </span>
    </span>
  );
}

/** The jaali: a carved-stone lattice of interlocking circles, as a backdrop. */
export function Jaali({ id, className, stroke = "var(--marigold)", opacity = 0.22, size = 44 }: { id: string; className?: string; stroke?: string; opacity?: number; size?: number }) {
  const r = size / 2;
  return (
    <svg className={className} aria-hidden width="100%" height="100%">
      <defs>
        <pattern id={id} width={size} height={size} patternUnits="userSpaceOnUse">
          <g fill="none" stroke={stroke} strokeOpacity={opacity} strokeWidth="1">
            <circle cx="0" cy="0" r={r} />
            <circle cx={size} cy="0" r={r} />
            <circle cx="0" cy={size} r={r} />
            <circle cx={size} cy={size} r={r} />
            <circle cx={r} cy={r} r={r} />
          </g>
          <circle cx={r} cy={r} r="1.6" fill={stroke} fillOpacity={opacity * 1.6} />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
}
