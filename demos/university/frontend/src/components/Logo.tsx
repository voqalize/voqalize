/** Varenya's mark: a lamp flame rising from an open book, under the arc of a gateway. */
export function Mark({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden className="mark">
      <circle cx="20" cy="20" r="19.5" fill="var(--ink)" />
      <path d="M8.5 31V17.5a11.5 11.5 0 0 1 23 0V31" fill="none" stroke="var(--paper)" strokeOpacity=".3" strokeWidth="1.3" />
      <path d="M9.5 27.5c4-1.6 7.6-1.2 10.5 1.4 2.9-2.6 6.5-3 10.5-1.4" fill="none" stroke="var(--paper)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9.5 31c4-1.6 7.6-1.2 10.5 1.4 2.9-2.6 6.5-3 10.5-1.4" fill="none" stroke="var(--paper)" strokeOpacity=".45" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 8.5c3.9 4.2 5 8.4 3.3 11.9A3.7 3.7 0 0 1 20 22.6a3.7 3.7 0 0 1-3.3-2.2C15 16.9 16.1 12.7 20 8.5Z" fill="var(--marigold)" />
      <path d="M20 15c1.4 1.8 1.7 3.6.9 5a1 1 0 0 1-1.8 0c-.8-1.4-.5-3.2.9-5Z" fill="var(--ink)" fillOpacity=".55" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="wordmark">
      <Mark />
      <span className="wordmark-text">
        <span className="wordmark-name">Varenya</span>
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
