<!-- rag-chunk: rag-project-overview | Ask my portfolio (formerly RAG Playground) product, inspectability, architecture, and repository -->
# Selected projects by Yash Khambhatta

Yash's portfolio covers four projects: Ask my portfolio, NSK (a booking platform for Nashik Sports Klub), HiveNote and a real-time MERN chat platform.

## Ask my portfolio - portfolio question answering

Ask my portfolio, first built as RAG Playground, is the chat on Yash's portfolio site that answers grounded questions about Yash. Yash started building it in July 2026 and continues to develop it. Its corpus contains curated resume facts and project writeups. Jev, a TypeSafe decision model, is the default retriever; six embedding routes are also available. DeepSeek V4.1 Flash writes answers by default, with Groq-hosted models as options.

The interface streams answers token by token and makes the retrieval process visible. Every response shows the selected retriever and language model, the retrieved source chunks with their scores, and each stage's latency. The backend uses FastAPI, PostgreSQL with pgvector, strict corpus-only prompting, rate limits, provider fallback, and query logging. The frontend is a Vite and React TypeScript single-page application.

Repository: https://github.com/Yash456k/ask-my-portfolio

<!-- rag-chunk: nsk-concurrency | Nashik Sports Klub booking scope, race prevention, and concurrency proof -->
## NSK - Nashik Sports Klub booking platform

Yash developed a multi-tenant facility-booking platform for Nashik Sports Klub, starting in August 2025. The site is live and takes real bookings for pickleball, cricket and padel courts, with distinct workflows for administrators, walk-in staff, and users. Administrators can manage a 40-day schedule.

The booking flow uses temporary slot reservations, MongoDB sessions, compound indexes, and atomic transactions for bulk bookings to prevent races. A k6 test sent 500 concurrent users toward one slot; exactly one booking committed, preserving 100 percent data integrity with 226 ms average latency in the reported test. In that test 472 requests were turned away with 409 Conflict, and about 27 timed out against the test machine's connection-pool limit.

<!-- rag-chunk: nsk-security-delivery | Nashik Sports Klub access control, authentication, realtime delivery, hosting, and links -->
The platform includes role-based access control, phone-number sign-in verified through Phone.Email, JWT authentication in HttpOnly cookies, online booking-fee payments through Razorpay, real-time availability, a GitHub Actions delivery pipeline, AWS EC2 hosting, and Nginx TLS and secure WebSocket proxying. Its frontend uses React 19, TypeScript and Vite; its backend uses Node.js, Express 5, Mongoose and Agenda on MongoDB.

- Live site: https://www.nashiksportsklub.com
- Public repository: https://github.com/Yash456k/NSK-Project-Public

<!-- rag-chunk: hivenote-overview | HiveNote shared notebook for AI agents, why Yash built it, how notes work, and links -->
## HiveNote - a shared notebook for AI agents

HiveNote is an open-source npm package that Yash started in September 2026. It gives AI agents one shared notebook, so they save what they learn and hand work to each other instead of Yash copy-pasting between them. He built it because he uses Claude Code, Codex and a Hermes agent, and was carrying each one's findings over to the others by hand. Any agent that can run a shell command can use it, through the `hivenote` command and a short skill file that teaches the agent when to read and save.

Every note has a name and a one-line description, so an agent lists the hive, opens only the notes its task needs, and updates them when it learns something new. Every version of a note is kept and can be restored. HiveNote is written in TypeScript on Node.js and keeps the whole hive in a single SQLite file.

- npm package: https://www.npmjs.com/package/hivenote
- Repository: https://github.com/Yash456k/hivenote

<!-- rag-chunk: hivenote-tasks-sharing | HiveNote tasks, waiting on another agent, queen and worker machines, and the live dashboard -->
A HiveNote note can also be a task. An agent marks the task as doing, which puts its name and the time on it for every agent to see, appends progress as it goes, and marks it done. Another agent can wait on that task and carry on within seconds of it finishing. To share one hive between machines, one machine becomes the queen by running `hivenote serve` and the others connect as workers, each with its own token. A browser dashboard shows the notes as cards or as a honeycomb, a task board that follows each task from To do to Done, and a live feed of which agent did what.

<!-- rag-chunk: realtime-chat | Real-time MERN chat scale, authentication, data model, AI, and links -->
## Real-time MERN Chat Platform

Yash built a live, event-driven full-stack messaging interface with Socket.IO for real-time conversations. The project supports more than 100 users and has handled more than 500 messages. It integrates Google OAuth 2.0 and Firebase authentication, uses React Context for state management, JWTs for security, and MongoDB schemas for users, chats, and messages.

The application also includes an AI chatbot powered by Google Gemini.

- Started: June 2024
- Live demo: https://yashchatapp.vercel.app
- Repository: https://github.com/Yash456k/SocketIO-MERN-chatApp
