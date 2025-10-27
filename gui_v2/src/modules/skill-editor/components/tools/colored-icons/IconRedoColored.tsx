/**
 * Colored Redo Icon
 */
export const IconRedoColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M18.4 10.6C16.55 8.99 14.15 8 11.5 8c-4.65 0-8.58 3.03-9.96 7.22L3.9 16c1.05-3.19 4.05-5.5 7.6-5.5 1.95 0 3.73.72 5.12 1.88L13 16h9V7l-3.6 3.6z"
      fill="url(#redo-gradient)"
    />
    <defs>
      <linearGradient id="redo-gradient" x1="2" y1="7" x2="22" y2="16" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#E74C3C" />
        <stop offset="100%" stopColor="#C0392B" />
      </linearGradient>
    </defs>
  </svg>
);
