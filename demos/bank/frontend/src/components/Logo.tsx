/**
 * Anvaya Bank's mark: a three-petal lotus drawn as one knotted line on a teal
 * tile, with a marigold bindu above it. Fictional; drawn for this demo.
 */
export function LogoMark({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 40 40" aria-hidden focusable="false">
      <rect width="40" height="40" rx="11" fill="#0e4d45" />
      <path d="M20 31C12.5 30.2 7.4 24.6 7.2 17.2c6 .9 10.9 5.6 12.8 13.8Z" fill="rgba(255,255,255,0.14)" stroke="#fff" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M20 31c7.5-.8 12.6-6.4 12.8-13.8-6 .9-10.9 5.6-12.8 13.8Z" fill="rgba(255,255,255,0.14)" stroke="#fff" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M20 31c-5.2-4.6-6.6-12.4 0-20.2 6.6 7.8 5.2 15.6 0 20.2Z" fill="#0e4d45" stroke="#fff" strokeWidth="1.7" strokeLinejoin="round" />
      <circle cx="20" cy="6.4" r="2.5" fill="#e8a33d" />
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="logo">
      <LogoMark />
      {compact ? null : (
        <span className="logo-word">
          Anvaya<span className="logo-bank">Bank</span>
        </span>
      )}
    </span>
  );
}
