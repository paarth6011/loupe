import { useRef, useState, type ReactNode } from "react";

// Shared building blocks for the auth screens (sign in / sign up / reset).
// SVG icons only (no emoji), labelled inputs, 44px touch targets, visible focus,
// and aria-live banners — per the project's design system + a11y baseline.

function MagnifierIcon() {
  return (
    <svg
      width="22"
      height="22"
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
  );
}

function EyeIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10.7 5.1A10.6 10.6 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-2.2 3.2M6.6 6.6A18 18 0 0 0 2 12s3.5 7 10 7a10.6 10.6 0 0 0 4.3-.9" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
      <path d="m2 2 20 20" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4M12 16h.01" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4M12 8h.01" />
    </svg>
  );
}

/** The gradient magnifier mark + wordmark, reused by the card and the showcase. */
function BrandLockup({ className }: { className?: string }) {
  return (
    <div className={`auth-brand${className ? ` ${className}` : ""}`}>
      <span className="auth-mark">
        <MagnifierIcon />
      </span>
      <span className="auth-wordmark">Loupe</span>
    </div>
  );
}

/** One KPI chip echoing the dashboard cards (accent rule + mono figure). */
function StatChip({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div
      className="auth-stat"
      style={{ ["--stat-accent" as string]: accent } as React.CSSProperties}
    >
      <span className="auth-stat-label">{label}</span>
      <span className="auth-stat-value num">{value}</span>
    </div>
  );
}

/** A decorative area chart in the brand colour for the showcase preview. */
function Sparkline() {
  const line =
    "M0,70 C22,66 34,56 52,58 C72,60 84,46 104,42 C126,38 138,50 160,38 " +
    "C184,25 198,32 220,30 C246,28 258,16 280,20 C300,23 312,14 320,15";
  return (
    <svg
      className="auth-spark"
      viewBox="0 0 320 84"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="authSparkFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.34" />
          <stop offset="100%" stopColor="var(--primary)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L320,84 L0,84 Z`} fill="url(#authSparkFill)" />
      <path
        d={line}
        fill="none"
        stroke="var(--primary)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Branded product showcase shown beside the form on wide screens. It speaks the
 * dashboard's visual language — wordmark, the accent rule, a live mini-panel
 * with a sparkline and KPI chips — so signing in feels like the same product.
 * Collapses out on narrow screens, where the form card carries the brand.
 */
function AuthAside() {
  return (
    <aside className="auth-aside">
      <BrandLockup className="auth-brand-aside" />
      <div className="auth-aside-body">
        <p className="auth-aside-title">
          Observability for your
          <br />
          LLM workloads.
        </p>
        <p className="auth-aside-sub">
          Track cost, latency, and errors across every model — live, in one
          dashboard.
        </p>
        <div className="auth-preview" aria-hidden="true">
          <div className="auth-preview-head">
            <span className="auth-preview-bar" />
            <span>Latency · p95</span>
            <span className="auth-preview-live">
              <span className="auth-preview-dot" />
              live
            </span>
          </div>
          <Sparkline />
          <div className="auth-stats">
            <StatChip label="Requests" value="1.2M" accent="var(--primary)" />
            <StatChip label="p95" value="2.1s" accent="var(--violet)" />
            <StatChip label="Spend" value="$1.5k" accent="var(--green)" />
          </div>
        </div>
      </div>
    </aside>
  );
}

/**
 * Two-pane auth layout: the branded showcase beside the form card. The card
 * holds the brand mark, title/subtitle, the form, and an optional footer. On
 * narrow screens the showcase drops away and the card stands on its own.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="auth-wrap">
      <div className="auth-grid">
        <AuthAside />
        <main className="auth-card">
          <BrandLockup className="auth-brand-card" />
          <header className="auth-head">
            <h1 className="auth-title">{title}</h1>
            {subtitle ? <p className="auth-sub">{subtitle}</p> : null}
          </header>
          {children}
          {footer ? <div className="auth-foot">{footer}</div> : null}
        </main>
      </div>
    </div>
  );
}

export function TextField({
  id,
  label,
  type = "text",
  value,
  onChange,
  autoComplete,
  inputMode,
  required = true,
}: {
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  inputMode?: "text" | "numeric" | "email";
  required?: boolean;
}) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="field-input"
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        inputMode={inputMode}
        required={required}
      />
    </div>
  );
}

/**
 * Segmented one-time-code input: `length` single-digit boxes that auto-advance
 * as you type, step back on Backspace, and accept a pasted code into any box.
 * `value` is the joined string; only digits are kept.
 */
export function OtpInput({
  id,
  label,
  value,
  onChange,
  length = 6,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  length?: number;
}) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);

  function focusBox(i: number) {
    refs.current[Math.max(0, Math.min(i, length - 1))]?.focus();
  }

  // Overwrite from box `start` with `digits`, returning the next empty index.
  function fillFrom(start: number, digits: string) {
    const arr = value.padEnd(length, " ").slice(0, length).split("");
    let j = start;
    for (const d of digits) {
      if (j >= length) break;
      arr[j] = d;
      j += 1;
    }
    onChange(arr.join("").replace(/ /g, "").slice(0, length));
    return j;
  }

  function handleChange(i: number, raw: string) {
    const digits = raw.replace(/\D/g, "");
    if (!digits) {
      // A non-digit / cleared box: blank just this slot.
      const arr = value.padEnd(length, " ").slice(0, length).split("");
      arr[i] = " ";
      onChange(arr.join("").replace(/ /g, "").slice(0, length));
      return;
    }
    const next = fillFrom(i, digits);
    focusBox(next);
  }

  function handleKeyDown(i: number, e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !value[i] && i > 0) {
      e.preventDefault();
      fillFrom(i - 1, " ");
      focusBox(i - 1);
    } else if (e.key === "ArrowLeft" && i > 0) {
      focusBox(i - 1);
    } else if (e.key === "ArrowRight" && i < length - 1) {
      focusBox(i + 1);
    }
  }

  function handlePaste(i: number, e: React.ClipboardEvent<HTMLInputElement>) {
    const digits = e.clipboardData.getData("text").replace(/\D/g, "");
    if (!digits) return;
    e.preventDefault();
    focusBox(fillFrom(i, digits));
  }

  return (
    <div className="field">
      <span className="field-label" id={`${id}-label`}>
        {label}
      </span>
      <div className="otp-row" role="group" aria-labelledby={`${id}-label`}>
        {Array.from({ length }, (_, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            id={`${id}-${i}`}
            className="otp-box"
            type="text"
            inputMode="numeric"
            autoComplete={i === 0 ? "one-time-code" : "off"}
            maxLength={1}
            value={value[i] ?? ""}
            aria-label={`${label} digit ${i + 1}`}
            onChange={(e) => handleChange(i, e.target.value)}
            onKeyDown={(e) => handleKeyDown(i, e)}
            onPaste={(e) => handlePaste(i, e)}
            onFocus={(e) => e.target.select()}
          />
        ))}
      </div>
    </div>
  );
}

export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  hint?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <div className="field-pw">
        <input
          id={id}
          className="field-input"
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          required
          aria-describedby={hint ? `${id}-hint` : undefined}
        />
        <button
          type="button"
          className="pw-toggle"
          onClick={() => setShow((s) => !s)}
          aria-label={show ? "Hide password" : "Show password"}
          aria-pressed={show}
        >
          {show ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
      {hint ? (
        <p className="field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function FormBanner({
  kind,
  children,
}: {
  kind: "error" | "notice";
  children: ReactNode;
}) {
  return (
    <div
      className={`auth-banner auth-banner-${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      <span className="auth-banner-icon">
        {kind === "error" ? <AlertIcon /> : <InfoIcon />}
      </span>
      <span>{children}</span>
    </div>
  );
}

/** Full-width primary submit button with a loading spinner. */
export function AuthButton({
  busy,
  children,
  busyLabel,
}: {
  busy: boolean;
  children: ReactNode;
  busyLabel: string;
}) {
  return (
    <button type="submit" className="auth-btn" disabled={busy}>
      {busy ? (
        <>
          <span className="spinner" aria-hidden="true" />
          {busyLabel}
        </>
      ) : (
        children
      )}
    </button>
  );
}

export function LinkButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" className="link-button" onClick={onClick}>
      {children}
    </button>
  );
}
