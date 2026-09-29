"""Segmenter: what is shown, what is spoken, and how long it takes to say."""

from __future__ import annotations

from audiobook_lib.segmenter import (
    apply_pronunciations,
    chunk_text,
    count_cjk,
    count_latin_words,
    estimate_seconds,
    segment_markdown,
    spoken_from_source,
)


def test_fenced_code_keeps_override_literal():
    src = """段落一 {{显示||朗读}}。

```python
tpl = "{{name||nom}}"
if a || b: pass
```

段落二。
"""
    segs = segment_markdown(src)
    assert [s.kind for s in segs] == ["para", "display", "para"]
    assert "{{name||nom}}" in segs[1].html
    assert segs[1].spoken is None


def test_override_splits_shown_and_spoken():
    segs = segment_markdown("段落一 {{显示||朗读}}。\n")
    assert segs[0].spoken == "段落一 朗读。"
    assert segs[0].html == "<p>段落一 显示。</p>"


def test_pipes_inside_math_in_the_shown_half():
    src = r"我们记 {{$\lVert x \rVert = |x_1| || |x_2|$||范数}} 为长度。"
    spoken, _ = spoken_from_source(src)
    assert spoken == "我们记 范数 为长度。"
    segs = segment_markdown(src)
    assert segs[0].html == (
        r"<p>我们记 $\lVert x \rVert = |x_1| || |x_2|$ 为长度。</p>"
    )


def test_code_span_override_is_literal():
    spoken, _ = spoken_from_source("写 `{{a||b}}` 就行。")
    assert spoken == "写 {{a||b}} 就行。"


def test_unbalanced_braces_are_flagged_but_text_survives():
    spoken, warns = spoken_from_source("坏的 {{只有左边 然后结束。")
    assert any("unbalanced" in w for w in warns)
    assert spoken == "坏的 {{只有左边 然后结束。"


def test_nested_and_ordered_lists():
    src = """- 一级甲
  - 二级甲
  - 二级乙
- 一级乙

1. 第一
2. 第二
"""
    segs = segment_markdown(src)
    assert [s.kind for s in segs] == ["item"] * 6
    assert [s.spoken for s in segs] == [
        "一级甲", "二级甲", "二级乙", "一级乙", "第一", "第二",
    ]
    assert [s.html.split('data-depth="')[1][0] for s in segs] == [
        "1", "2", "2", "1", "1", "1",
    ]
    assert [
        s.html.split('data-marker="')[1].split('"')[0] for s in segs[4:]
    ] == ["1.", "2."]


def test_blockquote_is_one_line_segment_per_source_line():
    src = """> 第一行
> 第二行
>
> 第三行
"""
    segs = segment_markdown(src)
    assert [s.kind for s in segs] == ["line", "line", "line"]
    assert [s.spoken for s in segs] == ["第一行", "第二行", "第三行"]
    assert segs[0].html == '<p class="line">第一行</p>'


def test_comment_rule_math_block_and_image():
    src = """<!-- 内部备注 -->

正文。

$$
a_1 = b
$$

---

![图](x.png)
"""
    segs = segment_markdown(src)
    assert [s.kind for s in segs] == ["para", "display", "rule", "display"]
    assert segs[1].html == '<div class="math">$$\na_1 = b\n$$</div>'
    assert segs[2].html == "<hr>"


def test_single_line_math_block():
    segs = segment_markdown("$$x_1 = 2$$\n")
    assert (segs[0].kind, segs[0].html) == (
        "display", '<div class="math">$$x_1 = 2$$</div>',
    )


def test_frontmatter_is_stripped():
    segs = segment_markdown("---\ntitle: x\n---\n\n# 标题\n")
    assert [s.kind for s in segs] == ["heading"]


def test_inline_markers_are_stripped_from_speech():
    spoken, _ = spoken_from_source(
        "**粗** *斜* `代码` [链接](http://x) 脚注[^1] <b>标签</b>"
    )
    assert spoken == "粗 斜 代码 链接 脚注 标签"


def test_identifiers_keep_their_underscores():
    spoken, _ = spoken_from_source("调用 read_to_string 即可。")
    assert spoken == "调用 read_to_string 即可。"


def test_pronunciations_match_the_source_form_longest_first():
    pron = {
        "$\\bar\\alpha_t$": "alpha bar t",
        "$\\bar\\alpha$": "alpha bar",
        "SQL": "S Q L",
    }
    spoken, warns = spoken_from_source("把 $\\bar\\alpha_t$ 存进 SQL。", pron)
    assert spoken == "把 alpha bar t 存进 S Q L。"
    assert warns == []  # a covered formula no longer warns
    assert apply_pronunciations("$\\bar\\alpha_t$", pron) == "alpha bar t"


def test_bare_inline_math_warns_and_drops_latex_punctuation():
    spoken, warns = spoken_from_source("这里的 $\\sigma_t$ 是标准差。")
    assert spoken == "这里的 sigma t 是标准差。"
    assert any("bare inline" in w for w in warns)


def test_pace_model():
    assert count_cjk("中文 abc 123 中") == 3
    assert count_latin_words("中文 abc 123 中") == 2
    assert round(estimate_seconds("一二三四", 500), 3) == 1.5


def test_chunking_splits_at_sentence_punctuation():
    long = "甲" * 40 + "。" + "乙" * 40 + "。" + "丙" * 40 + "。"
    chunks = chunk_text(long, 50)
    assert [len(c) for c in chunks] == [41, 41, 41]
    assert "".join(chunks) == long
    assert chunk_text("短", 50) == ["短"]
