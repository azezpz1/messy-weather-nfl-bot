# messy-weather-sports-bot

A bot to post messy NFL weather games to various social media sites

On the morning of NFL game days, this bot checks the forecast for every outdoor
stadium hosting a game that day, ranks them by how messy the weather looks
(snow first, then by a combined score of wind, precipitation odds, and
temperature extremes), and posts a weather report — currently to
[Bluesky](https://bsky.app), with a clean abstraction to add more platforms
later.

Games in domed, fixed-roof, or retractable-roof stadiums are skipped, since
roof status isn't reliably knowable ahead of time. If there are no outdoor
games that day, the bot posts nothing.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Configuration

The schedule (ESPN) and weather (National Weather Service) APIs are free and
require no credentials. Posting to Bluesky needs an
[app password](https://bsky.app/settings/app-passwords), set via environment
variables:

| Env var                 | Description                                   |
| ------------------------ | ---------------------------------------------- |
| `BLUESKY_HANDLE`         | Your Bluesky handle, e.g. `example.bsky.social` |
| `BLUESKY_APP_PASSWORD`   | An app password (not your account password)     |

## Running

```sh
# Preview what would be posted today, without posting anywhere:
uv run messy-weather-nfl-bot --dry-run

# Post for real (requires BLUESKY_HANDLE / BLUESKY_APP_PASSWORD):
uv run messy-weather-nfl-bot

# Post to multiple platforms at once (as more are added):
uv run messy-weather-nfl-bot --platforms bluesky
```

## Running on a schedule (e.g. a Raspberry Pi)

This script doesn't schedule itself — run it via cron (or any scheduler) on
game mornings. It's a no-op (exits cleanly, posts nothing) on days with no
outdoor NFL games, so it's safe to run daily if you'd rather not maintain a
precise NFL schedule in your crontab. A typical crontab entry, run at 9am on
Thursdays, Sundays, and Mondays:

```cron
# m h  dom mon dow          command
0  9   *   *   0,1,4        cd /path/to/messy-weather-nfl-bot && uv run messy-weather-nfl-bot
```

Cron does not load your shell profile or `.env` files automatically, so
`BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD` won't be set unless you provide
them explicitly: set them directly in the crontab, or in a wrapper script
that exports them before invoking `uv`.

### Updating to the latest release

Releases are cut via the "Release" GitHub Actions workflow (run manually from
the Actions tab), which bumps the version, tags it (`vX.Y.Z`), and publishes
a GitHub release. Rather than tracking `main` directly, point a deployment
(e.g. a Raspberry Pi) at the latest tag instead:

```sh
cd /path/to/messy-weather-nfl-bot
git fetch --tags
git checkout "$(git describe --tags "$(git rev-list --tags --max-count=1)")"
uv sync
```

Run that before your scheduled job (e.g. as the first line of the wrapper
script your crontab invokes) to stay on the latest release without ever
checking out unreleased commits from `main`.

## Development

```sh
uv run ruff check .      # lint
uv run ty check          # type check
uv run pytest            # unit + integration tests, with coverage
uv run pytest -m "not integration"  # unit tests only (no network)
```

Integration tests hit the real ESPN and NWS APIs (no credentials needed) but
never post to Bluesky — they use a console-printing poster instead. They run
in CI on every push and pull request via GitHub Actions.

### Code coverage

`pytest` runs with [`pytest-cov`](https://pytest-cov.readthedocs.io/) enabled
by default (see `[tool.pytest.ini_options]` / `[tool.coverage.*]` in
`pyproject.toml`), printing a per-file report and failing if total coverage
drops below 80%. CI also writes `coverage.xml` and uploads it as a build
artifact. For a browsable HTML report locally:

```sh
uv run pytest --cov-report=html
open htmlcov/index.html
```
