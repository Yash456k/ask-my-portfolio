<div align="center">

<a href="https://www.yash456k.com"><img src="docs/assets/home.png" alt="The home page of yash456k.com: &quot;I build stuff I find interesting&quot; beside a year of daily coding activity" width="100%"></a>

<h1>Ask my portfolio</h1>

<p>My portfolio site, with a chat that answers questions about my work and shows the sources behind every answer.</p>

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](Dockerfile)
[![React](https://img.shields.io/badge/React-19-20232A?style=flat-square&logo=react)](frontend/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)](app/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_%2B_pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](sql/schema.sql)

</div>

<br>

The site at [yash456k.com](https://www.yash456k.com) holds my experience, my projects, and a chat you can ask about any of it. The home page pairs a short introduction with a graph of my daily coding activity, refreshed every night from Codex, Claude Code and GitHub, where you can switch between the last three months and the full year.

## Experience and projects

Scrolling down, experience and projects sit side by side. The role cards stack like a deck you can drag through, the timeline above them marks where each role and the selected project fall, and the project wheel turns through my projects and opens each one with its details, metrics, and links. On a phone the same sections work with swipes.

[![Experience and projects side by side, with a timeline above the role cards](docs/assets/work.png)](https://www.yash456k.com/#work)

## The chat

The chat answers from a small set of documents about me, split into hand-reviewed passages. Every answer streams in with citations, and the panel beside it shows which passages were used, how closely each one matched, which model wrote the answer, and how long each step took.

[![The chat answering a question about Yash's work, with the passages it used listed beside the answer](docs/assets/chat.png)](https://www.yash456k.com/#playground)

## How it works

A question first goes to a retriever, which picks the passages most likely to hold the answer, and a language model then writes the reply from those passages alone, citing each one it uses.

![How a question is answered: a retriever picks passages, a language model writes from them, and the answer streams back with citations](docs/assets/architecture.svg)

You can choose the retriever: one of six embedding models, two of them fine-tuned on reviewed questions about my work, or Jev, a decision model from TypeSafe that reads every passage as plain text and picks the one that answers the question. Jev is the default because it put the right passage first more often than any of the embedding models, and when nothing in the portfolio can answer a question it says so before a language model is ever called.

| Retrieval | Right passage first | Mean reciprocal rank | Refused with no language model |
|---|---:|---:|---:|
| **Jev** (default) | **100%** | **1.00** | **45 of 51** |
| Qwen3 Embedding 0.6B | 80.0% | 0.88 | 18 of 51 |
| Portfolio E5 Small, fine-tuned | 77.3% | 0.86 | 9 of 51 |
| BGE Base | 72.9% | 0.84 | 0 of 51 |

These come from 276 test questions: 225 the portfolio can answer and 51 it has to refuse, like prompt injection, private details and off-topic requests. Jev put a right passage first on all 225 answerable ones (224 in an earlier run; it isn't deterministic). Its lead over the best embedding model is 20 points (95% interval 15 to 25): it ranked a right passage first on 45 questions where that model didn't, and never the other way round. The questions were written by one set of Claude agents and their evidence labelled blind by another, then locked before any retriever saw them; I haven't hand-reviewed them yet. The [full report](evaluation/retrieval-challenge-v3.md) covers all seven routes, each kind of question, and the limits, and an [earlier comparison](evaluation/jev-retrieval.md) on a smaller set of 37 questions agrees. The chat's final answers to the same questions were graded by a judge model: 213 of the 225 came out correct and fully supported, and all 51 that should be refused were ([report](evaluation/answers-challenge-v3.md)). I still have to check that judge against my own grades. Hand-reviewed passage boundaries raised Recall@5 by 0.10 over automatic splitting ([report](docs/manual-semantic-chunking-evaluation.md)). DeepSeek V4.1 Flash writes the answers, mostly because it was cheap lol, and it also stuck to the facts better than the other seven models I tried ([report](evaluation/llm-comparison.md)). Jev also reads what each visitor is asking for and how they seem to feel, which shows up as small tags in the chat.

## Run it yourself

With Node.js 22 you can run the site against the live API, which needs no models or keys (the public rate limits still apply):

```bash
git clone https://github.com/Yash456k/ask-my-portfolio.git
cd ask-my-portfolio/frontend
npm ci
VITE_API_URL=/api npm run dev
```

Running your own backend needs Docker and a `.env` copied from `.env.example` with Groq and OpenRouter keys, plus a TypeSafe key if you want Jev. The API also expects the two fine-tuned models in `model-artifacts/`, which are not in the repository; `scripts/train_portfolio_embedders.py` rebuilds them from the reviewed data in `training/`.

```bash
docker compose build api
docker compose up -d --wait db
docker compose run --rm --no-deps api python -m app.ingest --corpus /app/corpus
docker compose up -d api
```

Content updates are one command from my laptop, `scripts/deploy_corpus.sh`: it runs the 276-question retrieval evaluation as a gate, then has the server pull `main` and swap the new passages in while the API keeps serving. Only passages whose text changed are embedded again.

Tests run with `pytest -q` and `npm --prefix frontend run check`, and the evaluation suites are described in [evaluation/README.md](evaluation/README.md).

## License

[MIT](LICENSE)
