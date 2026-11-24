/** The Chhatri mark: a scalloped umbrella canopy over a hooked stem. */
export function Mark({ size = 34, className }: { size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="chh-canopy" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f4b23f" />
          <stop offset="1" stopColor="#e5791b" />
        </linearGradient>
      </defs>
      <path d="M20 4.5c-8.6 0-15.6 6.6-16 15.2 1.6-1.5 3.4-2.2 5.3-2.2s3.8.7 5.3 2.2c1.5-1.5 3.4-2.2 5.4-2.2s3.9.7 5.4 2.2c1.5-1.5 3.4-2.2 5.3-2.2s3.7.7 5.3 2.2C35.6 11.1 28.6 4.5 20 4.5Z" fill="url(#chh-canopy)" />
      <path d="M20 4.6c-3.2 3.4-5 8.4-5.3 15.1M20 4.6c3.2 3.4 5 8.4 5.3 15.1" fill="none" stroke="#fff" strokeOpacity=".55" strokeWidth="1.1" />
      <path d="M20 17.6V31a3.2 3.2 0 0 1-6.4 0" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="20" cy="3.6" r="1.5" fill="currentColor" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="logo">
      <Mark className="logo-mark" />
      <span className="logo-words">
        <span className="logo-name">
          Chhatri <span className="logo-dev" lang="hi">छतरी</span>
        </span>
        <span className="logo-sub">Insurance</span>
      </span>
    </span>
  );
}
