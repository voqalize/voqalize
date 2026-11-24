/**
 * Global Bank's mark: a globe drawn in white line on a teal tile (one meridian,
 * the equator and a tilted orbit), with a marigold point riding the orbit.
 * Fictional; drawn for this demo.
 */
export function LogoMark({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 40 40" aria-hidden focusable="false">
      <rect width="40" height="40" rx="11" fill="#0e4d45" />
      <circle cx="20" cy="20" r="10.6" fill="rgba(255,255,255,0.12)" stroke="#fff" strokeWidth="1.8" />
      <ellipse cx="20" cy="20" rx="4.6" ry="10.6" fill="none" stroke="#fff" strokeWidth="1.5" />
      <path d="M9.4 20h21.2" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" />
      <ellipse cx="20" cy="20" rx="15.2" ry="5.2" fill="none" stroke="#e8a33d" strokeWidth="1.6" transform="rotate(-28 20 20)" />
      <circle cx="32.6" cy="12.4" r="2.5" fill="#e8a33d" />
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="logo">
      <LogoMark />
      {compact ? null : (
        <span className="logo-word">
          Global<span className="logo-bank">Bank</span>
        </span>
      )}
    </span>
  );
}
