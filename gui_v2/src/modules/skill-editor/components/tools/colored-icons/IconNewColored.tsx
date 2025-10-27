/**
 * Colored New File Icon
 */
export const IconNewColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6z"
      fill="url(#new-file-gradient)"
    />
    <path
      d="M13 3.5L18.5 9H14c-.55 0-1-.45-1-1V3.5z"
      fill="#FFFFFF"
      opacity="0.5"
    />
    <path
      d="M12 14h-2v2h2v2h2v-2h2v-2h-2v-2h-2v2z"
      fill="#FFFFFF"
    />
    <defs>
      <linearGradient id="new-file-gradient" x1="4" y1="2" x2="20" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#50C878" />
        <stop offset="100%" stopColor="#3AA65D" />
      </linearGradient>
    </defs>
  </svg>
);
