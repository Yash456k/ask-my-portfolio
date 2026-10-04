# Rules for writing evaluation questions

You are writing test questions for a retrieval evaluation. The system under test is a chat on
Yash Khambhatta's portfolio site. A visitor asks a question about Yash; a retriever must pick,
out of 23 passages, the passage(s) that contain the answer. Your questions will be used to score
seven different retrievers, so a wrong or sloppy label unfairly punishes or rewards them.

Read `corpus-passages.md` in this folder first, all of it. Every passage has a `passage id`.

## What every question must satisfy
- It is something a recruiter, interviewer, hiring manager, or curious site visitor would ask
  about Yash or his work. Refer to him as "Yash" or "he" (third person). Never "you".
- It is fully answerable from the passages alone. Do not use outside knowledge.
- It asks about ONE specific fact or closely tied set of facts, unless told otherwise.
- The passages you list as evidence really contain the answer. Before you list a passage, find
  the sentence in it that answers the question.
- List EVERY passage that contains the answer, not only the one you were assigned. Some facts are
  stated in two or three passages (for example the FastAPI/pgvector stack, the six embedding
  models, Jev being the default, rate limits). If the same fact is answerable from another
  passage, that passage must be in the evidence list too. If a question would be answerable from
  four or more passages, it is too vague: rewrite it to be more specific.
- Within one passage, spread your questions across its different facts. No two questions should
  ask for the same fact.
- Do not ask questions whose answer depends on today's date.
- Do not copy a question from another style; each must be genuinely different.

## Styles
- `direct`: a clear, complete question that uses the passage's own key terms.
- `paraphrase`: asks for a fact without reusing the passage's distinctive words. Use synonyms and
  describe things indirectly (for example "the cricket and pickleball venue" instead of the
  club's name, "the model that picks passages without vectors" instead of "Jev"). It must still be
  unambiguous about which fact it wants.
- `terse`: 2 to 6 words, lowercase, no question mark, the way real visitors type
  (real examples from the site's log: "contact info", "background", "what does yash do").
- `noisy`: a casual question with 2 to 4 realistic typos, missing punctuation or apostrophes,
  maybe a stray word (real example: "what work has yash done , and hwat has been the challanges").
  It must remain understandable.
- `follow-up`: comes with a `history` of exactly two messages: a user question and a short
  assistant answer (one sentence, true to the corpus). The final question uses "he", "it",
  "that", "those" etc., so it CANNOT be understood without the history. The evidence is for
  the final question only.
- `interviewer`: a probing "why" or "how" or trade-off question an engineer would ask, answerable
  from the reasoning the passage gives (not just a fact lookup).

## Output
Write a single JSON file (path given in your task) containing a JSON array. Each element:

```json
{
  "style": "direct",
  "question": "…",
  "history": [],
  "facts": [
    {"label": "short name of the fact", "passages": ["passage-id", "other-passage-id-if-it-also-states-it"]}
  ],
  "reference_answer": "One or two sentences that answer the question using only what the passages say."
}
```

- `history` is `[]` except for `follow-up`, where it is
  `[{"role": "user", "content": "…"}, {"role": "assistant", "content": "…"}]`.
- `facts` has ONE entry for a normal question. Each entry's `passages` lists every passage that
  states that fact (any one of them is enough to answer). Use passage ids exactly as written.
- Use plain ASCII quotes inside strings and make sure the file is valid JSON (check it by
  running `python3 -c "import json;print(len(json.load(open('FILE'))))"`).

When you finish, reply with only: the file path, how many questions you wrote, and any passage
where you could not write the requested number of good questions (and why).
