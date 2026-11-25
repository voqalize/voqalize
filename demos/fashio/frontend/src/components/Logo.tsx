/** Fashio's mark (a rani-pink tile with an "f" and a saffron bindi) and wordmark. */
export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden focusable="false">
      <rect width="32" height="32" rx="9" fill="#d6246e" />
      <path d="M13.2 26V12.6a5 5 0 0 1 5-5h2.6" fill="none" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" />
      <path d="M9.4 15.4h9" fill="none" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" />
      <circle cx="23.2" cy="23.4" r="2.8" fill="#f2a400" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="logo">
      <LogoMark />
      <span className="logo-word">
        fash<span className="logo-i">i</span>o
      </span>
    </span>
  );
}
