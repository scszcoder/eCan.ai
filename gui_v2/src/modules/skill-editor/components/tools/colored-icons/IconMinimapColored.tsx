/**
 * Colored Minimap Icon
 */
export const IconMinimapColored = ({ size = 16, visible = true }: { size?: number; visible?: boolean }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="2" y="2" width="20" height="20" rx="2" fill="url(#minimap-gradient)" opacity={visible ? 1 : 0.5} />
    <rect x="5" y="5" width="6" height="6" rx="1" fill="#FFFFFF" opacity="0.8" />
    <rect x="13" y="5" width="6" height="6" rx="1" fill="#FFFFFF" opacity="0.6" />
    <rect x="5" y="13" width="6" height="6" rx="1" fill="#FFFFFF" opacity="0.6" />
    <rect x="13" y="13" width="6" height="6" rx="1" fill="#FFFFFF" opacity="0.4" />
    <defs>
      <linearGradient id="minimap-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#9C27B0" />
        <stop offset="100%" stopColor="#673AB7" />
      </linearGradient>
    </defs>
  </svg>
);
