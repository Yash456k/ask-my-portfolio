<!-- rag-chunk: ai-build-workflow | How Yash builds software with AI coding agents: the agents he uses, who does which part, and the rules agents follow -->
# How Yash builds with AI

Yash builds his projects with AI coding agents: Claude Code, Codex and a Hermes agent. The coding-activity graph on his portfolio's home page is refreshed every night from his Codex, Claude Code and GitHub activity, and many commits in the Ask my portfolio and HiveNote repositories list Claude as a co-author.

The agents write much of the code. Yash decides what each project should do and how it should work, sets the rules and checks the agents work to, and reviews and measures what they produce. HiveNote's repository, for example, has an AGENTS.md file that tells agents how to build and test it, which tests are worth writing, and that a new version is released only when Yash says so.

<!-- rag-chunk: ai-build-checks | How Yash checks work done by AI agents: agent-written test questions, blind labelling, a judge model, and recorded agent runs -->
## Checking what the agents produce

Yash relies on measured checks for work that agents do. For Ask my portfolio, Claude Sonnet agents wrote the 276 test questions, separate agents labelled their evidence blind, and the set was locked before any retriever saw it; Yash has not yet reviewed those questions by hand. A judge model graded the chat's final answers, and he still has to check that judge against his own grades.

Several changes in HiveNote's 0.5 release came from recorded runs of agents using it. In 20 trial runs where three agents picked work from one board, two of them marked the same task as theirs in 16, so 0.5 refuses a second agent's claim on a task that is already taken. Replayed over five recorded runs, the shorter command output in 0.5 showed agents 64% fewer tokens.
