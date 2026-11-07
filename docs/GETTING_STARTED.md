# Spinfix — Getting Started (project kickoff)

How to go from these four files to a running project with Claude Code in VS Code.

## 1. Install the tools (once)

| Tool | How | Check |
|---|---|---|
| Python 3.12 (64-bit) | python.org installer → tick "Add to PATH" | `python --version` |
| Git | `winget install Git.Git` | `git --version` |
| GitHub CLI (optional) | `winget install GitHub.cli` then `gh auth login` | `gh --version` |
| VS Code + Claude Code | already set up | — |
| FFmpeg (for video tools, later) | `winget install Gyan.FFmpeg` | `ffmpeg -version` |
| Inno Setup 6 (for installer, M7) | `winget install JRSoftware.InnoSetup` | — |

## 2. Create the project folder

1. Make a folder, e.g. `D:\Projects\spinfix`.
2. Put the files there like this:
   ```
   spinfix\
     CLAUDE.md
     docs\
       DOCUMENTATION.md
       PLAN.md
       GETTING_STARTED.md
   ```
3. Put your logo PNG (from ChatGPT) in `spinfix\assets\logo.png`.
4. Open the folder in VS Code.

## 3. Set your git identity for this repo (only you as author)

In the VS Code terminal, inside the folder:
```
git init
git config user.name "Vigesh"
git config user.email "154797502+Vigesh-VS@users.noreply.github.com"
```
Check with `git config user.email` — it must show the noreply address.

## 4. Create the GitHub repo

Create a **public** repo `Vigesh-VS/spinfix` on github.com (no README/license — Claude Code
will add them), then:
```
git remote add origin https://github.com/Vigesh-VS/spinfix.git
```

Recommended repo settings (GitHub → Settings):
- Code security → enable **Dependabot alerts**, **secret scanning**, **push protection**,
  **private vulnerability reporting**.
- Branches → protect `main`: require CI to pass before merging.

## 5. First message to Claude Code

Copy this as your first prompt:

> Read `CLAUDE.md`, `docs/DOCUMENTATION.md` and `docs/PLAN.md` fully. Then do **only
> milestone M0** from the plan. Before installing anything, list every dependency you want
> to add with its license and wait for my OK. Commit as Vigesh only, with no AI attribution
> lines. When M0 is done, summarise what you built, how I can check it, and stop.

After each milestone, review and then say e.g.:

> M0 looks good. Start M1. Same rules.

## 6. Daily routine

1. `git pull` → activate venv: `.venv\Scripts\activate`
2. Ask Claude Code to continue the current milestone.
3. Run the app: `python -m spinfix` — try the manual checks listed in PLAN.md.
4. Run tests: `pytest -q`.
5. Check the last commit's author: `git log -1 --format="%an <%ae>%n%b"` → only Vigesh, no
   `Co-Authored-By` line.
6. Push when you're happy: `git push`.

## 7. Before every push — quick safety checklist

- ☐ `gitleaks detect` shows no secrets
- ☐ No `.env`, `.pfx`, keys or personal files in `git status`
- ☐ CI is green
- ☐ Commit author is Vigesh only

## 8. Files still to come

| File | When |
|---|---|
| `README.md` (with screenshots/GIF) | M7, when the app works |
| `HOWTO.md` (install, use, uninstall, FAQ, SmartScreen help) | M7 |
| `SECURITY.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md` | M0 |
| `CHANGELOG.md` | first release |
