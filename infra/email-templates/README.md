# Loupe auth email templates

Branded HTML for the transactional emails Supabase sends during auth
(sign-up confirmation, password reset, magic link). They replace Supabase's
plain defaults so the signup flow looks like Loupe end to end.

## Files

| File | Supabase template | Status |
|------|-------------------|--------|
| `confirm-signup.html` | **Confirm sign up** | Fires on every signup |
| `reset-password.html` | **Reset password** | Fires on every password reset — shows a **6-digit code**, not a link |
| `password-changed.html` | **Security → Password changed** | Notification; off by default — enable the toggle |
| `magic-link.html` | **Magic link or OTP** | Dormant — the app doesn't use passwordless login yet |

The app currently only triggers **Confirm sign up** and **Reset password**.
`password-changed` is a security notification you opt into; `magic-link` is a
ready-to-go template for if/when passwordless login is added.

## How to apply

1. Supabase dashboard → **Authentication → Emails → Templates**.
2. Open a template (e.g. *Confirm sign up*), switch the editor to **Source / HTML**.
3. Replace the entire contents with the matching file here and **Save**.
4. Repeat for each template.

For **Password changed**: it lives under the *Security* section and ships
disabled — flip its toggle on, then paste `password-changed.html` into its HTML.

Send yourself a real test (sign up / request a reset) to confirm rendering —
the dashboard preview doesn't substitute the `{{ . }}` variables.

## Design notes (why it's built this way)

Email clients are far more restrictive than browsers, so these intentionally
differ from the app's dark UI:

- **Light body, dark branded header.** A light card renders reliably in Outlook
  and Gmail dark mode; the dark gradient header band keeps the Loupe identity.
- **Logo is a hosted PNG** (`email-logo.png`, the magnifier mark) — Gmail strips
  SVG, so the mark must be a raster image. The live "Loupe" text sits beside it,
  so even if a client blocks images the brand name still reads. (Gmail proxies
  and shows images by default, so it appears for most recipients.)
- **Bulletproof buttons.** Gradients/rounded corners are ignored by Outlook, so
  every button has a solid `#5e9bff` fallback and a VML `<v:roundrect>` for
  Outlook desktop.
- Brand tokens mirror the app: primary `#5e9bff → #7b5cff`, Inter / JetBrains
  Mono with web-safe fallbacks (clients that strip web fonts get Arial/Menlo).

### The logo asset

All four templates reference `https://www.getloupe.net/email-logo.png` (the
canonical host — the apex `getloupe.net` 308-redirects to `www`, and not every
mail client follows redirects on an `<img>`). That file is
`frontend/public/email-logo.png`, served at the site root once the frontend is
deployed. **The logo only appears after the frontend is deployed** with that
asset present — until then the `<img>` 404s (and the "Loupe" text still shows).

## Variables

- **confirm-signup** and **magic-link** use `{{ .ConfirmationURL }}` (the action link).
- **reset-password** uses `{{ .Token }}` — the 6-digit code, **not** a link. The
  app verifies a typed code because email scanners pre-fetch links and burn the
  one-time token (see `frontend/src/api/auth.ts` → `sendPasswordReset`). Do not
  add a `{{ .ConfirmationURL }}` link to this template or scanners will invalidate
  the code before the user types it.
- **password-changed** is a notification with no action link: `{{ .Email }}`
  (personalization) + `{{ .SiteURL }}` (the "secure your account" link).
