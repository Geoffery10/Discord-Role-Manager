![rolm_3_Banner](graphics/rolm_3.png)

# Discord-Role-Manager (Rolm)
[![Pipeline](https://img.shields.io/github/actions/workflow/status/Geoffery10/Discord-Role-Manager/test.yml)](https://github.com/Geoffery10/Discord-Role-Manager/actions/workflows/test.yml) ![Coveralls](https://img.shields.io/coverallsCoverage/github/Geoffery10/Discord-Role-Manager)
![GitHub contributors](https://img.shields.io/github/contributors/Geoffery10/Discord-Role-Manager)
![GitHub top language](https://img.shields.io/github/languages/top/Geoffery10/Discord-Role-Manager)

This is a role manager for my personal Discord servers
## Table of Contents
* [Getting Started](#getting-started)
* [Dashboard](#dashboard)
* [Authentik Integration](#authentik-integration)
* [Built With](#built-with)
* [Contributing](#contributing)
* [Authors](#authors)
* [License](#license)

## Getting Started
1. Clone or download the repository.
2. Ensure you have Python 3.10+ installed.
3. Install the project dependencies with `pdm install`.
4. (Optional) Install development dependencies for testing: `pdm install -d`.
5. Configure `roles.json` with the roles you want to manage and their associated emojis.
6. Copy `.env.example` to `.env` and fill in your Discord bot token and other settings.
7. To run the bot, execute `pdm run` (or `run.bat` on Windows).

## Dashboard
Rolm now includes a built-in web dashboard for managing users, roles, birthdays, guilds, and logs through a dark-themed web UI.

### Features
- **Overview** - live stats cards (users, guilds, reaction roles, birthdays) plus the next upcoming birthday
- **Users** - searchable/filterable user table pulled from the SQLite database
- **Roles** - view and edit reaction role mappings live (writes directly to `roles.json`)
- **Birthdays** - calendar view with month filter and today's birthday highlight
- **Guilds** - birthday channel and birthday role configuration viewer
- **Logs** - tail the latest bot logs in real-time

### Running the Dashboard
You can start the dashboard alongside the bot in a few ways:

**Option 1: Run both at once**
```bash
pdm run dashboard   # dashboard only
# Or use the bundled scripts:
#   Windows (interactive):  run.bat
#   Windows (background):   Rolm_Role_Manager.bat
#   PowerShell:             run.ps1
```

**Option 2: Run separately**
```bash
# Terminal 1
pdm run               # starts the bot
# Terminal 2
pdm run dashboard     # starts the dashboard
```

**Direct launch**
```bash
python -m dashboard.main   # respects DASHBOARD_HOST / DASHBOARD_PORT
```

The dashboard expects `discord.db`, `roles.json`, `birthday.json`, and `rolm.log` in the project root.

### Environment Variables
See `.env.example` for all available variables. Key dashboard variables:
- `DASHBOARD_HOST` - bind address (default `0.0.0.0`)
- `DASHBOARD_PORT` - bind port (default `8080`)
- `OAUTH2` - set to `true` to enable Authentik login
- `AUTHENTIK_CLIENT_ID`
- `AUTHENTIK_CLIENT_SECRET`
- `AUTHENTIK_ISSUER`
- `AUTHENTIK_REDIRECT_URI`
- `AUTHENTIK_USER_INFO_ENDPOINT`

## Authentik Integration
The dashboard supports optional OAuth2 / OIDC authentication via Authentik. When enabled, unauthenticated users are redirected to Authentik to log in before accessing the dashboard.

### Quick Setup
1. In Authentik, create a new **Provider**:
   - Type: OAuth2/OpenID Provider
   - Client type: Confidential
   - Redirect URI: `https://your-dashboard-domain/callback`
   - Scopes: `openid`, `profile`, `email`
2. Create an **Application** linked to that provider.
3. Copy the Client ID, Client Secret, and Issuer URL into your `.env`:
   ```
   OAUTH2=true
   AUTHENTIK_CLIENT_ID=your-client-id
   AUTHENTIK_CLIENT_SECRET=your-client-secret
   AUTHENTIK_ISSUER=https://authentik.yourdomain.com/application/o/your-provider/
   AUTHENTIK_REDIRECT_URI=https://your-dashboard-domain/callback
   AUTHENTIK_USER_INFO_ENDPOINT=https://authentik.yourdomain.com/application/o/userinfo/
   ```
4. Restart the dashboard. Visiting `/` will now redirect unauthenticated users to Authentik.

### Disabling Auth
Set `OAUTH2=false` (or omit the variables) to run the dashboard in open mode for local/trusted networks.

## Running Tests
After installing the development dependencies, you can run the test suite with:
```bash
pdm test
```
or directly with pytest:
```bash
pytest
```

#### Reasons your install failed:

* Missing pdm (Install pdm using `pip install pdm`)

## Contributing

Interested in contributing? Feel free to reach out to me on my discord! geoffery10 <img align="center" width="18" height="18" src="https://cdn3.iconfinder.com/data/icons/popular-services-brands-vol-2/512/discord-128.png">

## Authors
* Geoffery Powell - [Geoffery10](https://github.com/Geoffery10)

## License

This project is licensed under the **GNU General Public License v3.0** – see the [LICENSE](LICENSE) file for details.
