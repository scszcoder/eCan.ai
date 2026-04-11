/**
 * Colored History Icon
 */
export const IconHistoryColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Clock face */}
    <circle cx="11" cy="11" r="9" fill="url(#history-gradient)" />
    {/* Clock center */}
    <circle cx="11" cy="11" r="1.5" fill="#FFFFFF" />
    {/* Clock hands */}
    <path
      d="M11 7v4.5l2.5 1.5"
      stroke="#FFFFFF"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    {/* Curved arrow (history indicator) */}
    <path
      d="M15 4.5c1.5 1.5 2.5 3.5 2.5 6 0 2.5-1.5 5-4 6"
      stroke="#FFFFFF"
      strokeWidth="1.5"
      strokeLinecap="round"
      fill="none"
      opacity="0.8"
    />
    <defs>
      <linearGradient id="history-gradient" x1="2" y1="2" x2="20" y2="20" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#8B5CF6" />
        <stop offset="100%" stopColor="#6D28D9" />
      </linearGradient>
    </defs>
  </svg>
);
