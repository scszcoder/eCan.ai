/**
 * Colored Info Icon
 */
export const IconInfoColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10" fill="url(#info-gradient)" />
    <path d="M11 7h2v2h-2V7zm0 4h2v6h-2v-6z" fill="#FFFFFF" />
    <defs>
      <linearGradient id="info-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#42A5F5" />
        <stop offset="100%" stopColor="#1E88E5" />
      </linearGradient>
    </defs>
  </svg>
);
