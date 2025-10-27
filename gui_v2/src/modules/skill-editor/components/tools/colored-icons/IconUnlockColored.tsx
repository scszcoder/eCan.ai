/**
 * Colored Unlock Icon (Development mode)
 */
export const IconUnlockColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="5" y="11" width="14" height="10" rx="2" fill="url(#unlock-gradient)" />
    <path
      d="M8 11V7c0-2.21 1.79-4 4-4s4 1.79 4 4v1"
      stroke="url(#unlock-stroke-gradient)"
      strokeWidth="2"
      strokeLinecap="round"
      fill="none"
    />
    <circle cx="12" cy="16" r="1.5" fill="#FFFFFF" />
    <defs>
      <linearGradient id="unlock-gradient" x1="5" y1="11" x2="19" y2="21" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#66BB6A" />
        <stop offset="100%" stopColor="#43A047" />
      </linearGradient>
      <linearGradient id="unlock-stroke-gradient" x1="8" y1="3" x2="16" y2="8" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#66BB6A" />
        <stop offset="100%" stopColor="#43A047" />
      </linearGradient>
    </defs>
  </svg>
);
