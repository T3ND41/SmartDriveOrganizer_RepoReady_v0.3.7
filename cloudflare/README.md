# Optional `smart.drive.win` installer alias

The Worker serves the PowerShell installer at `/` as `text/plain`, which makes this command work after the custom hostname is connected:

```powershell
irm https://smart.drive.win | iex
```

## Requirements

- You must control the DNS zone for `drive.win` (or be authorized by its owner).
- The `drive.win` zone must be active in the Cloudflare account used to deploy this Worker.
- The GitHub repository `T3ND41/SmartDriveOrganizer` must be public and contain `install.ps1` on `main`.

## Deploy

1. Install Node.js LTS and Wrangler: `npm install --global wrangler`.
2. Authenticate: `wrangler login`.
3. Ensure the `drive.win` zone is present in the Cloudflare account and that you are authorized to add routes.
4. From this `cloudflare` folder, run: `wrangler deploy`.
5. In Cloudflare DNS, confirm the custom Worker route for `smart.drive.win/*` is active.
6. Test the endpoint before using it: `irm https://smart.drive.win` should return readable PowerShell source, not an HTML webpage.

The Worker does not store tokens, files, or user data. It proxies only the public `install.ps1` file from the repository and disables caching so the current installer source is served.

## Immediate fallback without a custom domain

After the repository is public, use the direct GitHub Raw URL:

```powershell
irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer/main/install.ps1 | iex
```

The custom domain cannot work until the owner of `drive.win` configures the DNS route. A subdomain cannot be configured by someone who does not control its parent DNS zone.
