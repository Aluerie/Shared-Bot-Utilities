# 🔨 Shared-Bot-Utilities

[![Tests](https://github.com/Aluerie/Shared-Bot-Utilities/actions/workflows/tests.yml/badge.svg)](https://github.com/Aluerie/Shared-Bot-Utilities/actions/workflows/tests.yml)

Shared utilities, concepts and small API wrappers for my bots.

At some point I realized that the `utils` folders in [@Aluerie/AluBot](<https://github.com/Aluerie/AluBot>) and [@Aluerie/IrenesBot](<https://github.com/Aluerie/IrenesBot>) held "same but different" files. So, in the spirit of DRY (don't repeat yourself), I moved them into this repository, and both bots now use it as a git submodule.

> [!NOTE]
> This is not a PyPI package and is not meant to be installed. It's a folder of modules that the bots import directly.

## What's inside

| Module | What it does |
| --- | --- |
| `errors` | The exception hierarchy and the `Policy` that tells error handlers whether to respond to the user and/or notify developers. |
| `concepts` | Building blocks for the bots: `BotBase`, the error notification manager, a `tasks.loop` subclass with error notifications, logging setup, the Discord webhook log mirror, the database pool, and `migrations`: numbered SQL files in a bot's `migrations/` folder, applied once each, in order, when the bot starts. |
| `apis` | Small async clients: Steam Web API, dota2.com datafeed, OpenDota, Stratz, 7TV, and the local API of my Dota2Bot. |
| `typings` | `TypedDict` schemas of those APIs' responses. |
| `cache` | `@cache` for async functions (LRU, timed or unlimited) and `ExpiringCache`. |
| `clock` | Datetime helpers: human-readable time differences and Discord timestamps. |
| `fmt` | Text formatting: codeblocks, plurals, ordinals, pretty-printed mappings for embeds. |
| `fuzzy` | Fuzzy string matching, based on RoboDanny's. |
| `scheduler` | Persistent jobs (reminders, birthdays, periodic messages) in a PostgreSQL table, which it creates itself: times on the clocks of a timezone, RRULE repeats, retries, skipping occurrences that are too late, at-least-once delivery across restarts. How it all works: [docs/scheduler.md](../docs/scheduler.md). |
| `gh` | Git helpers: latest commits with gitmoji titles, line counting. |
| `translate` | Google Translate. |
| `globs` | Global constants: user agent, emotes, logos, colours. |
| `timeparse` | Times that users type in ("2h30m", "tomorrow 3pm", "eow", ISO, Discord timestamps), understood in their timezone, and splitting a time from the text of a chat message. |
| `sqlcheck` | For tests: finds the SQL string literals in a bot's source and prepares each one in a throwaway database built from the bot's migrations, so a wrong table or column fails CI instead of prod. |
| `runtime` | Running under a supervisor (systemd now, Docker later): `is_prod` (`BOT_ENV=prod`) to tell prod from a run at home, `notify_ready` (systemd's `READY=1` and Docker's health file), `watchdog_loop` (systemd's watchdog, the health file, and a thread that ends a frozen process after dumping its stacks), and `run_until_sigterm` for a clean shutdown on `systemctl stop` / `docker stop`. |
| `ut` | Everything else: the `MISSING` sentinel, `measure_time`, `run` (uvloop on Linux). |

## Using it in a bot

The code imports itself as `shared` (e.g. `from shared import errors`). So the folder must be named `shared`, and its parent folder must be on `sys.path`. In the bots, that parent is `src/`.

```sh
# add it to a bot
git submodule add https://github.com/Aluerie/Shared-Bot-Utilities src/shared

# clone a bot together with it
git clone --recurse-submodules https://github.com/Aluerie/AluBot

# pull the latest version into a bot
git submodule update --remote src/shared
```

After updating, commit the new submodule commit in the bot's repository.

### Dependencies and tooling

* The runtime dependencies of `shared` are listed in [`pyproject.toml`](../pyproject.toml). Each bot has to list them in its own `pyproject.toml` too, because the bot's environment is the one that runs the code.
* Formatting, linting and type-checking rules come from the bot that contains the submodule. This repository's `pyproject.toml` has no `[tool.ruff]` or `[tool.ty]` sections on purpose, so the bot's config is the one that applies.
* The bot's ruff config needs some per-file ignores for `**/tests/**/*.py` (docstrings on test functions and the like); copy them from AluBot's `pyproject.toml`.

## License

[MPL-2.0](LICENSE). Some modules are adapted from other MPL-licensed projects (mostly [RoboDanny](https://github.com/Rapptz/RoboDanny)); each of those files says where its code comes from.
