# Public authentication rollout

This branch prepares email verification and recovery. The live switch and hosted tests require separate authorization. Keep registration private until the tests below pass.

## Before deployment

1. Record the current Supabase Auth configuration and migration history. Confirm the intended server origin is `https://snippet-manager-tan.vercel.app` and matches `SNIPPET_SITE_URL`, the currently registered OAuth redirect, and the intended Vercel environment. If the origin differs, use that exact fixed HTTPS origin for both templates and all matching allowlist entries below. Leave existing OAuth redirect entries in place.
2. Pause Supabase **Allow new users to sign up** and put the old website and snippet API behind a maintenance block. Validate the block from an unauthenticated client. Pausing Flask alone leaves the Supabase signup endpoint reachable. Collect existing account IDs and status privately. Keep a protected backup and migration history. Do not export passwords, access tokens, or email link hashes.
3. Apply `supabase/migrations/20261126005226_public_authentication.sql` once, after the two WP-01 migrations. It records a hold for every Auth identity present at that moment without changing accounts, snippets, or owner IDs. Verify the count of holds matches the pre-cutover account count. Rollback is in `supabase/rollback_public_authentication.sql`. Archive hold IDs and cutoffs privately, keep both maintenance gates in place, and stop routing traffic to the new app before rollback. Returning to the private-test app without these gates could let held accounts bypass verification.

## Dashboard settings

- **Authentication → URL Configuration**. Set **Site URL** to `https://snippet-manager-tan.vercel.app`. Allow the exact URLs `https://snippet-manager-tan.vercel.app/auth/confirm-email` and `https://snippet-manager-tan.vercel.app/auth/reset-password`. Keep the existing `https://snippet-manager-tan.vercel.app/oauth/vscode/callback` entry and OAuth client redirect if already present. Do not add wildcard hosts or a caller-provided destination.
- **Authentication → Sign In / Providers → Email**. Keep email/password enabled and keep the existing password policy. Turn **Confirm email** on while signup remains paused. Keep secure email change and refresh-token rotation enabled. Use an email OTP expiry of **3600 seconds** or shorter if delivery supports it. This implementation uses a ten-minute reset form after link verification. Keep any supported recent-authentication controls compatible with a fresh recovery session, and test them before reopening signup.
- **Authentication → Email → SMTP Settings**. Confirm custom SMTP is enabled and the sender is `snippo.support@gmail.com`. Verify the saved Gmail SMTP hostname and port match the existing configuration (`smtp.gmail.com`, port `465` with TLS or `587` with STARTTLS). Keep the Gmail App Password in Supabase. Disable link rewriting or click tracking if enabled. Gmail can throttle or block delivery independently of Supabase.
- **Authentication → Rate Limits**. Start with **30 auth emails per hour** if the custom SMTP cap permits it, **60 seconds** minimum between repeat confirmation/recovery sends where configurable, and **30 requests per 5 minutes per IP** for signup/sign-in-related and verification endpoints. Confirm how the dashboard groups these controls. Keep the normal token grant limit at **150 per 5 minutes per IP** initially to avoid interrupting desktop refresh. Disable anonymous sign-ins if unused. These are suggested starting values, not verified project settings. Monitor 429s, bounces and Gmail quota. Direct requests can bypass Flask's per-address limits and distributed clients can exhaust the shared email budget. If that occurs, keep signup closed and evaluate Supabase-supported CAPTCHA such as Cloudflare Turnstile with token forwarding from the web forms. CAPTCHA is not part of this change.

## Email templates

In **Authentication → Email → Templates**, replace the template bodies as follows. Use these fixed URLs and preserve the fragment. Do not use the stock `ConfirmationURL` or append the token as a query string. The browser script removes the fragment and sends the hash only after the user clicks Continue. Keep the callback pages free of analytics and set any request-body logging to exclude credentials and tokens.

### Confirm signup

Subject: Verify your Snippo email address

```html
<h2>Verify your Snippo email address</h2>
<p>Open this link and choose Continue to verify your email.</p>
<p><a href="https://snippet-manager-tan.vercel.app/auth/confirm-email#token_hash={{ .TokenHash }}">Verify email</a></p>
<p>If you did not request this account, you can ignore this email.</p>
```

### Reset password

Subject: Reset your Snippo password

```html
<h2>Reset your Snippo password</h2>
<p>Open this link and choose Continue to set a new password.</p>
<p><a href="https://snippet-manager-tan.vercel.app/auth/reset-password#token_hash={{ .TokenHash }}">Reset password</a></p>
<p>If you did not request a reset, you can ignore this email.</p>
```

## Existing private-test accounts

Previously auto-confirmed emails are not evidence of mailbox ownership. A held account cannot create a web session, use an existing web cookie, or access the snippet API with a directly obtained Supabase OAuth token. Provider-side recovery does not release the hold. Verify the rightful owner independently using the prior private testing channel and known account history before starting an assisted recovery. Keep disputed accounts on hold and do not transfer legacy snippets based only on control of the claimed mailbox.

For each approved identity, keep the hold in place while the rightful owner completes a password reset through the new Snippo email link. This proves delivery and email control, updates the password on the same user ID, revokes old sessions, and records an app JWT cutoff. Check provider Auth logs for that user's successful password update and OAuth grant revocation or manual equivalent. For a disputed or unavailable mailbox, use Supabase Auth Admin's supported user-update flow to a separately verified address only after the ownership review. The operator must confirm that the address is unused and repeat assisted recovery. Never hand an account to the claimant of a previously unverified address.

After checking ownership, the captured reset timestamp and revocation, an administrator can remove **only that user's hold**. Replace the placeholders with the verified UUID and the recorded cutoff integer from the assisted reset. Leave the cutoff in place. These statements are for the separately authorized cutover only.

```sql
BEGIN;
DELETE FROM snippet_private.legacy_email_holds AS holds
USING snippet_private.session_cutoffs AS cutoff
WHERE holds.user_id = '<verified-user-uuid>'::uuid
  AND cutoff.user_id = holds.user_id
  AND cutoff.invalid_through = '<verified-cutoff-epoch>'::bigint
RETURNING holds.user_id, cutoff.invalid_through;
COMMIT;
```

Expect exactly one returned row. If none is returned, leave the hold in place and recheck the UUID and cutoff. Test a fresh login and the old browser/desktop session before reopening access. If provider grant revocation was unavailable, keep the hold until the operator can verify old credentials or sessions cannot refresh. Supabase password changes revoke other refresh sessions. Already issued JWTs can remain valid at provider endpoints until expiration. Snippo rejects JWTs issued through its cutoff and removes stored web sessions. Fresh sign-in may need a new second after reset because JWT times have one-second precision.

## Activate and verify

1. With public access gated and provider signup paused, separately deploy this backend and verify the held accounts cannot sign in or use stale web and desktop sessions. Confirm the callback redirect and PKCE remain unchanged.
2. Verify **Confirm email** is on before enabling signup. Temporarily enable signup for a supervised test while the web gate remains restricted. Supabase Auth is independently reachable during this interval, so keep it short and pause signup again if any test fails.
3. Register using a fresh mailbox outside the Supabase project team. Check Gmail SMTP delivery timestamp and the actual sender, including the spam folder. Try signing in before verification and confirm denial. Open the email and check that loading the link alone leaves the account unverified. Click **Continue**, then sign in and verify exactly four starter snippets. Test duplicate signup, resend, provider cooldown/429, and expired and reused links.
4. Request a reset for the new account. Verify the second email arrives and the expired or used recovery link cannot change the password. Change the password, then check that the old password, web cookie, and desktop session cannot access Snippo. Verify login with the new password and desktop reauthorization. Perform the same delivery check during an assisted legacy recovery.
5. Use two new verified accounts to verify web and API owner isolation, desktop Show/Search/Insert, persistence across a restart, token renewal and sign-out. Confirm the public Auth provider settings and configured rate limits. Remove the public gate only after the separately approved live checks and outstanding privacy/deletion and release gates are resolved.

References: [Supabase email templates](https://supabase.com/docs/guides/auth/auth-email-templates), [password authentication](https://supabase.com/docs/guides/auth/passwords), [rate limits](https://supabase.com/docs/guides/auth/rate-limits), [custom SMTP](https://supabase.com/docs/guides/auth/auth-smtp), [sessions](https://supabase.com/docs/guides/auth/sessions), and [Gmail sending limits](https://support.google.com/mail/answer/22839).
