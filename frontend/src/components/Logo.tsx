export function LogoMark({ large }: { large?: boolean }) {
  return (
    <svg className={large ? "fb-logo-mark-lg" : "fb-logo-mark"} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M16 3 L27 7.5 V15.5 C27 22.5 22.5 27.5 16 29.5 C9.5 27.5 5 22.5 5 15.5 V7.5 Z" stroke="var(--accent)" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
      <line x1="16" y1="12" x2="16" y2="17" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="16" cy="20.5" r="1.8" fill="var(--accent)" />
    </svg>
  );
}

export function Wordmark({
  onClick,
  large,
  style,
}: {
  onClick?: () => void;
  large?: boolean;
  style?: React.CSSProperties;
}) {
  if (!onClick) {
    return (
      <div className="fb-wordmark" style={{ pointerEvents: "none", ...style }}>
        <LogoMark large={large} />
        FINBRAIN OS
      </div>
    );
  }
  return (
    <button className="fb-wordmark" style={style} onClick={onClick}>
      <LogoMark large={large} />
      FINBRAIN OS
    </button>
  );
}
