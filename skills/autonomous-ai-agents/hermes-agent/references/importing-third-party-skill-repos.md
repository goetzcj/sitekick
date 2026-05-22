# Importing third-party skill repositories

Use this when a user asks to import/install skills from a GitHub repo that contains multiple skill directories, such as `agentmail-to/agentmail-skills`.

## Pattern

1. Inspect the repository structure first. Look for one or more directories containing `SKILL.md`.
2. Add the repo as a tap when appropriate:
   ```bash
   hermes skills tap add owner/repo
   hermes skills tap list
   ```
   In the `/opt/hermes` checkout, use:
   ```bash
   /opt/hermes/.venv/bin/python /opt/hermes/hermes ...
   ```
3. Do not assume a tap exposes every skill in the repo through search. If search only returns a subset, install each `SKILL.md` by raw GitHub URL:
   ```bash
   hermes skills install https://raw.githubusercontent.com/owner/repo/main/<skill-dir>/SKILL.md --category <category> --yes
   ```
4. If the security scanner blocks with `CAUTION` only because the skill text contains normal package install snippets (`pip install ...`, `npm install ...`), and the user explicitly requested that repo, rerun with `--force` and mention the reason in the final note.
5. Direct `SKILL.md` URL installs may install only `SKILL.md`, not linked `references/`, `templates/`, or `scripts/` directories. If the repo has support files, copy them into the installed skill directory or otherwise ensure they are installed.
6. Verify from Hermes, not just the filesystem:
   ```bash
   hermes skills list | grep -E '<skill-name>|<category>'
   ```
   Also verify linked support files are present when relevant.
7. Tell the user to run `/reload-skills` or start a new session if they are already in an active session.

## Pitfalls

- `python` may not exist in the shell; use the Hermes venv Python path in source checkouts.
- `hermes skills search <term>` can return official or registry results and may not list every skill from a newly added tap.
- A successful install command does not prove linked reference files were included; check them explicitly.
