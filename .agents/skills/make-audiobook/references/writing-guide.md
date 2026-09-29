# Writing for the ear

A listener on a commute cannot re-read, cannot see a diagram, and will be
interrupted by an announcement every few minutes. Everything below follows from
that one fact. These are the habits of good audiobook and podcast writing, not
arbitrary house rules; when a rule fights the material, favour the listener.

## 1. The depth contract (decide it, don't assume it)

The same topic can be a ten-minute overview or a six-hour course. The skill does
not fix a depth; the outline does. Before writing anything, agree with the user
on:

- **Who is listening** — background they already have (e.g. "knows Python,
  never touched a systems language"; "has read Bloom's *The Western Canon*").
- **What they should be able to do or say afterwards** — "explain to a
  colleague why the reverse process needs a learned network", "recognise the
  sublime in Whitman when they meet it".
- **How much math / code / quotation** — use this ladder as shared vocabulary,
  then write the choice into `outline.md` and `book.yaml: depth`:
  1. *Intuition only* — analogies, no formulas; symbols named but not manipulated.
  2. *Skeleton formulas* — the 3–6 equations that carry the idea, spoken in
     words, shown exactly on screen; no derivations.
  3. *Derivations and mechanisms* — key steps of proofs, why each term exists,
     complexity, failure modes.
  4. *Implementation and frontier* — code-level details, trade-offs, open
     problems, disagreements between practitioners.
- **Total length and chapter length** — commute-sized chapters of 8–15 minutes
  work well; a book of 6–12 chapters is typical. See §6 for how to estimate.
- **Language** — Chinese by default; English on request. See §5.
- **Sources** — if the user hands you papers, a book, lecture notes, read them
  in full before outlining and stay faithful to them; otherwise draw on what you
  know and say so when something is contested.

Write the agreed contract at the top of `outline.md`, followed by the chapter
plan (title, one-paragraph summary, the 2–4 things the listener will take away,
the formulas or passages that will appear). The outline is the first review
checkpoint; do not draft chapters before the user has approved it.

## 2. Shape of a chapter

A chapter is a guided walk, not an article. Use this skeleton and adapt freely:

1. **Cold open (20–40 s).** A concrete puzzle, a wrong intuition, a line of a
   poem, a bug. Earn attention before explaining anything.
2. **Roadmap (20 s).** "这一章讲三件事：…、…、…。" The listener needs a map
   because they cannot skim.
3. **Body in 2–4 minute sections**, each with one idea, one example, and a
   one-sentence landing ("所以记住：…"). Use `##` headings; they are narrated
   and give the listener audible chapter marks.
4. **Recap (30–60 s).** Restate the two or three takeaways in different words
   than before. Repetition is a feature in audio, not a flaw.
5. **Bridge (10 s).** One sentence on what the next chapter does with this.

Keep paragraphs to one breath group, roughly 60–150 汉字 (40–90 English
words). Short paragraphs give the TTS engine natural phrasing and give the
reader a highlight that moves at a comfortable pace.

## 3. Sentence-level habits

- **One idea per sentence.** Split anything with two subordinate clauses.
- **Concrete before abstract, example before definition.** "你写了一个函数，
  把一个 String 传进去，然后想再用一次它，编译器报错了。这就是 move。" — then
  the definition.
- **Signpost relentlessly.** 首先/然后/最后、换句话说、这里的关键是、注意、
  我们回到刚才的例子. Verbal signposts replace typography.
- **Name things the same way every time.** Essay writing rewards synonyms;
  audio punishes them. Pick one term per concept and record it in the outline
  glossary.
- **Repeat nouns instead of pronouns** when the referent is more than a clause
  away. "它" is ambiguous within seconds.
- **No visual references.** Never "如下图所示", "上面的公式", "见表 2". The
  screen is optional. Say "刚才那个公式" or re-say the thing.
- **Enumerate in speech, not in bullets.** "有三个原因。第一，…。第二，…。
  第三，…。" and keep lists to three or four items. Markdown lists are supported
  but read stiffly.
- **Numbers the ear can hold.** "大约三成" beats "31.7%"; "几千个" beats
  "4,096". Use exact numbers only when the exact value is the point.
- **Nothing that cannot be said aloud** in spoken text: URLs, citations,
  DOIs, long identifiers, hex values. Put them in a shown-only block (a fenced
  block or a `<div>` at the end of the chapter, e.g. `延伸阅读`).
- **Pace cues are allowed.** "这一段稍微慢一点" or "这一句值得再听一遍" are
  things a good narrator says.
- **Address the listener.** 你 / 我们. The persona is a knowledgeable friend
  explaining on a walk: warm, precise, unhurried, honest about uncertainty,
  sparing with jokes.

## 4. Handling math, code, and quotations

Math and code are an essential part of learning many topics and belong in the
audiobook. They just have to be *spoken* well, and shown exactly. The detailed
conventions — how to read `\bar\alpha_t`, fractions, sums, a Rust signature —
are in `math-and-code.md`. The short version:

- Say what a formula *means* first, then say the formula in words, then show
  the exact LaTeX in a `$$` block. Keep any single spoken formula under about
  fifteen seconds; split longer ones into named pieces.
- Never dictate code. Describe what it does, name the two or three identifiers
  that matter, and show the snippet in a fenced block.
- Quotations (poems, passages) go in a blockquote so they are read line by line
  with a breath between lines. Say who is speaking before the quote begins.

## 5. Language policy

### Chinese (default)

Chinese technical prose in practice is code-switched, and the audiobook should
sound like a good Chinese lecturer, not like a translated textbook.

- **Keep a term in English when English is what practitioners actually say.**
  buffer, trait, borrow checker, lifetime, closure, diffusion model, latent,
  sampler, attention, token, embedding, loss, gradient (in ML contexts), pull
  request, commit. Translating these ("缓冲区", "特征", "借用检查器") makes the
  text harder to map onto docs and code the listener will meet later.
- **Translate when the Chinese term is the established one** and English would
  sound affected: 函数, 变量, 概率, 期望, 方差, 矩阵, 编译器, 内存, 递归,
  隐喻, 韵律, 崇高.
- **First appearance per chapter of a translated term: give the English too,
  in spoken form.** "梯度下降，英文叫 gradient descent，…" or "…也就是
  gradient descent". Written parentheses "梯度下降（gradient descent）" are
  acceptable and TTS engines handle them, but the spoken form flows better.
- **Decide once per book.** Record every term decision in the glossary section
  of `outline.md` and reuse it in every chapter.
- **Spacing and inflection.** Put a space on both sides of an embedded English
  word. Don't inflect English inside Chinese: "这些 trait" not "这些 traits";
  "两个 buffer" not "两个 buffers".
- **Acronyms** are a TTS hazard. Use the `pronunciations` map in `book.yaml`
  to spell them out ("SQL" → "S Q L", "GPU" → "G P U") or pick the spoken form
  a Chinese engineer would use ("API" is usually fine as-is).
- **Greek letters** are spoken in English (alpha, beta, epsilon, theta, sigma),
  which is how Chinese practitioners actually say them.

### English

Same craft. Choose one variety of spelling. Spell out symbols and short
initialisms in the spoken text where an engine would guess ("S-Q-L" vs
"sequel" — pick one, map it). Read poetry line by line in a blockquote.

## 6. Length and pace estimation

`audiobook-stats` estimates minutes per chapter. Its model, so you can plan
before running it:

- Mandarin narration at a normal audiobook pace ≈ 4 汉字 / second (≈ 240 字/分).
- English (in either language mode) ≈ 2.5 words / second (≈ 150 wpm).
- Plus the configured pauses between segments (about 0.5 s per paragraph).

So a 12-minute Chinese chapter is roughly 2,600–2,900 汉字 of spoken text; an
English one about 1,700 words. Users listen at 1.2–1.5× speed surprisingly
often, so err on the side of slightly *more* content per chapter rather than
padding.

## 7. Literature, poetry, and criticism

Treat a literary chapter like a seminar led by a well-read friend, not a
summary.

- **Let the text speak first.** Read the lines (blockquote, line by line),
  then unpack them. For a Chinese audiobook about an English-language poem,
  read the original lines in English and then give a Chinese rendering or
  close paraphrase; ask the user whether they want originals read at all if the
  poems are long.
- **Describe form in words** — stanza shape, meter, where the volta falls,
  enjambment — since the listener cannot see the lineation. Show the passage on
  screen with its line breaks (blockquote) so the reader can check.
- **Name the critics and their arguments**, and distinguish the critic's claim
  from your own reading. When discussing a critic's book (Bloom, Vendler,
  Empson…), paraphrase the argument and quote only short, distinctive phrases.
- **Copyright.** Public-domain texts (Whitman, Dickinson, 杜甫, 李商隱) may be
  quoted in full. Living or recent authors and critics: quote briefly, paraphrase
  the rest, and never reproduce a chapter's structure wholesale. The audiobook
  is original commentary.
- **Context budget.** Biography and period background earn their place only
  when they change how a line sounds. Cut the rest.

## 8. Review loop

1. Show `outline.md`; wait for approval or edits.
2. Draft chapters. Drafting several chapters in parallel is fine, but hand
   each writer the same outline and glossary, then read the whole set for
   terminology drift, repeated cold-opens, and missing bridges.
3. Run `audiobook-stats` and share the table (minutes per chapter, flagged
   raw math, over-long paragraphs). Fix what it flags.
4. Hand the chapters to the user for reading. Expect several rounds. Small
   edits are cheap later because unchanged paragraphs are never re-synthesized.
5. Only after the text is approved: preview a voice, then synthesize.
