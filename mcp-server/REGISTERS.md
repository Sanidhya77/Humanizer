# Registers: where the numbers come from

A **register** is what normal writing looks like for one kind of text: a bachelor
thesis in computer science, a PhD thesis in sociology, a LinkedIn post. Each
register stores **ranges** (low–high) for measurable features, not single
targets. Real writers vary, and pushing every text onto one number is what makes
"humanized" text read strangely.

`check_voice` applies two layers:

1. **Register.** Anything outside the register's range is a real problem for that genre (`must_fix`, `ai_patterns`).
2. **Personal voice.** The writer's own habits, learned from their texts, steer the draft *inside* the register's range (`voice_nudges`). Habits the register rules out are listed in `not_applied` and never used. Examples: contractions from a blog going into a paper, or "you" going into a thesis.

Voice strength: `off`, `light` (register only; default for academic), `medium`
(default for blogs), `strong`. Punctuation habits (parentheses, colons,
semicolons, dashes) are only ever reduced toward the writer's rate, never added,
because they come from content like citations and units.

## Registers

**Academic** = level × domain, with an optional section.

| Levels | Domains | Sections |
|---|---|---|
| high_school, undergraduate, masters, phd, published | cs_engineering, natural_sciences, life_health, social_sciences, business, humanities | abstract, introduction, literature, methods, results, discussion, conclusion |

Example: `academic:phd:social_sciences`, section `methods`.

**Platforms:** blog_personal, blog_technical, blog_company, academic_blog, linkedin, x_thread, newsletter, forum_post.

**Custom:** `scripts/fetch_corpus.py` downloads human-written texts (from the arXiv API, or from a CSV of links) and cleans them, then `scripts/build_register.py NAME FOLDER` measures a folder of real texts
and makes a register from the 10th–90th percentiles. Use it for fields or
platforms not covered here, or to replace a preset with your department's theses.

## Evidence used

Automatic counts with word lists differ from hand-coded corpus studies, so the
presets use the studies for **direction and ratios**, anchored on real texts
measured with this tool (a CS bachelor thesis and a CS journal article, both
human-written, 2026).

| Finding | Used for | Source |
|---|---|---|
| Hedges are the most frequent stance feature in research articles, 14.5 per 1,000 words, and soft fields use 75% more stance and engagement markers than hard fields | Hedge ranges, soft vs hard domains | Hyland (2008), summarised in [Dobakhti](https://files.eric.ed.gov/fulltext/EJ1026107.pdf) |
| Philosophy, marketing, applied linguistics and sociology account for over 70% of hedges, more than twice as common as in engineering and physics | Domain shifts | Hyland (1998), summarised in [Akman & Karahan 2023](https://dergipark.org.tr/en/download/article-file/2959762) |
| First-year university writers over-use intensifying boosters compared with advanced writers; hedges and contrast connectors mark development | high_school and undergraduate shifts | [Aull & Lancaster 2014](https://peeref.com/works/55621580), summarised in [Afzaal et al. 2025](https://public-pages-files-2025.frontiersin.org/journals/education/articles/10.3389/feduc.2025.1589004/pdf) |
| PhD theses carry more metadiscourse than master's theses (35% more when normed for length); hedges dominate in both | masters and phd shifts | Hyland & Tse (2004), summarised in [Springer chapter](https://springerlink.bibliotecabuap.elogim.com/10.1007/978-3-031-04895-1_5) |
| Research-article sentences average about 24.9 words (SD 11.6) | Sentence-length ranges | Gray (2011), cited in [Lu et al.](https://pdf.arxiv.org/pdf/1907.11843) |
| Education research articles average 24.7 words per sentence, longer in literature reviews and discussions | Sentence length, section shifts | [Linguistics Journal study](https://bvbvf1.bib-bvb.de/vufind/PrimoRecord/cdi_proquest_journals_2303817857/Details) |
| Median paragraph is 109 words; most fall between 65 and 167 (9,830 PubMed Central papers) | Paragraph ranges | [Quantifying Health](https://quantifyinghealth.com/paragraph-length-in-research-papers/) |
| About 30% of clauses in science articles are passive (60 articles, six journals); roughly 29% of all passives sit in the methods section, more than any other section. Verified against the paper | Passive ranges, methods shift | [Alvin 2014, JCOM](https://arc.ucr.edu/media/1196/download) |
| Passive is much higher in methods than in introductions and discussions, and lowest in social sciences | Section and domain shifts | Martinez (2001), table in [course notes](https://is.muni.cz/el/fi/jaro2018/VV070/um/63343868/language_charts.pdf?lang=en) |
| Self-mention varies by field: "we" is common in physics and electronic engineering, rare in mechanical engineering; "I" appears in applied linguistics and sociology | First-person ranges | Hyland (2001), same table |
| Instruction-tuned LLMs use present participial clauses at 2–5× and nominalizations at 1.5–2× the human rate; GPT-4o (not the Llama base models) uses the agentless passive at about half the human rate. Verified against the arXiv version | `participle_clauses_per_1k` and `nominalizations_per_1k` ceilings | [Reinhart et al., PNAS 2025](https://arxiv.org/abs/2410.16107) |
| "delves", "showcasing" and "underscores" rose sharply in 2024 PubMed abstracts | Strong AI-word list | [Kobak et al.](https://arxiv.org/pdf/2406.07016) |
| "realm", "intricate", "showcasing" and "pivotal" surged in arXiv CS abstracts after 2023 | Strong AI-word list | [Liang et al. 2024](https://arxiv.org/pdf/2404.01268.pdf) |
| Academic blogs are a hybrid between research articles and journalism, with more reader engagement | academic_blog register | [Zou & Hyland 2019](https://ueaeprints.uea.ac.uk/id/eprint/71877/1/Recontextualising_Discourses_Zou_Hyland_final_copy.pdf) |
| LinkedIn readability guidance: keep average sentences near 14–18 words | linkedin register (soft guidance) | [AI Carousels guide](https://www.aicarousels.com/free-tools/linkedin-post-readability-score-checker) |

Platform ranges (blogs, social) rest on practitioner data and on measuring real
posts, so they are looser than the academic ones. They are the best candidates
for replacing with `build_register.py` on posts you trust.

## Limits

- Word-list counts miss context. "Clear" in "clear the cache" counts as a booster. Ranges are wide enough to absorb that noise.
- Some AI-favoured words are real terms in some fields ("benchmark harness", "robust estimator"), so they sit on the soft list and only matter at high rates.
- Registers describe typical writing. A good writer can break a range on purpose; that is why nudges are optional and the rewrite rule says never to force one.

## Measured registers (shipped with the package)

These 34 registers were measured from real texts written **before ChatGPT
(November 2022)**, most of them from 2015–2019. Each was screened with the
detector, and suspect texts were dropped. Only statistics are shipped, in
`src/humanizer_mcp/measured/*.json`: feature ranges plus the list of source
file names. No text is included.

A measured register replaces the estimated preset with the same name. A
level/domain combination with no measured data (for example
`academic:high_school:cs_engineering`) falls back to the estimated preset
described above. Sections (`methods`, `discussion`, ...) still shift
measured academic registers.

Range rule: p10–p90 when there are 20 or more texts, otherwise min–max.
Both are padded 10%. Paragraph length, nominalizations and participle
clauses are widened to include the preset, so normal human text is not
flagged.

| Register | Texts | Sentence length (words) | Sources |
|---|---|---|---|
| `academic:high_school:humanities` | 9 | 17–33 | JASNA high school essay contest winners 2016–18 |
| `academic:high_school:natural_sciences` | 6 | 19–24 | Journal of Emerging Investigators (high school research) |
| `academic:high_school:social_sciences` | 9 | 12–39 | NYT Learning Network editorial contest winners 2016 |
| `academic:undergraduate:business` | 8 | 16–27 | bachelor theses (Finnish/Dutch university repositories) |
| `academic:undergraduate:cs_engineering` | 11 | 15–24 | bachelor theses (Twente, TalTech, ZČU, others) |
| `academic:undergraduate:humanities` | 6 | 18–31 | bachelor theses (Aalto, Tufts, Lund) |
| `academic:undergraduate:life_health` | 12 | 18–27 | bachelor theses (Tufts, Twente, Groningen, Lund) |
| `academic:undergraduate:natural_sciences` | 12 | 15–33 | bachelor theses (Tufts, Twente, Groningen, Lund) |
| `academic:undergraduate:social_sciences` | 13 | 19–33 | bachelor theses (Tufts, Twente, Lund, Waterloo) |
| `academic:masters:business` | 7 | 19–26 | master's theses (Aalto, Twente, LUT, Vaasa) |
| `academic:masters:cs_engineering` | 7 | 18–26 | master's theses (Aalto, Twente, Chalmers, Lund) |
| `academic:masters:humanities` | 15 | 17–37 | master's theses (Waterloo, Aalto, Tufts, Edinburgh) |
| `academic:masters:life_health` | 16 | 17–32 | master's theses (Tufts, Edinburgh, Twente, Lund) |
| `academic:masters:natural_sciences` | 15 | 18–32 | master's theses (Aalto, Tufts, Waterloo, Cambridge) |
| `academic:masters:social_sciences` | 19 | 15–37 | master's theses (Tufts, Edinburgh, Twente, Lund) |
| `academic:phd:business` | 14 | 13–32 | PhD theses (Aalto, Cambridge, Edinburgh, Twente) |
| `academic:phd:cs_engineering` | 8 | 19–26 | PhD theses (Edinburgh, Chalmers, Cambridge) |
| `academic:phd:humanities` | 15 | 19–39 | PhD theses (Cambridge, Tufts, Edinburgh, Twente) |
| `academic:phd:life_health` | 14 | 14–38 | PhD theses (Cambridge, Tufts, Edinburgh, Waterloo) |
| `academic:phd:natural_sciences` | 14 | 18–31 | PhD theses (Cambridge, Edinburgh, Chalmers, Twente) |
| `academic:phd:social_sciences` | 15 | 22–31 | PhD theses (Tufts, Edinburgh, Twente, Waterloo) |
| `academic:published:business` | 21 | 21–29 | open-access articles (OpenAlex, Springer, M@n@gement, PLOS, SciELO) |
| `academic:published:cs_engineering` | 32 | 18–28 | arXiv papers |
| `academic:published:economics` | 15 | 13–34 | arXiv econ papers |
| `academic:published:humanities` | 10 | 21–33 | open-access articles via OpenAlex (mostly linguistics/education) |
| `academic:published:life_health` | 12 | 18–37 | PLOS articles |
| `academic:published:natural_sciences` | 16 | 17–30 | PLOS articles |
| `academic:published:social_sciences` | 16 | 19–27 | PLOS articles |
| `blog_personal` | 9 | 12–26 | personal blogs 2017–19 (Cal Newport, Legal Nomads, Nathan Barry, ...) |
| `blog_company` | 11 | 13–35 | company blogs 2017–19 (Buffer, Shopify, Atlassian, Dropbox, ...) |
| `blog_technical` | 9 | 10–23 | engineering blogs (Cloudflare, Julia Evans, Martin Fowler, GitHub) |
| `academic_blog` | 8 | 14–32 | Brookings, Behavioral Scientist, Crooked Timber, UCL IOE, World Bank |
| `newsletter` | 8 | 13–25 | public newsletter archives 2019 (Garbage Day, Not Boring, HEATED, ...) |
| `forum_post` | 14 | 11–30 | Stack Exchange answers (academia, workplace, writers, history, SE) |

`linkedin` and the other social platforms stay as estimates: posts from
after 2019 are too mixed with AI-assisted writing to measure as "human".
