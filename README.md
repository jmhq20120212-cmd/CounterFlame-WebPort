# CounterFlame WebPort — public playtest

Unofficial web port by Teaser.lua. Deployment repository for the existing WebGL build and multiplayer server.

## Deploy on Render

- Create a Web Service from this repository.
- Runtime: Docker; branch: main; Dockerfile: ./Dockerfile.
- Region: Oregon; compute: Free ($0/month).
- Health check: /; keep the Docker command unchanged.
- The Docker build downloads base release web-1791591234 plus the persistent arena and communications overlays, verifying every SHA-256 hash.
- Before deploying, set CF_TURSO_URL and CF_TURSO_AUTH_TOKEN as private Render environment variables. The token must be scoped to the account database with read/write access.
- Import an available private SQLite backup into the empty database with LocalServer/migrate_accounts.py and verify the result. Then set CF_ACCOUNT_MIGRATION_VERIFIED=1. Startup refuses unconfigured temporary storage.
- Render supplies RENDER_EXTERNAL_HOSTNAME and PORT. The launcher configures the matching HTTPS origin automatically.
- HTTPS serves the game and account API. WSS /ws connects multiplayer through the same public domain.

The release package excludes local account databases, Unity editor sources, logs, backups, and QA files. Test APIs are disabled; QA paths are blocked at the proxy.

## Playing with friends

Open the service URL, create separate test accounts, and have one player create a custom lobby. Other players join with its room code and choose teams.

## Room communication and accounts

- Press T to open room chat and Enter to send. Escape closes the input.
- Press O for push-to-talk. In Settings > Microphone, enable microphone access, choose an input and voice output, switch to always-active mode or change the key. Output selection depends on browser support.
- Voice stops transmitting when the game loses focus and the microphone stops on room exit. Text and audio are relayed only to the current room and are not stored.
- Sign out is available at the bottom of Profile. The 1000-coin welcome reward is issued only once per client IP; additional accounts start at zero. Existing balances and inventories are preserved.

## Free-plan limitations

Render can sleep after inactivity, so the first visit may take time to wake it. Accounts, password hashes, inventories and saved progression live in Turso, independently of the Render instance. Keep periodic private database exports. Bandwidth, database quotas and free-hour limits still apply. Data already lost from an older ephemeral instance cannot be recreated without a backup.

To update, publish a new release package and update the URL and SHA-256 in download_build.py. Never upload player databases or credentials.
