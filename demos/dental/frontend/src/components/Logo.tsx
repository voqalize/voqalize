import { CLINIC } from "../data/clinic";

/** The Dantika mark: a molar whose crown holds a leaf. */
export function Mark({ size = 34 }: { size?: number }) {
  return (
    <svg className="mark" width={size} height={size} viewBox="0 0 40 40" aria-hidden focusable="false">
      <path
        d="M12.5 5.5C7.6 5.5 5 9.3 5 13.8c0 5 2.9 8.2 4 13.1 1 4.6 2.1 8.6 5 8.6 3.2 0 3.2-6.8 6-6.8s2.8 6.8 6 6.8c2.9 0 4-4 5-8.6 1.1-4.9 4-8.1 4-13.1 0-4.5-2.6-8.3-7.5-8.3-3 0-4.6 1.9-7.5 1.9s-4.5-1.9-7.5-1.9Z"
        fill="var(--brand)"
      />
      <path d="M20 11.2c-4.6 1.6-6 6.6-1.4 11 .4.4 1 .4 1.4 0 4.6-4.4 3.2-9.4 0-11Z" fill="var(--accent)" />
      <path d="M20 13.4v9.2" stroke="var(--brand)" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="logo">
      <Mark />
      <span className="logo-words">
        <span className="logo-name">{CLINIC.short}</span>
        <span className="logo-sub">Dental Studio</span>
      </span>
    </span>
  );
}
