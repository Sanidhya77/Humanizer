# Humanizer: a copy editor for your drafts, with a record of every change

Most "humanizers" rewrite your text until a detector stops flagging it. This one does the opposite.
It edits the way a human copy editor does (small, targeted changes inside your own sentences),
measures how much it changed, and gives you a record you can show.

It is a fork of [blader/humanizer](https://github.com/blader/humanizer). The original skill tells the
model *how* to edit. This fork adds an MCP server ([`mcp-server/`](mcp-server/README.md)) that runs on
your own computer, with no API key, and *measures* the edit.

### How it differs

| | Paraphrasing humanizers | Pattern-list skills | This fork |
|---|---|---|---|
| What it does to your draft | Rewrites it, often several times | Removes known AI phrasings | Fixes errors and AI phrasings inside your sentences |
| How much it changes | Not measured | Not measured | Measured per paragraph, inside a budget (12% or 20%) |
| Your facts | Often drift | Not checked | Every number, citation, link and quote is checked |
| Your voice | Replaced by the tool's | Kept if you give a sample | Your draft is the reference; drift away from it is reported |
| What you can show afterwards | A detector score | Nothing | A change record and a draft AI-use statement |
| Runs where | Usually a paid web service | In your agent | In your agent, tools on your own computer |

### What you get

- **An edit budget.** `measure_change` reports the share of your wording that was reworded, paragraph by
  paragraph, and names every sentence that was rebuilt. Spelling fixes do not count against the budget.
- **A change record.** Each job saves `changes.html`: your draft and the edit in one page, removed words
  struck through and added words underlined, with the numbers on top.
- **An honest AI-use statement.** `ai_use_statement` says which kind of help the edit was (spelling and
  grammar only, language revision, substantial rewriting, or text the tool wrote) and drafts the
  disclosure that journals, universities and clients ask for.
- **Style drift.** Did the edit pull your text toward model habits: overused words, added dashes,
  written-out contractions, a removed "I", softened claims, longer words?
- **Meaning.** Did any number, citation, link, quote or name get dropped or invented?
- **Quality.** Did the edit make anything worse? Doubled words, open brackets, cut-off paragraphs,
  hidden characters and look-alike letters are reported before the text is saved.
- **Register.** Is the draft inside what is normal for this kind of writing? There are 34 registers
  measured from real pre-2020 texts: high school to published papers, across six fields, plus blogs,
  newsletters and forum posts. See [REGISTERS.md](mcp-server/REGISTERS.md).
- **Voice (optional).** Learns your habits from your own writing and applies them only inside the
  register, so your blog's contractions never end up in your thesis.
- **Word files.** Edited paragraphs are written into a copy of your .docx. Styles, headings, tables and
  layout stay as they were.

**Quick start:** follow [mcp-server/README.md](mcp-server/README.md) (about 15 minutes on Windows),
then ask Claude: *"I wrote this draft myself. Edit it lightly. Register: blog_technical."*

### Why edit lightly: the evidence

In a small test on GPTZero ([docs/edit-budget.md](docs/edit-budget.md)), three human-written drafts
were edited to three depths:

| Edit | Share reworded | Rebuilt sentences | GPTZero | `ai_use_statement` level |
|---|---|---|---|---|
| Light (errors only) | 6 to 11% | 0 | Human, 3 of 3 | copy editing |
| Middle (reworded in place) | 17 to 20% | 0 | Human, 3 of 3 | language revision |
| Heavy (sentences rebuilt) | 36 to 41% | 4 to 5 | AI, 3 of 3 | substantial rewriting or generated text |

The facts were the same in every version. Only the amount of rewording differed. The test is small
(one writer, one detector, one day), so read the budget as a guide.

Published research points the same way. A 2026 study from Google DeepMind
([How LLMs Distort Our Written Language](https://arxiv.org/abs/2603.18161)) found that when LLMs revise a
person's essay they change its style and its meaning across the whole text, even when asked only for
grammar edits, while human editors make small, targeted changes that keep the author's voice. Pangram's
[EditLens](https://arxiv.org/abs/2510.03154) showed that the amount of AI editing in a text can itself
be detected. More in [docs/related-work.md](docs/related-work.md).

### What this fork does not do

- It does not make AI-written text human-written. Detectors are trained on rewritten AI text, and a
  model rewording a model's draft is still a model's draft. For such a draft the skill removes the
  patterns that read badly and asks you for what only you know: your example, your measurement, your
  opinion, in your words. `find_generic` picks the paragraphs worth a question.
- It does not use detector-evasion tricks: no translation chains, no hidden characters, no look-alike
  letters, no rewriting against a detector's score. Those lower quality, and detectors are trained on
  them.
- It does not predict GPTZero, Turnitin or any other commercial detector. The built-in `score_text`
  is an optional local estimate.
- It does not decide what you must disclose. `ai_use_statement` drafts a statement from what it
  measured; the rules of your university, client or journal decide what is required.

Everything below this line is the original Humanizer documentation.

---

Humanizer makes AI-written text sound like a person wrote it, without changing what it says. It is built on Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), the guide Wikipedia editors use to catch AI-generated text, and it works in Claude Code, Codex, and any other agent that supports skills.

**Before:**
> I'm thrilled to announce that shared drafts are finally here! 🚀 For months, our own team was drowning in files named final_v7.docx — and we knew there had to be a better way. Now two people can edit the same doc at once, with every change appearing live for both of them. It's not just a feature; it's a whole new way to collaborate. Comments stay anchored to the exact sentence they reference, even as the text around them evolves. And the best part? It's available today on every plan, completely free. Let that sink in.

**After:**
> Shared drafts are out today. For months our own team passed around files named final_v7.docx, and we got sick of it. Now two people can edit the same doc at once and see each other's changes as they type. Comments stay attached to the sentence they're about, even when the text around it changes. It's free on every plan.

In a blind test, judges preferred Humanizer's rewrite over the original AI text 16 times out of 16 ([#229](https://github.com/blader/humanizer/issues/229)).

The original skill edits for human readers and does not target detectors. This fork keeps that aim and adds measurement: how much of your wording changed, whether the text fits its register, and whether every fact survived. No detector score is a guarantee, and detectors change often.

## The five strongest tells

These are the most common signs of AI writing, and Humanizer rewrites any of them on sight:

1. **Not X but Y:** "It's not just a feature, it's a shift."
2. **One-line closers:** "Let that sink in."
3. **Sayings that sound deep:** "At its core, what really matters is..."
4. **A staged run-up:** "Here's the thing." "Honestly?"
5. **Arguing with no one:** "I'm not saying X, but..."

Humanizer checks for [26 patterns](#the-26-patterns) in all.

## Installation

Once installed, run it with `/humanizer`.

### Claude Code

```text
/plugin marketplace add Sanidhya77/Humanizer
/plugin install humanizer@humanizer
```

The plugin needs Claude Code 2.1.142 or newer; on older versions, use `npx skills add Sanidhya77/Humanizer --global --agent claude-code`.

### Codex

```bash
npx skills add Sanidhya77/Humanizer --global --agent codex
```

### pi

```bash
pi install git:github.com/Sanidhya77/Humanizer
```

Add `-l` to install it only in the current project. `pi update --extensions` pulls new versions.

### Claude.ai and Claude Desktop

Download this repository as a ZIP (**Code → Download ZIP**) and upload it as a skill in Settings.

### Other agents

```bash
npx skills add Sanidhya77/Humanizer --global --agent '*'
```

This installs Humanizer for every agent the Skills CLI supports, including Gemini CLI, GitHub Copilot, and Windsurf. Leave off `--global` in any command above to install it only in the current project. For an agent the Skills CLI does not know, copy `SKILL.md` into its skill folder.

## Usage

Call the skill directly:

```
/humanizer

[paste your text here]
```

Or ask in plain language:

```
Please humanize this text: [your text]
```

To rewrite a file, give Humanizer its path:

```
Humanize the prose in docs/launch-post.md
```

Humanizer reads the current file in full before editing, including files it wrote earlier in the session. Its summary states how many sections it reviewed and identifies any it could not cover.

### Match your voice

If you want the rewrite to sound more like you, include a sample:

```
/humanizer

Here's a sample of my writing for voice matching:
[paste 2-3 paragraphs of your own writing]

Now humanize this text:
[paste AI text to humanize]
```

Humanizer follows the sample's rhythm, word choice, punctuation, and deliberate quirks, including dashes if you use them.

## How it works

A language model writes whatever is most likely to come next, so by default it makes the choice that fits the widest range of readers and subjects. A person chooses for one reader and one subject. Every tell Humanizer looks for is a form of that default choice: a sentence that signals importance instead of adding a fact, rhythm or formatting applied by rule, an ordinary fact dressed as a pivotal one, text left over from the chat, or a reply that re-explains what the reader already knows.

> "LLMs use statistical algorithms to guess what should come next. The result tends toward the most statistically likely result that applies to the widest variety of cases."
> Wikipedia, ["Signs of AI writing"](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)

Humanizer marks every tell it finds, strongest first. It drafts a rewrite and may merge, split, or reorder sentences and paragraphs, then checks the draft against the patterns and the original claims and writes the final version. Where the text is generic, it adds a specific detail it knows to be true, and it keeps every claim the original made.

When you paste text, Humanizer shows its work: the first rewrite, a short critique of anything that still sounds artificial, and the final version. Point it at a file and it changes only the prose, leaving code, data, frontmatter, and link targets alone. Personal writing keeps the writer's opinions and quirks. Technical and reference prose stays neutral and plain.

## The 26 patterns

Humanizer numbers the patterns from strongest and most common to weakest. It edits any of the first five the first time it sees one, and acts on a pattern marked *weak alone* only when several tells share a passage, because a careful writer may use any one of them on purpose.

### A. Staging instead of stating

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 1 | **Not X but Y** | "It's not just X, it's Y", "This doesn't mean X. It means Y." | State the point directly |
| 2 | **One-line closers and dramatic fragments** | "That is the real win." after every section; "This shows the importance of..." after an example; "No prior. No nostalgia." | Cut the closer that repeats or explains the example; merge fragments into a specific claim |
| 3 | **Sayings that sound deep** | "At its core, what matters is...", "Symmetry is the language of trust" | Replace the saying with the specific claim |
| 4 | **Staged run-up before the point** | "Let's dive in", "Honestly? It depends..." | Remove the run-up and state the point |
| 5 | **Arguing with no one** | "This isn't mainly about...", "A tempting approach would be..." | Remove the unraised objection or fake option; keep any real claim |

### B. Rhythm by rule

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 6 | **Forced triads** | "innovation, inspiration, and insights"; three examples plus a lesson | Use the number of items the meaning needs |
| 7 | **Repeated sentence openings** | "She noted... She noted... She filed..." | Merge the sentences or change the subject |
| 8 | **Dashes as the universal connector** (*weak alone*) | "institutions—not the people—yet this continues—" | Use periods, commas, colons, or parentheses; match a sample that uses dashes |
| 9 | **Stacked qualifiers** (*weak alone*) | "could potentially possibly be argued" | Keep only qualifiers the source supports |
| 10 | **Hyphenated pairs everywhere** (*weak alone*) | "the report is high-quality" | Keep the hyphen before the noun or where the dictionary has one |
| 11 | **Passive voice and missing subjects** (*weak alone*) | "No configuration file needed" | Name the actor when that helps |

### C. Inflation and borrowed authority

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 12 | **Overused AI words** | "delve... testament... landscape... showcasing" | Use plain words |
| 13 | **Inflated significance** | "marking a pivotal moment", "Despite challenges... continues to thrive", "The future looks bright" | Keep the fact and drop the significance; end on the last concrete fact |
| 14 | **Vague connection or association** | "associated with the leadership of", "in connection with" | Name the relationship if you know it |
| 15 | **Shallow -ing phrases** | "symbolizing... reflecting... showcasing..." | Keep only what the source supports |
| 16 | **Sales language** | "nestled within the breathtaking region" | State what the thing is |
| 17 | **Borrowed authority** | "Experts believe...", "cited in NYT, BBC, FT, and The Hindu" | Name a real source and what it said, or remove the claim or list |
| 18 | **Avoiding is, are, and has** | "serves as... features... boasts" | "is... has" |

### D. Formatting by rule

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 19 | **Bold as decoration** | "**OKRs**, **KPIs**"; "**Performance:** Performance improved" | Remove the bold; turn a labeled list into prose |
| 20 | **Decorative headings** | "Strategic Negotiations And Partnerships", "🚀 Launch Phase:", "The decision, on one screen" | Sentence case; remove emojis and arrows; name what the section holds |
| 21 | **Curly quotation marks** (*weak alone*) | `said “the project”` | `said "the project"` |

### E. Leftovers from the chat and the draft

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 22 | **Chatbot residue** | "Great question! ... I hope this helps!" | Remove the wrapper and keep the content |
| 23 | **Knowledge-limit disclaimers and guesses** | "While details are limited in available sources, it appears..." | State what the source shows, or remove the sentence |
| 24 | **A heading repeated in the first sentence** | "## Performance" + "Speed matters." | Let the heading do the work |
| 25 | **Writing about the document instead of its subject** | "This function was added to replace...", "compiled from...", "The table below compares..." | Describe the subject; state a convention only when the reader cannot see it |

### F. Writing for the wrong reader

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 26 | **Re-explaining what the reader knows** | A reply that walks the diagnosis and proves the plan works before the decision | Lead with the decision; leave the diagnosis and the proof for the ticket that follows |

## Full example

**Before (AI-sounding):**
> I recently spent five unforgettable days in Lisbon last October, and let me tell you — this city completely stole my heart. From the moment I checked into my charming hotel perched high in the historic Alfama district, I knew I was somewhere truly special.
>
> Yes, the famous hills are challenging — with countless stairs between my hotel and everything else, my legs certainly felt it! — but every climb rewards you with breathtaking, panoramic views that make it all worthwhile.
>
> No trip would be complete without riding the iconic Tram 28, a roughly forty-minute journey shared with plenty of fellow travelers eager to capture the magic. And the food? Simply divine. While the pastéis de nata at Pastéis de Belém are a beloved national treasure, my absolute favorite came from a hidden gem in Graça, still warm from the oven.
>
> But what truly makes Lisbon special isn't just the sights — it's the feeling. Wander just a block or two above the main squares and you'll discover a quieter, more authentic side of the city, inviting you to slow down and savor every moment.
>
> Of course, the must-see São Jorge Castle offers stunning views over the rooftops below. The queues can be long, but the experience is absolutely worth it for any history buff or curious traveler.
>
> Would I go back? Absolutely — next time in spring, and with better shoes! Lisbon isn't just a place to visit; it's a place to fall in love with, again and again. ✨

**After:**
> I spent five days in Lisbon last October. My hotel was up in Alfama, with a lot of stairs between it and everything else. My legs felt every one of them, but the views from the top made up for it.
>
> Everyone tells you to ride Tram 28, so I did. It took about forty minutes, and most of the car was other tourists taking pictures out the windows.
>
> The custard tarts at Pastéis de Belém are the famous ones. The best one I had came from a place in Graça, still warm from the oven.
>
> The part of Lisbon I liked most starts a block or two above the main squares, where the streets go quiet and nobody is in a hurry. São Jorge Castle has good views over the rooftops and a long queue to get them.
>
> I'd go back, in spring next time, and with better shoes.

## Sources

- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) is the source for the pattern list.
- [WikiProject AI Cleanup](https://en.wikipedia.org/wiki/Wikipedia:WikiProject_AI_Cleanup) maintains the page.

## Version history

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT

If Humanizer helps you, a star helps other people find it.
