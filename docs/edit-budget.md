# The edit budget: evidence and limits

Humanizer edits a writer's own draft inside a budget: at most 12% (`light`) or 20% (`normal`) of the characters in a paragraph may be reworded, and no sentence may be rebuilt. This page explains where those numbers come from and how far to trust them.

Short version: a small test, one writer, one detector, one day. The pattern was clear. The exact thresholds are not.

## The test (14 November 2026)

**Material.** Three short drafts (about 100, 200 and 330 words), typed by one writer with no grammar tool. Rough English, many typing errors.

**Versions of each draft.**

| Version | What was done | Who did it |
|---|---|---|
| raw | Nothing | writer |
| light | Spelling, grammar and punctuation fixed. Words and order kept. | Claude |
| middle | About half the sentences reworded in place. No sentence rebuilt. | Claude |
| heavy | Sentences rebuilt for clarity. Same facts. | Claude |
| inserted | A new AI-written draft on the same topic, with 3 or 4 of the writer's own sentences placed in it unchanged. | Claude + writer |

**Detector.** GPTZero, free plan, "Model 5.0b", one scan per text. The free plan shows the class (Human, Mixed, AI) and three percentages. It did not show sentence highlights or the "AI Polished" tag.

**Measurement.** `measure_change(raw, version)` from this repo. `changed_pct` is the share of characters reworded after spelling fixes are set aside. `writer_words_pct` is the share of the final words that are the writer's own, in their own order.

## Results

| Draft | Version | `changed_pct` | `writer_words_pct` | Rebuilt sentences | GPTZero |
|---|---|---|---|---|---|
| 1 | raw | 0 | 100 | 0 | Human 100% |
| 1 | light | 6.4 | 91.7 | 0 | Human 100% |
| 1 | middle | 17.0 | 79.3 | 0 | Human 86%, AI 14% |
| 1 | heavy | 39.0 | 50.8 | 4 | **AI 100%** |
| 1 | inserted | 45.2 | 40.8 | 7 | **AI 94%**, Mixed 6% |
| 2 | raw | 0 | 100 | 0 | Human 100% |
| 2 | light | 7.4 | 88.3 | 0 | Human 100% |
| 2 | middle | 17.0 | 81.1 | 0 | Human 100% |
| 2 | heavy | 41.2 | 34.3 | 5 | **AI 100%** |
| 2 | inserted | 45.1 | 36.4 | 5 | **Mixed 100%** |
| 3 | raw | 0 | 100 | 0 | Human 100% |
| 3 | light | 11.3 | 83.4 | 0 | Human 100% |
| 3 | middle | 20.5 | 74.6 | 0 | Human 100% |
| 3 | heavy | 36.3 | 51.2 | 5 | **AI 100%** |
| 3 | inserted | 53.9 | 42.2 | 7 | **Mixed 100%** |

## What the test shows

1. **The amount of rewording decided the label.** The facts and the paragraph order were the same in the light, middle and heavy versions. Up to 20.5% reworded, all six edited texts were classed Human. From 36.3%, all three were classed AI.

2. **Rebuilt sentences separate the two groups cleanly.** Every text classed Human had zero rebuilt sentences. Every heavy version had four or five. In this data that is a sharper line than the percentage.

3. **The first warning came at 17%.** Draft 1's middle version was the only edited text with a non-zero AI share (14%).

4. **Nothing was tested between 20.5% and 36.3%.** The point where the label flips is somewhere in that gap.

5. **Typed-in sentences moved an AI draft to "Mixed" in two of three cases.** With 36% and 42% of the words being the writer's, the text was classed Mixed. With 41% it stayed AI. Three texts cannot say how much is enough.

## How the budgets were set

| Setting | Value | Reason |
|---|---|---|
| `light` | 12% per paragraph | The three light versions measured 6.4 to 11.3%. A correction pass on a rough draft fits. |
| `normal` | 20% per paragraph | The highest level that was tested and stayed Human (17.0, 17.0, 20.5%). |
| `heavy` zone | 30% and more | Below the lowest AI result (36.3%), inside the untested gap. |
| Rebuilt sentences | none | See point 2. `ok` is false as soon as one sentence is rebuilt. |

The budget applies per paragraph, because a document at 15% on average can hide a few fully rewritten paragraphs. Paragraphs under 25 words are measured but not held to it.

## Why spelling fixes are set aside

Fixing "teh" to "the" changes a whole word but none of the writer's choices. On these drafts, spelling fixes alone changed 25 to 40% of the words. A budget in plain word counts would be used up before any editing started. So `measure_change` first finds the corrections (small edit distance, split or joined words), applies them to the original, and measures what is left.

A changed number is never treated as a correction.

## What other work says

- **GPTZero's own description of "AI Polished".** GPTZero built that class from human texts that an LLM was asked to polish or rewrite, and kept only samples inside an edit-distance window. Samples too close to the original looked like the Human class, and samples too far looked like the AI class. That is the same shape as the results above. Source: [Behind the Scenes: Introducing "AI Polished"](https://gptzero.me/news/behind-the-scenes-introducing-lightly-edited-by-ai/).
- **GPTZero technical report (2026).** Of 4,631 polished texts, about 90% were labelled Polished. The ones mislabelled as plain AI were those that differed most from the human original. Source: [arXiv:2602.13042](https://arxiv.org/abs/2602.13042).
- **Saha and Feizi (2025), "Almost AI, Almost Human".** Eleven detectors on 11.7K human texts polished to different degrees. Many detectors flagged even minimal polishing, and did not separate minor from major polishing well. This is the main reason not to read the budget as a guarantee: the kind of change matters, not only its size. A polish that swaps plain words for "better" ones can be flagged at a small percentage. Source: [arXiv:2502.15666](https://arxiv.org/abs/2502.15666).
- **DAMAGE (2025).** A humanizer fine-tuned against a detector was still detected 93% of the time. Rewriting AI text does not make it read as human-written to a current detector. Source: [ACL Anthology](https://aclanthology.org/2025.genaidetect-1.9.pdf).

## Limits

- One writer, three drafts, one scan each. Enough to see a pattern, not to fix a threshold.
- One detector version on one day. GPTZero changes its model often. Turnitin, Originality and others were not tested.
- The raw drafts are full of typing errors, which may help them read as human. The light and middle versions are the fairer comparison, and they also stayed Human.
- All edits were made by one model (Claude). Another editor may leave different traces at the same percentage.
- The texts are informal. Academic prose was not tested.
- The test measures a detector, not readers. Whether a text reads well is a separate question, and the more important one.

## What this means for use

- If you wrote the draft, a light edit keeps it yours, on the page and to the detector tested here.
- If a model wrote the draft, no amount of editing by a model makes it human-written. Adding what only you know (your example, your measurement, your opinion, in your words) changes what the text is. Where disclosure is expected, describe the text as what it is.
- Re-run the test before quoting these numbers anywhere. `measure_change` gives the left-hand columns for any pair of texts.
