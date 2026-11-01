# הקרנפים | ברקן — קהילת יוצאי פלוגה ב׳

Hebrew RTL heritage and veterans community. PostgreSQL via Neon; Flask on Render. Membership approval is separate from Google account authentication.

## Security incident: read-only mode

Google Safe Browsing currently flags the `karnafim-community-46.onrender.com` host. Keep account sign-in, member lookup, contact requests, chat, photo uploads and moderation writes disabled. The public archive and memorial pages are available without collecting visitor passwords.

**Three independent release conditions are required to restore private features:**

- `KARNAFIM_MAINTENANCE=0`
- `KARNAFIM_SAFETY_RELEASE_APPROVED=1`
- Google OAuth must be explicitly enabled and pass client ID/secret configuration checks (`KARNAFIM_GOOGLE_AUTH_ENABLED=1`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).

If any condition is missing or invalid, the server boots read-only without reading the private database. Never set the release-approval variable before a verified clean Google Safe Browsing classification and passing security regression tests. The release flag is an operator approval, *not* an automatic Google API status check.

Google OAuth also separately requires `KARNAFIM_GOOGLE_AUTH_ENABLED=1`, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` injected privately in Render; this must only happen once the host is confirmed safe. The OAuth redirect URI is `https://karnafim-community-46.onrender.com/auth/google/callback`. Never commit secrets or display them in logs.

Set `SECRET_KEY`, `DATABASE_URL` and `ADMIN_EMAIL` privately. Admins and other members must be approved in the DB; Google verifies identity, not military service. Do not display personal details or contact information without member opt-in.

## Read-only checks

`python -m unittest discover -s karnafim-site/tests -p 'test_readonly_boot.py' -v` tests that both ordinary maintenance and a misconfigured maintenance-off switch remain private. `python karnafim-site/security_regression.py --live` checks public routes, retired credential pages and response security headers. Google Safe Browsing reviews remain an external decision; a successful deploy does not clear the browser warning.
