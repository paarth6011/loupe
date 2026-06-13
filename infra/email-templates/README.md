# Loupe auth email templates

Branded HTML for the transactional emails Supabase sends during auth
(sign-up confirmation, password reset, magic link). They replace Supabase's
plain defaults so the signup flow looks like Loupe end to end.

## Files

| File | Supabase template |
|------|-------------------|
| `confirm-signup.html` | **Confirm sign up** |
| `reset-password.html` | **Reset password** |
| `magic-link.html` | **Magic link or OTP** |

## How to apply

1. Supabase dashboard → **Authentication → Emails → Templates**.
2. Open a template (e.g. *Confirm sign up*), switch the editor to **Source / HTML**.
3. Replace the entire contents with the matching file here and **Save**.
4. Repeat for each template.

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

All three use only `{{ .ConfirmationURL }}` (the action link). If you switch a
flow to OTP codes instead of links, Supabase also exposes `{{ .Token }}` — drop
it into a styled block and point users at the in-app code entry.
