/**
 * Colored Zoom Icon
 */
export const IconZoomColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="10" cy="10" r="7" stroke="url(#zoom-gradient)" strokeWidth="2" fill="none" />
    <path d="M15 15l6 6" stroke="url(#zoom-handle-gradient)" strokeWidth="2" strokeLinecap="round" />
    <path d="M7 10h6M10 7v6" stroke="url(#zoom-cross-gradient)" strokeWidth="2" strokeLinecap="round" />
    <defs>
      <linearGradient id="zoom-gradient" x1="3" y1="3" x2="17" y2="17" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#29B6F6" />
        <stop offset="100%" stopColor="#0288D1" />
      </linearGradient>
      <linearGradient id="zoom-handle-gradient" x1="15" y1="15" x2="21" y2="21" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#29B6F6" />
        <stop offset="100%" stopColor="#0288D1" />
      </linearGradient>
      <linearGradient id="zoom-cross-gradient" x1="7" y1="7" x2="13" y2="13" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#29B6F6" />
        <stop offset="100%" stopColor="#0288D1" />
      </linearGradient>
    </defs>
  </svg>
);
