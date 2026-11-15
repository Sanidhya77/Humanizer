# Related work: what was reviewed and what was taken from it

Reviewed on 15 November 2026, before version 4.2.0, in two passes. The questions: what do other humanizer projects and current research do, which of it makes this tool better for the writer, and what does nobody else offer?

## The landscape in one page

GitHub lists more than 40 repositories under the `text-humanizer` topic. They fall into four groups:

| Group | Examples | What they offer | What they leave out |
|---|---|---|---|
| Bypass pipelines | lynote-ai/humanize-text, StealthHumanizer, text-humanizer | Multi-pass rewriting, translation chains, "undetectable" output | Any measure of what happened to the text. Reviews keep reporting odd synonyms and changed facts. |
| Pattern-list skills | blader/humanizer (upstream), unslop, harshaneel/humanize, language versions for Russian, Turkish, Korean, Chinese | A prompt that removes known AI phrasings | Measurement. The skill cannot tell you how much it changed or whether a fact was lost. |
| Hosted "humanize and detect" MCP servers | Rephrasy, humantext.pro | Rewrite, then show a detector score falling | They need an API key and credits, and the score is the product. |
| Local checkers | Slop-Chop, Byakugan, SignsofAI | Rule-based detection of AI tells, on your machine | They read one text. None compares the edit with the writer's draft. |

No project found in this review measures the edit against the writer's own draft, limits it, and hands the writer a record of it. That is the gap this fork fills.

## Other humanizer projects

Most open-source "humanizers" on GitHub state one goal: get AI-written text past GPTZero and Turnitin. Their usual methods:

| Method | What it does | Taken? | Why |
|---|---|---|---|
| Translation chains | Translate the text through several languages and back | No | Meaning drifts with every hop. GPTZero lists multi-language translation chains among the attacks it tests its detector against. |
| Multi-pass LLM paraphrasing | Rewrite the text several times with different prompts | No | In our own test, heavy rewording is exactly what moved human drafts to "AI". Detectors are trained on paraphrased output (DAMAGE; GPTZero). |
| Detector-guided rewriting | Rewrite until a local detector's score drops | No | It optimises against one detector on one day, and its purpose is to hide how a text was written. Version 4.1.0 removed the last trace of this from the loop. |
| "Fingerprint disruption" | Hidden characters, look-alike letters, odd spacing | No. The opposite: `check_quality` reports them | They break search, screen readers and copy-paste, and RAID found GPTZero nearly unaffected by look-alike letters. |
| Pattern lists | Remove known AI phrasings | Yes, already | This is what the upstream skill does, and it is kept. |

The upstream project, [blader/humanizer](https://github.com/blader/humanizer), says in its README that it does not try to get past AI detectors and that detectors still flag most of its output. This fork keeps that position.

## Detection research

| Source | Finding | What changed here |
|---|---|---|
| EditLens, Pangram, ICLR 2026 ([arXiv:2510.03154](https://arxiv.org/abs/2510.03154)) | AI-edited text is detectable, and so is the amount of editing. Typo-level fixes count as human; "fix any mistakes" is the smallest kind of AI edit. | Corrections are separated from rewording more carefully. Word swaps are listed so they can be undone. |
| Saha and Feizi 2025, APT-Eval ([arXiv:2502.15666](https://arxiv.org/abs/2502.15666)) | Many detectors flag even minimal AI polishing. | The docs say the budget is a guide. Style drift was added because the kind of change matters, not only its size. |
| Reinhart et al. 2025 ([arXiv:2410.16107](https://arxiv.org/abs/2410.16107)); Kobak et al. 2025 ([arXiv:2406.07016](https://arxiv.org/abs/2406.07016)) | Models overuse "-ing" clauses, nominalizations and a set of style words. | Style drift compares the edit with the writer's own draft on these features and names what the edit added. |
| Abdulhai et al. 2026, Google DeepMind, "How LLMs Distort Our Written Language" ([arXiv:2603.18161](https://arxiv.org/abs/2603.18161)) | When LLMs revise a person's essay they change style and meaning across the whole text, even when asked only for grammar edits. Human expert revisions are small and targeted. LLM-edited essays use fewer pronouns and more nouns, and heavy LLM use made essays far more often neutral on the question asked. | This is the strongest outside support for the edit budget. Style drift now also notes pronouns replaced by nouns, added hedging and removed opinions. |
| DAMAGE 2025 ([ACL Anthology](https://aclanthology.org/2025.genaidetect-1.9.pdf)) | Every humanizer tested lowered fluency. The worst added stray characters, nonsense phrases and invented citations. | `check_quality` was added. `check_meaning` already reports invented citations. |
| Binoculars, Hans et al. 2024 ([arXiv:2401.12070](https://arxiv.org/abs/2401.12070)) | A stronger zero-shot detector than Fast-DetectGPT at low false-positive rates. | Not adopted. It compares two 7B-parameter models, which does not run on a laptop CPU. |

## Showing the work instead of guessing at it

Two things outside the humanizer world shaped version 4.2.0.

**Process records.** [Grammarly Authorship](https://www.grammarly.com/authorship) does not detect AI. It records how a document was written (typed, pasted, edited with grammar suggestions, generated) and turns that into a report the writer can share. The idea carries over: a record of what the editor did is better evidence than a detector's guess. Every saved job now includes `changes.html`, which marks each edit against the writer's draft. It is a record of the edit, not of how the draft was typed, and it says so.

**Disclosure rules.** Publishers now separate assistive use (an AI tool corrects grammar and spelling in the author's own text) from generative use (the tool rewords or writes). Guides to 2026 policies report that Springer Nature and Elsevier exempt copy editing and basic grammar checks from disclosure, that Sage separates assistive from generative use, and that most venues ask for a statement naming the tool, the task, the extent and the human check for anything beyond that ([thesify, 2026 guide](https://www.thesify.ai/blog/ai-policies-academic-publishing-2026); [Kennesaw State University overview](https://campus.kennesaw.edu/offices-services/research/ai-disclosure.php)). `measure_change` already measures where an edit falls on that line, so `ai_use_statement` turns the measurement into a draft statement. Policies differ and change; the tool drafts, the venue's own page decides.

## Considered and left out

- **EditLens as a local score.** A RoBERTa-large checkpoint is published and would run on a CPU. Its licence is CC BY-NC-SA 4.0 (non-commercial) and the download is gated, so it cannot ship with an MIT tool or be used for paid writing work. Anyone who qualifies can try it on their own texts.
- **A longer AI word list.** Kobak et al. publish hundreds of "excess" words. Many are ordinary academic words, and the bundled registers were measured with the current list, so a longer one would need all 34 registers measured again.
- **Grammar checkers (LanguageTool).** Needs Java, and the model doing the editing already checks grammar. `check_quality` looks for damage instead.

## What would improve the tool most from here

More test data, before more features. Also worth doing: a second detector and a second writer in `docs/edit-budget.md`, and a short screen recording of `changes.html` for the README.

On test data: The edit budget rests on three short texts by one writer. Repeating the test with other writers, with academic prose, and in the untested gap between 20% and 36% would do more than any new tool.
