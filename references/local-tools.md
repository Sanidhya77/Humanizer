# Using the Humanizer local tools

Read this when the Humanizer MCP tools are connected. It is the working loop for `SKILL.md`.

The tools measure. You edit. No tool here predicts what GPTZero, Turnitin or any other commercial detector will say, so never tell the user a text "will pass".

## 1. Before you edit

Settle three things. Ask the user if you cannot tell.

**Whose words are these?**

- The writer typed the draft themselves, however rough. Use the *own draft* loop below.
- A model drafted it. Use the *AI-written draft* section instead.

**Which register?** Call `list_registers` if unsure and `get_register` to read its guide. For a long academic text, check sections separately (`section="methods"`, ...).

**How much may change?**

| Mode | Budget per paragraph | What you may do |
|---|---|---|
| `light` | 12% | Fix spelling, grammar and punctuation. Nothing else. |
| `normal` (default) | 20% | Also remove AI patterns and fix unclear phrasing, inside the writer's own sentences. |

The budget counts rewording only. Spelling and typing fixes are free: `measure_change` sets them aside. Raise the budget with `budget_pct` only when the user asks for a heavier edit, and tell them what the test in `docs/edit-budget.md` found.

## 2. The own-draft loop

1. **Load.** `read_document(path)` for .txt and .md. `read_docx_paragraphs(path)` for .docx, which also gives the paragraph indexes you need later. If the user names a voice profile, call `get_voice_profile`.

2. **Measure the original.** `check_voice(original, register=...)` so the report can show the register fit before and after.

3. **Edit.** Work inside the writer's sentences:
   - Fix errors.
   - Remove a pattern from `SKILL.md` only where it appears, with the smallest change that removes it.
   - Leave every sentence that has no problem exactly as it is.
   - Do not merge, split or reorder sentences or paragraphs. One paragraph in, one paragraph out.
   - Do not swap a plain word for a better one.

4. **Measure the change.** `measure_change(original, edit, mode=...)`. For long documents pass `original_path` and `rewrite_path`.
   - `ok: true`: continue.
   - `paragraphs_over_budget`: go back to the writer's wording in those paragraphs and re-apply only the fixes that are needed.
   - `rebuilt_sentences`: put the writer's original sentence back, fix only its errors, and keep your rebuilt version for the suggestions list in step 9.
   - `sentence_count.joined_or_split`: for a writer's own draft, put their sentence boundaries back unless the register check requires longer or shorter sentences. If it does, say in the report how many sentences were joined.
   - `word_swaps`: undo every swap that does not fix an error or remove a pattern. The writer's word was a choice.
   - `style_drift.flags`: each one names a habit of the writer that the edit removed, or a model habit it added. Put the writer's version back.
   - Run it again. Two rounds are enough. If a paragraph is still over budget, say so in the report instead of pushing on.

5. **Check the register.** `check_voice(edit, register=..., profile_name=...)`.
   - Fix `must_fix` and `ai_patterns` items only where the fix fits in the budget. List the rest as suggestions.
   - The ranges are limits, not targets. A text inside them is done. Do not lengthen sentences or add passives to raise `register_fit`.
   - Apply `voice_nudges` only where they read naturally. Never apply anything in `not_applied`.
   - With a profile, the edit should not sit further from the writer's voice than the original did. `compare_to_voice` on both shows that.

6. **Check the meaning.** `check_meaning(original, edit)`. Restore any missing number, citation, link or quote. Remove anything invented.

7. **Check the quality.** `check_quality(original, edit)`. Fix every item in `hard_issues`. For each item in `worth_a_look`, prefer the writer's original wording.

8. **Save.**
   - Text: `save_output(text, title, original=..., report=...)`.
   - .docx: `rewrite_docx(path, {index: new text})` with only the paragraphs you changed. It saves a copy and keeps styles, headings, tables and layout. Tell the user about every entry in `skipped` and `check_formatting`.
   - Put in the report: the `measure_change` result, register fit before and after, and the meaning and quality checks.

9. **Tell the user**, in a few lines:
   - how much changed (`changed_pct`) and how much is still their own wording (`writer_words_pct`)
   - that `changes.html` in the job folder shows every edit, marked
   - the suggestions: sentences you would rewrite, each with its reason, for them to accept or redo in their own words
   - anything you could not fix inside the budget

## 3. The AI-use statement

When the text is for a university, a journal or a client, or the user asks what they have to declare, call `ai_use_statement(original, edit)`.

- Give the user the `statement`, the `level_label` and the `usually` line.
- Say what the statement covers: the edit between the two texts. If the user's original was itself drafted with AI, the statement must say so. Ask if you do not know.
- Rules differ between venues. Tell the user to read theirs, and to put in the real tool name and version.
- Never present the statement, or `changes.html`, as proof that a text is human-written. They record what the edit did.

## 4. AI-written drafts

Run the full process in `SKILL.md` ("How to work"). Be straight with the user about what it does: it removes the patterns that make the text read badly. It does not make the text human-written, and detectors are trained on rewritten AI text.

What does change the text is content only the writer has:

1. Call `find_generic(text)`. `ask_about` lists the paragraphs with the least in them: no numbers, names, examples, first-hand detail or stated opinion. Read them yourself before asking; the score is a count, and a low score does not mean a model wrote the paragraph.
2. Ask one specific question per paragraph, no more than `questions_allowed` (one per 300 words, between three and eight). Send them all in one message. Quote the first few words of each paragraph so the writer can find it.
   - Good: "You say CRM adoption fails in small firms. Did you see that happen anywhere?"
   - Bad: "Can you add an example here?"
3. Each question can be answered, skipped, or answered with "cut". A skipped paragraph stays as it is. Rough answers in any language are fine.
4. Put the answer into the paragraph almost word for word. Fix its errors and join it to the sentences around it. Do not re-compose it.
5. Never invent an answer.
6. Run `check_meaning(original, rewrite, also_allowed=<the writer's answers>)` so their new facts are not reported as invented.
7. Run `check_quality(original, rewrite)`.
8. Report `writer_words_pct` from `measure_change(<their answers and typed text>, rewrite)` if they ask how much of the text is theirs.

A text that is partly theirs and partly a model's is a mixed text. That is the accurate description of it, and the user should describe it that way where disclosure is expected (a university, a client, a journal).

## 5. The local detector

`score_text` is optional. It is a small language model that marks passages that read as predictable. Use it on 100 words or more to find passages worth a second look.

- It does not predict any commercial detector.
- A high score on a sentence is not a reason to reword it. If the sentence has no error and no pattern from `SKILL.md`, leave it.

## 6. What the numbers mean

| Field | Meaning |
|---|---|
| `changed_pct` | Share of characters reworded, after spelling fixes are set aside. |
| `writer_words_pct` | Share of the final words that are the writer's own, in their own order. |
| `corrections` | Spelling and typing fixes. They do not count against the budget. |
| `sentences.kept` | At least 85% of the sentence is the writer's wording. |
| `sentences.edited` | 50 to 85%. |
| `sentences.rebuilt` | Under 50%. The sentence is now yours, not theirs. |
| `zone` | `within_budget`, `over_budget`, or `heavy` (30% and more). |
| `sentence_count` | Sentences in the original and in the edit, and whether they were joined or split (a change of 10% or more). Joining keeps the words, so `changed_pct` barely moves; this field shows it. |
| `word_swaps` | One word replaced by one different word ("use -> leverage"). |
| `style_drift.flags` | Habits of the writer the edit removed, or model habits it added: overused words, dashes, written-out contractions, removed pronouns or opinions, added hedging, abstract nouns, longer words. Notes, not a pass or fail. |
| `style_drift.before_after` | Counts in the original and in the edit: contractions, first-person words, pronouns, hedging words, stated opinions, abstract nouns, average word length. |

Where the budgets come from, and how far to trust them: `docs/edit-budget.md`.
