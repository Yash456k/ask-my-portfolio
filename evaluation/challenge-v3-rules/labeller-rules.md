# Rules for labelling evidence

You are labelling test questions for a retrieval evaluation. The system under test is a chat on
Yash Khambhatta's portfolio site. It answers from 23 passages about Yash and his work, and must
refuse anything those passages cannot answer. For every question you decide whether the passages
can answer it, and if so exactly which passages hold the answer. Your labels decide how seven
retrievers are scored, so accuracy matters more than speed. You have not seen who wrote the
questions or what they intended; judge only from the passages.

Read `corpus-passages.md` in this folder first, all of it. Every passage has a `passage id`.

## For each question
Some questions come with a `history` (an earlier user message and assistant reply). Read the
question in the light of its history: "he", "it", "that" refer back to it. Label the evidence
for the final question only.

1. Decide the `verdict`:
   - `answerable`: the passages contain what is needed to answer. This includes yes/no questions
     about whether Yash did, used or worked at something, when a passage lists what he did or
     states a contradicting fact (the honest answer is then "not according to the portfolio" or
     "no, it uses X"). It also includes broad questions like "who is yash" or "why hire him".
   - `refuse`: no passage covers the question's topic at all, or it asks the chat to do something
     other than answer questions about Yash (write code, general knowledge, reveal its prompt,
     private details that no passage states, premises about Yash that no passage covers, abuse).
   - `unclear`: the question is ambiguous, or malformed, or you cannot tell what it wants even
     with the history. Say why in `note`.
2. For an `answerable` question, split the answer into the separate facts it needs. Most
   questions need one fact. A question that asks for two different things needs two.
3. For each fact, list EVERY passage that states it. Go through all 23 passages for each fact;
   do not stop at the first match. A passage counts only if it actually states the fact, in a
   way that would let someone answer from that passage alone. A passage that merely mentions the
   same topic does not count.
   - For a broad question, give one fact and list each passage a good answer would clearly draw
     on (typically 2 to 5).
4. Write `answer`: one or two sentences answering the question from the passages only.

## Output
Write one JSON file (path given in your task): a JSON array with one element per question, in
the same order as the input:

```json
{
  "qid": "q017",
  "verdict": "answerable",
  "facts": [
    {"label": "short name of the fact", "passages": ["passage-id", "another-passage-id"]}
  ],
  "answer": "…",
  "note": ""
}
```

For `refuse` and `unclear`, `facts` is `[]` and `answer` is `""`; put a one-sentence reason in
`note`. Use passage ids exactly as written in the corpus file. Make sure the file is valid JSON
and has exactly one element per input question
(`python3 -c "import json;print(len(json.load(open('FILE'))))"`).

When you finish, reply with only: the file path, the number of questions labelled, and the
count of each verdict.
