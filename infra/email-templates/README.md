# Loupe auth email templates

Branded HTML for the transactional emails Supabase sends during auth
(sign-up confirmation, password reset, magic link). They replace Supabase's
plain defaults so the signup flow looks like Loupe end to end.

## Files

| File | Supabase template | Status |
|------|-------------------|--------|
| `confirm-signup.html` | **Confirm sign up** | Fires on every signup |
| `reset-password.html` | **Reset password** | Fires on every password reset |
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
- **No image or SVG logo.** Gmail strips SVG and blocks images by default, so
  the mark is a CSS gradient chip + live "Loupe" text — it always shows, even
  with images off. Nothing to host.
- **Bulletproof buttons.** Gradients/rounded corners are ignored by Outlook, so
  every button has a solid `#5e9bff` fallback and a VML `<v:roundrect>` for
  Outlook desktop.
- **Plain-link fallback** under every button for clients that mangle the CTA.
- Brand tokens mirror the app: primary `#5e9bff → #7b5cff`, Inter / JetBrains
  Mono with web-safe fallbacks (clients that strip web fonts get Arial/Menlo).

## Variables

The action emails (confirm, reset, magic link) use only `{{ .ConfirmationURL }}`.
`password-changed.html` is a notification with no action link, so it uses
`{{ .Email }}` (personalization) and `{{ .SiteURL }}` (the "secure your account"
link). If you switch an action flow to OTP codes instead of links, Supabase also
exposes `{{ .Token }}` — drop it into a styled block and point users at the
in-app code entry.
