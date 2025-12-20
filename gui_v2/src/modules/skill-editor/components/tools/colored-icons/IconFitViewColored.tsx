/**
 * Colored Fit View/Expand Icon
 */
export const IconFitViewColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M4 4h5v2H6v3H4V4zm0 11h2v3h3v2H4v-5zm11 5v-2h3v-3h2v5h-5zM18 4v5h-2V6h-3V4h5z"
      fill="url(#fitview-gradient)"
    />
    <rect x="9" y="9" width="6" height="6" rx="1" fill="url(#fitview-gradient-inner)" />
    <defs>
      <linearGradient id="fitview-gradient" x1="4" y1="4" x2="20" y2="20" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#667EEA" />
        <stop offset="100%" stopColor="#764BA2" />
      </linearGradient>
      <linearGradient id="fitview-gradient-inner" x1="9" y1="9" x2="15" y2="15" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#667EEA" />
        <stop offset="100%" stopColor="#764BA2" />
      </linearGradient>
    </defs>
  </svg>
);
