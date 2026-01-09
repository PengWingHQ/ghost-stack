# 👻 GhostStack

> **The Agent-First Stack Manager** — Built for AI, loved by Vibe Coders.

GhostStack is a local-first, headless workflow engine designed for the "Vibe Coding" era. Unlike traditional tools built for human eyes, GhostStack is built for **AI Agents**. It exposes a robust CLI and MCP (Model Context Protocol) server that allows tools like Cursor and Claude Code to manage stacked PRs and perform deep, context-aware reviews.

---

## ✨ Features

### 🔍 The "Ghost" Review
AI-powered code review that understands your entire codebase:
- **Vector Search**: Finds "hidden impact" files not in your diff but logically related
- **Context-Aware**: Detects when changes to one file might break another
- **Local RAG**: Uses ChromaDB for real-time embeddings of your codebase

### 📚 Stack Management
Seamless stacked PR workflow:
- **Clean Branching**: `gs stack add` handles all the Git complexity
- **Auto-Sync**: `gs stack sync` uses `git rebase --update-refs` to keep your stack healthy
- **Agent Safety**: Auto-stash, dirty tree protection, and an "Undo" log

### 🤖 Agent-Native Interfaces
- **MCP Server**: First-class integration with Cursor, Claude, and Antigravity
- **CLI**: Markdown-formatted output that LLMs can parse beautifully
- **JSON Mode**: Structured output for programmatic consumption

---

## 🚀 Quick Start

```bash
# Download and install
curl -L ghoststack.sh | sh

# Initialize in your repo
cd your-project
gs init

# Start stacking!
gs stack add "feature/auth-refactor"
```

---

## 🛠️ CLI Commands

| Command | Description |
|---------|-------------|
| `gs init` | Initialize GhostStack in the current repo |
| `gs stack list` | Show the current stack tree (JSON) |
| `gs stack add <name>` | Create a new branch on top of current |
| `gs stack sync` | Rebase the entire stack on main |
| `gs review` | Get an AI-powered review of your changes |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Interface Layer                          │
│  ┌──────────────┐                    ┌──────────────────┐   │
│  │  MCP Server  │  ←  Primary        │   CLI (`gs`)     │   │
│  │   (JSON)     │     Interface      │   (Markdown)     │   │
│  └──────────────┘                    └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Stacking Engine                          │
│  • git rebase --update-refs (native Git)                    │
│  • Auto-stash / dirty tree protection                       │
│  • Undo log (reflog wrapper)                                │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Review Intelligence                      │
│  • ChromaDB (local vector store)                            │
│  • Real-time file embeddings                                │
│  • LLM API connector (Gemini/Claude/OpenRouter)             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Tech Stack

- **Language**: Python (bundled with PyInstaller for single-file binary)
- **Vector DB**: ChromaDB (embedded)
- **Git**: Subprocess calls to system `git`

---

## 🗺️ Roadmap

- [x] Project initialization
- [ ] **Phase 1**: Clean CLI (`gs stack create`, `gs stack sync`)
- [ ] **Phase 2**: Local Brain (ChromaDB + file ingestor)
- [ ] **Phase 3**: API Connector (LLM integration)
- [ ] **Phase 4**: MCP Server

---

## 📄 License

MIT License — See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Built for Agents. Loved by Vibes.</strong>
</p>
