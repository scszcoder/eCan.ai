/**
 * Colored Save Icon
 */
export const IconSaveColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4z"
      fill="url(#save-gradient)"
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
    <defs>
      <linearGradient id="save-gradient" x1="3" y1="3" x2="21" y2="21" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#4A90E2" />
        <stop offset="100%" stopColor="#357ABD" />
      </linearGradient>
    </defs>
  </svg>
);
