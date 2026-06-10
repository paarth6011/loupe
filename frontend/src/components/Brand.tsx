// The Loupe wordmark + gradient magnifier mark, shared by the dashboard topbar
// and the public status page so the brand stays consistent.
export default function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>
      </span>
      Loupe
    </div>
  );
}
