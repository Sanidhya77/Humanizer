"""Tests that need no model download. Run: pytest mcp-server/tests"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from humanizer_mcp.change import measure_change  # noqa: E402
from humanizer_mcp.meaning import check_meaning  # noqa: E402
from humanizer_mcp.text_utils import sentences  # noqa: E402
from humanizer_mcp import voice  # noqa: E402

ORIGINAL = (
    'Smith et al. (2021) found that response times fell by 23.5% after caching was added '
    '[4]. The study covered 1,200 requests across 3 regions (Lee & Park, 2019; Chen, 2020). '
    'As one engineer put it, "the cache did more than the rewrite ever could." '
    "See https://example.org/report and doi 10.1145/3368089.3409741 for details. AWS and GCP were tested."
)


def test_sentences_handle_abbreviations_and_decimals():
    s = [x.text for x in sentences("Dr. Lee et al. measured 3.5 ms (Fig. 2). It rose! Why?\n## Title\nNext.")]
    assert s == ["Dr. Lee et al. measured 3.5 ms (Fig. 2).", "It rose!", "Why?", "## Title", "Next."]


def test_meaning_ok_when_facts_kept():
    rewrite = (
        "Response times dropped 23.5% once caching went in, according to Smith et al. (2021) [4]. "
        "They looked at 1200 requests in 3 regions (Lee & Park, 2019; Chen, 2020). One engineer said "
        '"the cache did more than the rewrite ever could." Details: https://example.org/report, '
        "10.1145/3368089.3409741. AWS and GCP were both tested."
    )
    r = check_meaning(ORIGINAL, rewrite)
    assert r["ok"], r


def test_meaning_catches_drops_and_inventions():
    rewrite = (
        "Response times dropped about 25% once caching went in, according to Smith et al. (2021). "
        "They looked at many requests across 3 regions (Lee & Park, 2019). AWS was tested."
    )
    r = check_meaning(ORIGINAL, rewrite)
    assert not r["ok"]
    assert "23.5%" in r["missing_numbers"] and "1200" in r["missing_numbers"]
    assert "25%" in r["added_numbers"]
    assert "Chen, 2020" in r["missing_citations"] and "[4]" in r["missing_citations"]
    assert r["changed_quotes"] and r["missing_links"]
    assert "GCP" in r["names_to_check"]


def test_voice_profile_roundtrip(tmp_path):
    os.environ["HUMANIZER_HOME"] = str(tmp_path)
    sample = (
        "I've been testing caches for weeks. Most of them don't help. The one that did? Redis, "
        "set up badly at first, then fixed. I'll explain what changed and why it mattered to my "
        "side project, which gets maybe two hundred visitors a day on a good day.\n\n"
    ) * 12
    prof = voice.build_profile("Shivam Blog", [sample], register="blog_technical")
    path = voice.save_profile(prof)
    assert path.exists() and prof["name"] == "shivam-blog"
    assert voice.load_profile("shivam blog")["stats"]["contractions_per_1k"] > 15
    assert any("contraction" in g.lower() for g in prof["style_guide"])


def test_register_flags_ai_text_and_passes_human_text():
    ai = (
        "Artificial intelligence is not just a technological advancement; it is a fundamental shift in how we "
        "approach problem-solving. In today's rapidly evolving landscape, organizations are increasingly leveraging AI "
        "to streamline operations, enhance decision-making, and unlock new opportunities. Moreover, the integration of "
        "machine learning models into everyday workflows has proven to be a game-changer, enabling teams to focus on "
        "what truly matters. Ultimately, the future of AI depends on our ability to balance innovation with responsibility. "
        "By fostering collaboration between technologists, policymakers, and the broader community, we can ensure that "
        "AI serves as a powerful force for good."
    )
    r = voice.check_voice(ai, register="academic:undergraduate:cs_engineering")
    flagged = {m["feature"] for m in r["ai_patterns"]}
    assert {"participle_clauses_per_1k", "ai_words_strong_per_1k"} <= flagged
    assert r["register_fit"] < 70


def test_blog_habits_are_not_forced_into_academic_text(tmp_path):
    os.environ["HUMANIZER_HOME"] = str(tmp_path)
    blog = (
        "I'm not gonna lie, you'll love this. It's quick. You don't need much: a laptop, some coffee, and "
        "an afternoon. I tried it last week and honestly? It worked better than I'd hoped, which isn't something "
        "I say often about build tools.\n\n"
    ) * 10
    prof = voice.build_profile("me", [blog], register="blog_personal")
    draft = (
        "The benchmark compared four frameworks under identical load. Each configuration was run five times, "
        "and the median of the runs was reported. Throughput differed by less than 0.2% within each class, "
        "while memory use differed by a factor of ten between the classes.\n\n"
    ) * 6
    r = voice.check_voice(draft, register="academic:published:cs_engineering", profile=prof, strength="strong")
    nudged = {n["feature"] for n in r["voice_nudges"]}
    blocked = {n["feature"] for n in r["not_applied"]}
    # contractions / "you" from the blog must never be pushed into a paper
    assert "contractions_per_1k" in blocked and "you_your_per_1k" in blocked
    assert "contractions_per_1k" not in nudged and "you_your_per_1k" not in nudged
    # and the writer's heavy "I" is capped at what the register allows
    for n in r["voice_nudges"]:
        if n["feature"] == "i_me_my_per_1k":
            from humanizer_mcp import registers
            cap = registers.resolve("academic:published:cs_engineering")["ranges"]["i_me_my_per_1k"][1]
            assert n["writer_target"] <= cap


def test_private_profile_keeps_no_text(tmp_path):
    os.environ["HUMANIZER_HOME"] = str(tmp_path)
    secret = ("Acme's new Orion router ships in March with a 40% faster chip and our quieter fan. " * 40)
    prof = voice.build_profile("client", [secret], private=True)
    dumped = str(prof)
    assert "Orion" not in dumped and "Acme" not in dumped
    assert prof["excerpts"] == [] and prof["favourite_words"] == []


def test_punctuation_is_never_added_to_match_voice():
    writer = ("The server (FastAPI, version 0.110) handled 1,200 requests (Table 3); see Section 4 (Methods). " * 30)
    prof = voice.build_profile("paren", [writer], register="academic:published:cs_engineering")
    draft = ("The server handled the requests well and the results were stable across runs. " * 30)
    r = voice.check_voice(draft, profile=prof, strength="strong")
    assert "parentheses_per_1k" not in {n["feature"] for n in r["voice_nudges"]}


def test_low_stance_is_optional_not_must_fix():
    plain = ("The server handled four hundred requests per second at twenty users. Memory stayed under one gigabyte. "
             "Latency rose at fifty users, and the worker pool saturated at one hundred. ") * 20
    r = voice.check_voice(plain, register="academic:published:cs_engineering")
    must = {m["feature"] for m in r["must_fix"]}
    assert "boosters_per_1k" not in must and "hedges_per_1k" not in must


def test_own_profile_in_same_register_widens_range(tmp_path):
    os.environ["HUMANIZER_HOME"] = str(tmp_path)
    long_sents = ("The framework was evaluated under sustained load across six concurrency levels, and the median "
                  "latency together with the throughput was recorded for every configuration in the experiment. ") * 30
    prof = voice.build_profile("me", [long_sents], register="academic:undergraduate:cs_engineering")
    without = voice.check_voice(long_sents, register="academic:undergraduate:cs_engineering")
    with_me = voice.check_voice(long_sents, register="academic:undergraduate:cs_engineering", profile=prof)
    assert "avg_sentence_words" in {m["feature"] for m in without["must_fix"]}
    assert "avg_sentence_words" not in {m["feature"] for m in with_me["must_fix"]}
    assert "avg_sentence_words" in with_me["widened_by_your_writing"]


def test_measured_registers_bundled(monkeypatch, tmp_path):
    monkeypatch.setenv("HUMANIZER_HOME", str(tmp_path))
    from humanizer_mcp import registers
    reg = registers.resolve("academic:masters:humanities")
    assert reg["kind"] == "measured" and "real texts" in reg["label"]
    # sections still shift measured academic registers
    assert registers.resolve("academic:published:cs_engineering", section="methods")["name"].endswith("@methods")
    # a combination with no measured data falls back to the estimated preset
    assert registers.resolve("academic:high_school:cs_engineering")["kind"] == "academic"
    # build_register's --like still gets the estimated preset
    assert registers.resolve("blog_personal", builtin=True)["kind"] == "platform"
    assert len(registers.list_all()["measured"]) >= 30


# --- edit budget (docs/edit-budget.md) -----------------------------------------

ROUGH = (
    "The reason i am building this tool is for my own need aswell, becuase i write blogs for someone and "
    "each time i have to find teh ai detector and the rewriter for that. This does not mean i write form ai. "
    "I do the resaerch and topic finidng and i choose what to write and what tone to give it. "
    "So i wanted somehting that can find the balance between teh writing quality and what the detectors say."
)


def test_spelling_fixes_do_not_use_the_edit_budget():
    fixed = (
        "The reason I am building this tool is for my own need as well, because I write blogs for someone and "
        "each time I have to find the AI detector and the rewriter for that. This does not mean I write from AI. "
        "I do the research and topic finding and I choose what to write and what tone to give it. "
        "So I wanted something that can find the balance between the writing quality and what the detectors say."
    )
    r = measure_change(ROUGH, fixed, mode="light")
    assert r["ok"], r
    assert r["changed_pct"] < 3 and r["corrections"] >= 8
    assert r["writer_words_pct"] > 95
    assert r["sentences"]["rebuilt"] == 0


def test_heavy_rewrite_is_flagged_with_its_rebuilt_sentences():
    rebuilt = (
        "I built this tool for myself, since blog work for a client means hunting for a detector and a rewriter "
        "every single time. AI does not do everything, though. Research, topics, content and tone are my decisions. "
        "My goal was a sensible trade-off between readable prose and detector results."
    )
    r = measure_change(ROUGH, rebuilt)
    assert not r["ok"] and r["zone"] == "heavy"
    assert r["paragraphs_over_budget"][0]["status"] == "heavy"
    assert r["sentences"]["rebuilt"] >= 2 and r["paragraphs_over_budget"][0]["rebuilt_sentences"]
    assert r["writer_words_pct"] < 50


def test_changed_number_is_never_a_spelling_fix():
    r = measure_change("We ran 12 trials over 3 days in the first lab.", "We ran 15 trials over 3 days in the first lab.")
    assert r["corrections"] == 0 and r["changed_pct"] > 0


def test_untouched_and_added_paragraphs_are_told_apart():
    a = "First paragraph stays exactly as the writer typed it, with all of its words in the same order as before.\n\n" \
        "Second paragraph also stays the same, because nothing in it needed any kind of fixing at all today."
    b = a + "\n\nA brand new closing paragraph that the writer never wrote, added by the editor at the very end of the text here."
    r = measure_change(a, b, detail=True)
    assert [p["status"] for p in r["paragraphs"]] == ["unchanged", "unchanged", "added"]
    assert r["sentences"]["new"] == 1 and not r["ok"]


def test_custom_budget_and_bad_mode():
    orig = "The server handled four hundred requests per second at twenty users, and memory stayed under one gigabyte for the whole run of the test."
    new = "The server handled four hundred requests per second with twenty users, and memory use stayed below one gigabyte for the whole run of the test."
    assert measure_change(orig, new, budget_pct=50)["ok"]
    assert not measure_change(orig, new, budget_pct=1)["ok"]
    try:
        measure_change(orig, new, mode="extreme")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown mode must be rejected")


def test_meaning_allows_what_the_writer_added():
    rewrite = ORIGINAL + " In my own project the cache cut load time by 40%."
    assert "40%" in check_meaning(ORIGINAL, rewrite)["added_numbers"]
    r = check_meaning(ORIGINAL, rewrite, also_allowed="In my own project the cache cut load time by 40%.")
    assert r["ok"], r


def test_measured_academic_register_defaults_to_light():
    text = ("The framework was evaluated under sustained load across six concurrency levels. "
            "Median latency was recorded for every configuration in the experiment. ") * 12
    assert voice.check_voice(text, register="academic:masters:business")["strength"] == "light"
    assert voice.check_voice(text, register="blog_technical")["strength"] == "medium"


def test_one_line_intros_do_not_trigger_thin_paragraphs():
    from humanizer_mcp import registers
    lo = registers.resolve("academic:masters:business")["ranges"]["avg_paragraph_words"][0]
    body = ("The survey covered small and medium firms in the retail sector and was sent out in two waves. " * 4).strip()
    assert len(body.split()) >= lo
    intro = "This chapter presents the findings."
    text = "\n\n".join(["## Findings", intro, body, "## Discussion", intro, body, "## Limits", intro, body])
    stats_avg = voice.text_stats(text)["avg_paragraph_words"]
    assert stats_avg < lo  # the raw average is dragged down by the one-line lead-ins
    r = voice.check_voice(text, register="academic:masters:business")
    assert "avg_paragraph_words" not in {m["feature"] for m in r["must_fix"] + r["optional"]}


def test_rewrite_docx_keeps_styles_and_never_overwrites(tmp_path):
    import docx
    from humanizer_mcp.docx_edit import docx_paragraphs, rewrite_docx

    src = tmp_path / "report.docx"
    d = docx.Document()
    d.add_heading("Findings", level=1)
    d.add_paragraph("Teh first paragraph has a typo in it and is otherwise fine as it is.")
    p = d.add_paragraph("The second paragraph has an ")
    p.add_run("italic term").italic = True
    p.add_run(" in the middle of it.")
    d.add_paragraph("The third paragraph is left alone.")
    d.save(str(src))
    before = src.read_bytes()

    listed = docx_paragraphs(src)["paragraphs"]
    assert [x["kind"] for x in listed] == ["heading", "body", "body", "body"]
    assert listed[0]["editable"] is False and listed[1]["editable"] is True

    r = rewrite_docx(src, {"0": "A new heading", "1": "The first paragraph has a typo in it and is otherwise fine as it is.",
                           "2": "The second paragraph has an italic term in its middle.", "99": "nothing"})
    assert r["paragraphs_rewritten"] == [1, 2]
    assert {s["index"] for s in r["skipped"]} == {0, 99}
    assert r["check_formatting"][0]["index"] == 2 and "italic term" in r["check_formatting"][0]["was_formatted"]
    assert src.read_bytes() == before  # the original is untouched

    out = docx.Document(r["saved_to"])
    texts = [x.text for x in out.paragraphs]
    assert texts[0] == "Findings" and out.paragraphs[0].style.name == "Heading 1"
    assert texts[1].startswith("The first") and texts[3] == "The third paragraph is left alone."
    try:
        rewrite_docx(src, {"1": "x y z"}, output_path=src)
    except ValueError:
        pass
    else:
        raise AssertionError("writing over the original must be refused")
