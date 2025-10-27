/**
 * Colored Add Node Icon
 */
export const IconAddNodeColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="9" fill="url(#addnode-gradient)" />
    <path d="M12 8v8M8 12h8" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
    <defs>
      <linearGradient id="addnode-gradient" x1="3" y1="3" x2="21" y2="21" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#66BB6A" />
        <stop offset="100%" stopColor="#43A047" />
      </linearGradient>
    </defs>
  </svg>
);
