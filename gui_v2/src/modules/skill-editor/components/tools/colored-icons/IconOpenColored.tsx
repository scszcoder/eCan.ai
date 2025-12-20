/**
 * Colored Open/Folder Icon
 */
export const IconOpenColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z"
      fill="url(#folder-gradient)"
    />
    <defs>
      <linearGradient id="folder-gradient" x1="2" y1="4" x2="22" y2="20" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#FFB84D" />
        <stop offset="100%" stopColor="#FF9500" />
      </linearGradient>
    </defs>
  </svg>
);
