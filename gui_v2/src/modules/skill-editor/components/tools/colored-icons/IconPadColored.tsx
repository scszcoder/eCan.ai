/**
 * Colored Trackpad Icon - matches original proportions
 */
export const IconPadColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size * 1.26} height={size} viewBox="0 0 48 38" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect
      x="1.83317"
      y="1.49998"
      width="44.3333"
      height="35"
      rx="3.5"
      stroke="url(#pad-gradient)"
      strokeOpacity="0.8"
      strokeWidth="2.33333"
    />
    <path
      d="M14.6665 30.6667H33.3332"
      stroke="url(#pad-gradient)"
      strokeOpacity="0.8"
      strokeWidth="2.33333"
      strokeLinecap="round"
    />
    <defs>
      <linearGradient id="pad-gradient" x1="1.83317" y1="1.49998" x2="46.1665" y2="36.5" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#90A4AE" />
        <stop offset="100%" stopColor="#607D8B" />
      </linearGradient>
    </defs>
  </svg>
);
