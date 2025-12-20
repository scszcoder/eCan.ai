/**
 * Colored Stop Icon
 */
export const IconStopColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10" fill="url(#stop-gradient)" />
    <rect x="7.5" y="7.5" width="9" height="9" rx="1" fill="#FFFFFF" />
    <defs>
      <linearGradient id="stop-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#EF5350" />
        <stop offset="100%" stopColor="#E53935" />
      </linearGradient>
    </defs>
  </svg>
);
