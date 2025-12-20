/**
 * Colored Auto Layout Icon
 */
export const IconAutoLayoutColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="3" y="3" width="8" height="8" rx="1" fill="url(#auto-layout-gradient-1)" />
    <rect x="13" y="3" width="8" height="8" rx="1" fill="url(#auto-layout-gradient-2)" />
    <rect x="3" y="13" width="8" height="8" rx="1" fill="url(#auto-layout-gradient-3)" />
    <rect x="13" y="13" width="8" height="8" rx="1" fill="url(#auto-layout-gradient-4)" />
    <defs>
      <linearGradient id="auto-layout-gradient-1" x1="3" y1="3" x2="11" y2="11" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#667EEA" />
        <stop offset="100%" stopColor="#764BA2" />
      </linearGradient>
      <linearGradient id="auto-layout-gradient-2" x1="13" y1="3" x2="21" y2="11" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#F093FB" />
        <stop offset="100%" stopColor="#F5576C" />
      </linearGradient>
      <linearGradient id="auto-layout-gradient-3" x1="3" y1="13" x2="11" y2="21" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#4FACFE" />
        <stop offset="100%" stopColor="#00F2FE" />
      </linearGradient>
      <linearGradient id="auto-layout-gradient-4" x1="13" y1="13" x2="21" y2="21" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#43E97B" />
        <stop offset="100%" stopColor="#38F9D7" />
      </linearGradient>
    </defs>
  </svg>
);
