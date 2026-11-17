export default function Brand({ size = 26 }) {
  return (
    <span className="brand">
      <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
        <path d="M9 10L23 9M9 10l7 13M23 9l-7 14" stroke="#1F2430" strokeWidth="1.5" fill="none" />
        <circle cx="9" cy="10" r="4" fill="#2F5FD0" />
        <circle cx="23" cy="9" r="3" fill="#0F9D8A" />
        <circle cx="16" cy="23" r="4" fill="#D9822B" />
      </svg>
      Knowledge Graph
    </span>
  );
}
