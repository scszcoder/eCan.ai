/**
 * Colored Pause Icon
 */
export const IconPauseColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10" fill="url(#pause-gradient)" />
    <rect x="8.5" y="7" width="2.5" height="10" rx="1" fill="#FFFFFF" />
    <rect x="13" y="7" width="2.5" height="10" rx="1" fill="#FFFFFF" />
    <defs>
      <linearGradient id="pause-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#FFA726" />
        <stop offset="100%" stopColor="#FF9800" />
      </linearGradient>
    </defs>
  </svg>
);
