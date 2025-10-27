/**
 * Colored Save As Icon
 */
export const IconSaveAsColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4z"
      fill="url(#saveas-gradient)"
    />
    <path
      d="M12 19c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3z"
      fill="#FFFFFF"
      opacity="0.9"
    />
    <path
      d="M15 9H5V5h10v4z"
      fill="#FFFFFF"
      opacity="0.7"
    />
    <path
      d="M17 17h4v2h-4v4h-2v-4h-4v-2h4v-4h2v4z"
      fill="url(#saveas-plus-gradient)"
    />
    <defs>
      <linearGradient id="saveas-gradient" x1="3" y1="3" x2="21" y2="21" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#7E57C2" />
        <stop offset="100%" stopColor="#5E35B1" />
      </linearGradient>
      <linearGradient id="saveas-plus-gradient" x1="11" y1="11" x2="21" y2="23" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#66BB6A" />
        <stop offset="100%" stopColor="#43A047" />
      </linearGradient>
    </defs>
  </svg>
);
