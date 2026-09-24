[![Ask my portfolio answering a question about Yash's work, with the passages it used listed beside the answer](docs/assets/ask-my-portfolio.png)](https://www.yash456k.com/#playground)

# Ask my portfolio

[![Live demo](https://img.shields.io/badge/Live_demo-yash456k.com-C74634?style=for-the-badge)](https://www.yash456k.com/#playground)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](Dockerfile)
[![React](https://img.shields.io/badge/React-19-20232A?style=flat-square&logo=react)](frontend/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi)](app/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_%2B_pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](sql/schema.sql)
[![CI](https://github.com/Yash456k/rag-playground/actions/workflows/ci.yml/badge.svg)](https://github.com/Yash456k/rag-playground/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-black?style=flat-square)](LICENSE)

My portfolio site, with a chat that answers questions about my work and shows the sources behind every answer.

The site at [yash456k.com](https://www.yash456k.com) holds my experience, my projects, and a graph of my daily coding activity. The chat answers from a small set of documents about me, split into hand-reviewed passages, and every answer streams in with citations while the panel beside it shows which passages were used, how closely each one matched, which model wrote the answer, and how long each step took.

## How it finds answers

You can choose how the chat looks for its sources: one of six embedding models, two of them fine-tuned on reviewed questions about my work, or Jev, a decision model from TypeSafe that reads every passage as plain text and picks the one that answers the question. Jev is the default because it put the right passage first more often than any of the embedding models, and when nothing in the portfolio can answer a question it says so before a language model is ever called.

| Retrieval | Recall@1 | Mean reciprocal rank |
|---|---:|---:|
| **Jev** (default) | **0.95** | **1.00** |
| Portfolio E5 Small, fine-tuned | 0.81 | 0.91 |
| BGE Base | 0.78 | 0.90 |
| MiniLM L6 | 0.64 | 0.79 |

These come from 39 answerable test questions, and the [full comparison](evaluation/jev-retrieval.md) covers all seven routes and how refusals were checked. Hand-reviewed passage boundaries raised Recall@5 by 0.10 over automatic splitting ([report](docs/manual-semantic-chunking-evaluation.md)). DeepSeek V4.1 Flash writes the answers, mostly because it was cheap lol, and it also stuck to the facts better than the other seven models I tried ([report](evaluation/llm-comparison.md)). Jev also reads what each visitor is asking for and how they seem to feel, which shows up as small tags in the chat.

## How it's built

![How a question flows from the site through Cloudflare Tunnel and the API to retrieval, the language model, and back as a streamed answer](docs/assets/architecture.svg)

The site is hosted on Vercel and the API runs on a single Hetzner server that can only be reached through a Cloudflare Tunnel; the [security notes](deploy/SECURITY.md) describe how it is locked down. Questions and answers are saved to improve the portfolio, as the note under the chat says, and raw IP addresses are never stored.

## Run it yourself

With Node.js 22 you can run the site against the live API, which needs no models or keys (the public rate limits still apply):

```bash
git clone https://github.com/Yash456k/rag-playground.git
cd rag-playground/frontend
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

Tests run with `pytest -q` and `npm --prefix frontend run check`, and the evaluation suites are described in [evaluation/README.md](evaluation/README.md).

## License

[MIT](LICENSE)
