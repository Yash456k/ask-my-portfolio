<!-- rag-chunk: rag-project-overview | RAG Playground product, inspectability, architecture, and repository -->
# Selected projects by Yash Khambhatta

## RAG Playground - portfolio question answering

RAG Playground is an interactive public portfolio feature that lets visitors ask grounded questions about Yash. Its corpus contains curated resume facts and project writeups. Visitors can compare six resident embedding routes: MiniLM L6, BGE Small, BGE Base, Qwen3 Embedding 0.6B, and portfolio-tuned E5 Small and GTE Small models. They can also choose among Groq-hosted generation models.

The interface streams answers token by token and makes the retrieval process visible. Every response shows the selected embedder and language model, the retrieved source chunks with cosine-similarity scores, and embedding, retrieval, first-token, generation, and total latency. The backend uses FastAPI, PostgreSQL with pgvector, one vector column per embedding space, strict corpus-only prompting, daily per-IP and global rate limits, provider fallback, and query logging. The frontend is a Vite and React TypeScript single-page application.

Repository: https://github.com/Yash456k/rag-playground

<!-- rag-chunk: nsk-concurrency | Nashik Sports Klub booking scope, race prevention, and concurrency proof -->
## NSK - Nashik Sports Klub booking platform

Yash developed a multi-tenant facility-booking platform for Nashik Sports Klub. It manages Pickleball and Cricket inventory with distinct workflows for administrators, walk-in staff, and users. Administrators can manage a 40-day schedule.

The booking flow uses temporary slot reservations, MongoDB sessions, compound indexes, and atomic transactions for bulk bookings to prevent races. A k6 test sent 500 concurrent users toward one slot; exactly one booking committed, preserving 100 percent data integrity with 226 ms average latency in the reported test.

<!-- rag-chunk: nsk-security-delivery | Nashik Sports Klub access control, authentication, realtime delivery, hosting, and links -->
The platform includes role-based access control, MSG91 OTP verification, JWT authentication in HttpOnly cookies, real-time availability, a GitHub Actions delivery pipeline, AWS EC2 hosting, and Nginx TLS and secure WebSocket proxying.

- Live site: https://www.nashiksportsklub.com
- Public repository: https://github.com/Yash456k/NSK-Project-Public

<!-- rag-chunk: realtime-chat | Real-time MERN chat scale, authentication, data model, AI, and links -->
## Real-time MERN Chat Platform

Yash built a live, event-driven full-stack messaging interface with Socket.IO for real-time conversations. The project supports more than 100 users and has handled more than 500 messages. It integrates Google OAuth 2.0 and Firebase authentication, uses React Context for state management, JWTs for security, and MongoDB schemas for users, chats, and messages.

The application also includes an AI chatbot powered by Google Gemini.

- Live demo: https://yashchatapp.vercel.app
- Repository: https://github.com/Yash456k/SocketIO-MERN-chatApp
