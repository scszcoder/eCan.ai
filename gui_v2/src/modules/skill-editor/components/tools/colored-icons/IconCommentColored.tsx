/**
 * Colored Comment Icon
 */
export const IconCommentColored = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="1 1 22 22" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14l4 4V4c0-1.1-.9-2-2-2z"
      fill="url(#comment-gradient)"
    />
    <path d="M7 9h10v2H7V9zm0-3h10v2H7V6z" fill="#FFFFFF" opacity="0.9" />
    <defs>
      <linearGradient id="comment-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#FFA726" />
        <stop offset="100%" stopColor="#FB8C00" />
      </linearGradient>
    </defs>
  </svg>
);
