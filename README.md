# CounterFlame WebPort — public playtest

Unofficial web port by Teaser.lua. Deployment repository for the existing WebGL build and multiplayer server.

## Deploy on Render

- Create a Web Service from this repository.
- Runtime: Docker; branch: main; Dockerfile: ./Dockerfile.
- Region: Oregon; compute: Free ($0/month).
- Health check: /; keep the Docker command unchanged.
- The Docker build downloads release web-1791591234 and verifies its SHA-256 before extracting it.
- Render supplies RENDER_EXTERNAL_HOSTNAME and PORT. The launcher configures the matching HTTPS origin automatically.
- HTTPS serves the game and account API. WSS /ws connects multiplayer through the same public domain.

The release package excludes local account databases, Unity editor sources, logs, backups, and QA files. Test APIs are disabled; QA paths are blocked at the proxy.

## Playing with friends

Open the service URL, create separate test accounts, and have one player create a custom lobby. Other players join with its room code and choose teams.

## Free-plan limitations

Render can sleep after inactivity, so the first visit may take time to wake it. Accounts and inventory use ephemeral SQLite storage: data can disappear after sleep, restart, or redeploy. Use this service only for playtests. Bandwidth and free-hour limits still apply.

To update, publish a new release package and update the URL and SHA-256 in download_build.py. Never upload player databases or credentials.
