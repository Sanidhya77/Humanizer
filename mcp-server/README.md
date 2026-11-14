# Humanizer local tools (MCP server)

The Humanizer skill tells Claude *how* to rewrite. This server gives Claude tools to
*measure* the result on your own computer:

| Tool | What it does |
|---|---|
| `measure_change` | Compares your original with the edit. Returns the share of characters reworded per paragraph, the share of the final words that are still yours, and every sentence that was rebuilt. Spelling fixes are counted separately and do not use the edit budget. |
| `check_meaning` | Compares original and edit. Lists any number, citation, link, quote or name that was dropped or invented. |
| `list_registers` / `get_register` | Writing registers: academic level × field (high school to PhD and published papers, six fields, plus sections like methods and discussion), and blog and social platforms. Each has acceptable ranges and a short guide. |
| `check_voice` | Checks a draft against a register and, optionally, your voice profile. Returns what must be fixed, AI patterns, optional voice nudges, and the habits it deliberately does **not** apply in this register. |
| `create_voice_profile` | Learns your habits from your own writing, one profile per genre. `private=True` stores only numbers, no text, for client or company writing. |
| `get_voice_profile` / `list_voice_profiles` | Loads saved profiles. |
| `compare_to_voice` | Shortcut: `check_voice` in the profile's own register. |
| `read_document` | Reads .txt, .md, .docx files. |
| `read_docx_paragraphs` / `rewrite_docx` | Lists the paragraphs of a .docx, then writes the edited ones into a copy. Styles, headings, tables and layout stay as they were. The original file is never changed. |
| `save_output` | Saves the final text, original and report to the output folder. |
| `score_text` | Optional local estimate of how model-like a text reads. It does not predict GPTZero or any other commercial detector. |
| `humanizer_status` | Shows folders, model and calibration state. |

`measure_change`, `check_meaning`, `check_voice` and `score_text` take either the text or a file path, so long
documents do not have to be pasted.

Claude does the rewriting itself, so you don't need an OpenAI or Anthropic API key.

## Requirements

- Python 3.10+ and [uv](https://docs.astral.sh/uv/) (recommended), or plain pip
- About 2 GB of disk for CPU PyTorch and the detector model
- No GPU needed. The default model scores 1,000 words in a few seconds on a laptop i5.

## Install (Windows)

Open PowerShell. Every block below can be pasted as it is.

**1. Install uv** (skip if `uv --version` already works):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. If the repo path has non-ASCII letters or spaces** (for example a OneDrive
folder such as `OneDrive - Universität Beispiel`), make a short ASCII alias first.
Some tools fail on paths like that. A junction is a folder alias and needs no admin rights:

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\HumanizerRepo" -Target "C:\full\path\to\Humanizer"
```

Use `C:\Users\YOU\HumanizerRepo` in every path below.

**3. Install the dependencies** (CPU-only PyTorch, no GPU needed). If the repo sits in
OneDrive, keep the Python environment outside it, or OneDrive will try to sync
thousands of files:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:USERPROFILE\.humanizer-venv"
cd "$env:USERPROFILE\HumanizerRepo\mcp-server"
uv sync
```

**4. Download the detector model once** (~500 MB), so the first chat isn't slow:

```powershell
uv run humanizer-mcp --download
```

**5. Check that it works:**

```powershell
uv run --with pytest pytest tests
"This is a short test paragraph. It only checks that scoring runs end to end on this computer." | Out-File -Encoding utf8 test.txt
uv run humanizer-mcp --score test.txt
```

macOS / Linux: the same steps in a terminal. Skip step 2 unless your path is unusual.

## Connect to Claude Desktop

**1. Find the right config file.** Open Claude Desktop, go to
**Settings → Desktop app** (older versions: **Settings → Developer**) and click
**Edit config**. Use the file it opens.

Don't type the path from memory. On Windows the Microsoft Store version of
Claude Desktop does **not** read `%APPDATA%\Claude\claude_desktop_config.json`.
It reads a file under `%LOCALAPPDATA%\Claude-Data\...` instead, and the
**Edit config** button always opens the right one.

**2. Get the full path to uv** (Claude Desktop often can't find it otherwise):

```powershell
(Get-Command uv).Source
```

**3. Add the server** to the file. Replace `YOU` with your Windows user name, and
use double backslashes:

```json
{
  "mcpServers": {
    "humanizer": {
      "command": "C:\\Users\\YOU\\.local\\bin\\uv.exe",
      "args": ["run", "--directory", "C:\\Users\\YOU\\HumanizerRepo\\mcp-server", "humanizer-mcp"],
      "env": {
        "HUMANIZER_HOME": "C:\\Users\\YOU\\HumanizerRepo\\local",
        "UV_PROJECT_ENVIRONMENT": "C:\\Users\\YOU\\.humanizer-venv"
      }
    }
  }
}
```

If the file already has other settings, add `"humanizer": {...}` inside the existing
`"mcpServers"` block instead of pasting a second one.

**4. Restart Claude Desktop fully**: quit it from the system tray, not just the window.

**5. Check it.** **Settings → Desktop app → Local MCP servers** should show
`humanizer – Running`. In a chat, ask *"run humanizer_status"*.
It should answer with your folders and `"detector_model": "openai-community/gpt2"`.

If it shows an error instead, the log is in the same settings page (**Open logs**).
The usual causes are a wrong `uv` path, single backslashes, or a path with
non-ASCII letters (use the junction from step 2).

**6. Add the skill.** Zip `SKILL.md` together with the `references` folder (both from the repo
root) and upload the zip under **Settings → Capabilities → Skills**.

**Claude Code:** `claude mcp add humanizer -- uv --directory /path/to/Humanizer/mcp-server run humanizer-mcp`

## Using it

Tell Claude whose draft it is and what kind of text it is, for example:

> I wrote this draft myself. Edit it lightly. Register: blog_technical.

Claude then runs this loop (the full version is in [`references/local-tools.md`](../references/local-tools.md)):

1. `check_voice` on the original, to see where it sits in the register.
2. Edit inside your sentences: fix errors, and remove AI patterns where they appear.
3. `measure_change`. Wherever a paragraph is over budget or a sentence was rebuilt, Claude goes back
   to your wording and keeps only the fixes that are needed.
4. `check_voice` (still inside the register?) and `check_meaning` (nothing dropped or invented?).
5. `save_output`, or `rewrite_docx` for a Word file.
6. A short report: how much changed, how much is still your wording, and a list of sentences Claude
   would rewrite, for you to accept or redo yourself.

**The two budgets**

| Mode | Budget per paragraph | Use it for |
|---|---|---|
| `light` | 12% | Fixing spelling, grammar and punctuation only |
| `normal` (default) | 20% | Also removing AI patterns and unclear phrasing |

**Example.** One 330-word draft with many typing errors, edited three ways:

| Edit | Corrections | `changed_pct` | `writer_words_pct` | Rebuilt sentences | `ok` |
|---|---|---|---|---|---|
| Errors fixed | 66 | 11.3 | 83.4 | 0 | yes |
| Reworded in place | 51 | 20.5 | 74.6 | 0 | no (just over 20%) |
| Sentences rebuilt | 24 | 36.3 | 51.2 | 5 | no |

On GPTZero the first two were classed Human and the third AI. See
[docs/edit-budget.md](../docs/edit-budget.md) for the whole test and its limits.

**If an AI wrote the draft**, say so. Claude then runs the full Humanizer rewrite and asks you a
few specific questions, so the text gains what only you know. It stays AI-assisted text, and
Claude will not tell you it "passes".

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `HUMANIZER_HOME` | `~/Humanizer` | Profiles, calibration, custom registers and outputs live here. Keep it out of git (the repo ignores `local/`). |
| `HUMANIZER_OUTPUT_DIR` | `HUMANIZER_HOME/output` | Where finished rewrites are saved |
| `HUMANIZER_MODEL` | `fast` | `fast` (GPT-2, ~500 MB), `accurate` (Qwen2.5-0.5B, ~1 GB, 3–4× slower), or any Hugging Face causal LM id |
| `HUMANIZER_THREADS` | cores − 2 | CPU threads for the detector |
| `UV_PROJECT_ENVIRONMENT` | `mcp-server/.venv` | Where uv puts the Python environment. Set it outside OneDrive/Dropbox folders. |

## How the detector works

For each word, a small language model compares the word you actually wrote with the word
it would typically pick itself. AI text keeps landing on the model's own typical choices;
people pick more surprising words. The gap, averaged over the text, is the
*discrepancy* (method from Fast-DetectGPT, Bao et al., ICLR 2024). It also measures
*burstiness*: how much sentence length and predictability vary.

Example: a sentence where every word is the model's top guess scores a discrepancy
around +0.4 (AI-like). A sentence with an odd but correct word choice can drop below 0
(human-like).

Treat the score as a pointer to passages worth a second look. It is a small model's opinion and
does not predict any commercial detector. Rewording a sentence only to lower it works against you:
heavy rewording is what moved human drafts to "AI" in the [edit-budget test](../docs/edit-budget.md).

## Registers and voice

See [REGISTERS.md](REGISTERS.md) for the registers, the research behind each range,
and how voice strength works. The short version: the register decides what is
acceptable, and your voice only steers inside that. Your blog's contractions
never end up in your thesis.

To add a field or platform from real texts you trust:

```
uv run python scripts/build_register.py my_field "C:\path\to\folder_of_texts" --like academic:phd:humanities
```

## Optional: calibrating the local score

Out of the box the 0–100 score uses rough defaults. You can fit it to your own GPTZero results.
Expect a rough match at best: GPTZero is a trained classifier and this is a small language model.

1. Make `HUMANIZER_HOME/calibration/` with `human/` (your own writing), `ai/` (raw AI
   output) and optionally `rewrites/` (Humanizer outputs). 10+ files each, 200+ words.
2. Check files on GPTZero and record the AI % in `calibration/gptzero.csv`:
   ```
   file,ai_percent
   post1.txt,3
   chatgpt_essay.txt,98
   rewrite_07.md,41
   ```
   Files listed there are labelled by GPTZero's verdict; others by their folder.
3. Run `uv run python scripts/calibrate.py --compare`. It tries both models, keeps the one
   that agrees with the labels best, and writes `calibration.json`.

No local detector matches GPTZero exactly, and GPTZero updates its models. Recalibrate
with a few fresh GPTZero checks now and then.

## Tests

```
uv run --with pytest pytest tests
```
