# Publish Nightwave from GitHub to a live website

> **Correct architecture:** GitHub hosts the *source files*. A Render **web service** hosts the app at a public HTTPS URL. Do not turn on GitHub Pages: Pages cannot execute the Python backend or accept the live WebSocket connections.

## No-terminal route

1. Extract the complete `nightwave-chat-github-ready.zip` archive.
2. Go to **github.com/new** and create a repository such as `nightwave-chat`.
3. Select **Add file → Upload files** or GitHub's **uploading an existing file** link. Upload the *extracted files and folders*, not the archive. Make sure `render.yaml` and `Dockerfile` sit at the top level; include hidden `.github/workflows/tests.yml` and `.gitignore`.
4. Commit the upload. Click the **Actions** tab to see the automated API and WebSocket tests.
5. Visit **dashboard.render.com → New → Blueprint**. Connect the GitHub repository, review the service, and approve the paid plan/disk and deployment.
6. Open the URL Render shows for your `nightwave-chat` web service. The homepage and API both work under this same `https://…onrender.com` address.
7. Open the site in two separate browsers, choose different usernames, send a Global message and then a DM. Reload both pages to confirm persistence.

## Using git instead of GitHub's upload interface

Run these commands **inside the extracted directory**:

```bash
git init
git add .
git commit -m "Initial Nightwave chat release"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/nightwave-chat.git
git push -u origin main
```

Create the empty repository on GitHub first and replace `YOUR_GITHUB_USERNAME`. If GitHub asks you to authenticate, use its approved Git credential/login flow; do not paste passwords into command lines.

## Troubleshooting

- **Render doesn't see `render.yaml`:** It must be at the GitHub repository root, next to `Dockerfile`; delete unnecessary wrapper folders.
- **Render requests a payment method:** The default `starter` plan plus disk is intentionally paid to keep usernames and message history across deploys. Check the current pricing before approving.
- **Wrong public URL:** Use the Render-provided HTTPS URL, not the GitHub repo URL and not a GitHub Pages URL.
- **Server starts then exits with a SQLite error:** Check Render logs, verify a disk is mounted at `/app/data` and `DATABASE_PATH=/app/data/nightwave.db`. The Docker entrypoint fixes permissions on a newly mounted disk.
- **Messages appear to disappear:** Verify you deployed the **Blueprint** and it included the persistent disk. A manual free service has an ephemeral filesystem.
- **Status shows 'Reconnecting':** Check that the host supports WebSocket upgrades and that you are opening the HTTPS URL. If you configured `PUBLIC_ORIGIN`, it must exactly match the website's `https://` origin, with no trailing slash.
- **A former username is unavailable:** With zero login, the browser session cookie is the only credential. Lost cookie = lost ownership of the username (by design; no recovery flow).

## Domain name

Render already gives a `*.onrender.com` HTTPS URL. You do not need to purchase a domain. If you have one, add it under Render **Settings → Custom Domains**, follow Render's DNS instructions, then update `PUBLIC_ORIGIN` only if you had explicitly set it previously.

## Before inviting a large public audience

Add moderation and abuse-reporting, a block feature, durable anti-spam controls, backups/recovery strategy, and an account-recovery decision. DM privacy here means access control, **not end-to-end encryption**.
