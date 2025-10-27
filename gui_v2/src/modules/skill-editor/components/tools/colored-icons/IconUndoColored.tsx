/**
 * Colored Undo Icon
 */
export const IconUndoColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z"
      fill="url(#undo-gradient)"
    />
    <defs>
      <linearGradient id="undo-gradient" x1="2" y1="7" x2="22" y2="16" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#9B59B6" />
        <stop offset="100%" stopColor="#8E44AD" />
      </linearGradient>
    </defs>
  </svg>
);
