import {
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { flushSync } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ApiError, getConfig, streamChat } from './api'
import { AboutSection } from './components/AboutSection'
import { AllProjectsSection } from './components/AllProjectsSection'
import { LandingSection } from './components/LandingSection'
import { SectionNavigator } from './components/SectionNavigator'
import { emotionColor } from './emotions'
import { WorkSection } from './components/WorkSection'
import type {
  AssistantMessage,
  ConversationSignals,
  ChatMessage,
  EmbeddingConfirmation,
  HistoryItem,
  ModelOption,
  PlaygroundConfig,
  RetrievedChunk,
  StreamEvent,
} from './types'

const QUESTION_LIMIT = 500

type PortfolioRoute = 'home' | 'projects' | 'about'

function routeFromPath(pathname: string): PortfolioRoute {
  if (pathname === '/projects' || pathname.startsWith('/projects/')) return 'projects'
  if (pathname === '/about' || pathname.startsWith('/about/')) return 'about'
  return 'home'
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => unknown
}

function transitionInterface(update: () => void) {
  const transitionDocument = document as ViewTransitionDocument
  if (!transitionDocument.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    update()
    return
  }
  transitionDocument.startViewTransition(() => flushSync(update))
}

const STORAGE_KEYS = {
  embedder: 'rag-playground:embedder',
  model: 'rag-playground:model',
  topK: 'rag-playground:v2:top-k',
  history: 'rag-playground:history-aware',
}

const PREVIEW_CHUNKS: RetrievedChunk[] = [
  {
    id: 'preview-resume',
    title: 'Resume',
    source: 'about-and-experience.md',
    content: 'Full-stack engineering, applied AI, education, and measurable internship experience.',
    score: 0.92,
  },
  {
    id: 'preview-projects',
    title: 'Projects',
    source: 'projects.md',
    content: 'Production projects spanning RAG, concurrent booking systems, and real-time chat.',
    score: 0.89,
  },
  {
    id: 'preview-case-study',
    title: 'RAG Engineering',
    source: 'rag-playground-case-study.md',
    content: 'Retrieval training, pgvector architecture, deployment tradeoffs, and verification.',
    score: 0.86,
  },
]

function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

function optionLabel(options: ModelOption[], id: string | null | undefined): string | undefined {
  if (!id) return undefined
  return options.find((option) => option.id === id)?.label
}

function storedChoice(key: string, options: ModelOption[], fallback: string): string {
  const stored = window.localStorage.getItem(key)
  return stored && options.some((option) => option.id === stored) ? stored : fallback
}

function updateAssistant(
  messages: ChatMessage[],
  messageId: string,
  update: (message: AssistantMessage) => AssistantMessage,
): ChatMessage[] {
  return messages.map((message) =>
    message.id === messageId && message.role === 'assistant' ? update(message) : message,
  )
}

function LoadingScreen({ error, onRetry }: { error?: string; onRetry: () => void }) {
  return (
    <div className="app-shell">
      <div className="background-art" aria-hidden="true">
        <span className="shape shape-one" />
        <span className="shape shape-two" />
        <span className="shape shape-three" />
      </div>
      <main className="load-state">
        <div className="load-orbit" aria-hidden="true">
          <span />
        </div>
        <p className="eyebrow">CONFIGURING RETRIEVAL GRAPH</p>
        <h1>{error ? 'The pipeline did not answer.' : 'Loading the model ladder…'}</h1>
        <p>{error ?? 'Fetching the live embedders and generation models from the API.'}</p>
        {error && (
          <button className="retry-button" type="button" onClick={onRetry}>
            Retry connection
          </button>
        )}
      </main>
    </div>
  )
}

type ModelControlsProps = {
  config: PlaygroundConfig
  embedderId: string
  modelId: string
  topK: number
  historyAware: boolean
  disabled: boolean
  compact?: boolean
  onEmbedderChange: (id: string) => void
  onModelChange: (id: string) => void
  onTopKChange: (value: number) => void
  onHistoryAwareChange: (value: boolean) => void
}

type ThemeSelectProps = {
  label: string
  options: ModelOption[]
  value: string
  disabled: boolean
  onChange: (id: string) => void
}

function ThemeSelect({ label, options, value, disabled, onChange }: ThemeSelectProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const selected = options.find((option) => option.id === value) ?? options[0]

  useEffect(() => {
    if (!open) return
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  return (
    <div className={`theme-select ${open ? 'is-open' : ''}`} ref={rootRef}>
      <span className="control-label">{label}:</span>
      <button
        className="select-trigger"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{selected?.label}</span>
        <svg viewBox="0 0 12 12" aria-hidden="true"><path d="m2.5 4.5 3.5 3 3.5-3" /></svg>
      </button>
      {open && (
        <div className="select-menu" role="listbox" aria-label={label}>
          {options.map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={option.id === value}
              key={option.id}
              onClick={() => {
                onChange(option.id)
                setOpen(false)
              }}
            >
              <span>{option.label}</span>
              <small>{option.description}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ModelControls({
  config,
  embedderId,
  modelId,
  topK,
  historyAware,
  disabled,
  compact = false,
  onEmbedderChange,
  onModelChange,
  onTopKChange,
  onHistoryAwareChange,
}: ModelControlsProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const advancedRef = useRef<HTMLDetailsElement>(null)
  const embedder = config.embedders.find((item) => item.id === embedderId)
  const panelTitleId = compact ? 'model-panel-title-compact' : 'model-panel-title'

  useEffect(() => {
    if (!advancedOpen) return

    const closeOutside = (event: PointerEvent) => {
      if (!advancedRef.current?.contains(event.target as Node)) setAdvancedOpen(false)
    }
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setAdvancedOpen(false)
    }

    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [advancedOpen])

  return (
    <section className={`model-panel ${compact ? 'is-compact' : ''}`} aria-labelledby={panelTitleId}>
      <h2 className="visually-hidden" id={panelTitleId}>Choose the route</h2>
      <div className="model-grid">
        <ThemeSelect
          label="Embedding"
          options={config.embedders}
          value={embedderId}
          disabled={disabled}
          onChange={onEmbedderChange}
        />
        <ThemeSelect
          label="LLM"
          options={config.llms}
          value={modelId}
          disabled={disabled}
          onChange={onModelChange}
        />
      </div>
      {compact && (
        <details className="route-advanced" open={advancedOpen} ref={advancedRef}>
          <summary
            aria-expanded={advancedOpen}
            onClick={(event) => {
              event.preventDefault()
              setAdvancedOpen((current) => !current)
            }}
          >
            <svg className="route-settings-icon" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3 4h10M3 12h10M5.5 2.5v3M10.5 10.5v3" />
            </svg>
            <span>Settings</span>
          </summary>
          <div className="advanced-content">
            <label>
              Context
              <select
                value={topK}
                onChange={(event) => onTopKChange(Number(event.target.value))}
                disabled={disabled}
              >
                {config.retrieval.selectableTopK.map((value) => (
                  <option key={value} value={value}>Top {value}</option>
                ))}
              </select>
            </label>
            <label className="advanced-toggle">
              <input
                type="checkbox"
                checked={historyAware}
                onChange={(event) => onHistoryAwareChange(event.target.checked)}
                disabled={disabled}
              />
              Use recent questions for follow-ups
            </label>
            {embedder && (
              <span className="optimization-readout">
                {embedder.optimization.portfolioTuned ? 'Fine-tuned' : 'Baseline'} ·{' '}
                {embedder.optimization.queryTransform} · threshold{' '}
                {embedder.optimization.minimumScore.toFixed(2)}
              </span>
            )}
          </div>
        </details>
      )}
    </section>
  )
}

function SourceCard({ chunk, index }: { chunk: RetrievedChunk; index: number }) {
  const preview = chunk.content
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)]\([^)]+\)/g, '$1')
    .replace(/\|/g, ' · ')
    .replace(/\s+/g, ' ')
    .trim()

  return (
    <article className="source-card">
      <div className="source-title">
        <svg className="source-number" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 3.5h7l4 4V20.5H7zM14 3.5v4h4M10 12h5M10 15.5h5" />
        </svg>
        <strong>{chunk.title}</strong>
      </div>
      <span className="source-file">Source: {chunk.source}</span>
      <p>{preview}</p>
      <footer className="source-meta">
        <span>Chunk {index + 1}</span>
        <strong aria-label={`Similarity score ${chunk.score.toFixed(2)}`}>
          Score: {chunk.score.toFixed(2)}
        </strong>
      </footer>
    </article>
  )
}

function RetrievedRail({
  chunks,
  embedding,
  pendingEmbedding,
  retrievalMs,
  emotions,
  collapsed = false,
  onToggle,
}: {
  chunks: RetrievedChunk[]
  embedding?: EmbeddingConfirmation
  pendingEmbedding?: string
  retrievalMs?: number
  emotions?: ConversationSignals['emotions']
  collapsed?: boolean
  onToggle?: () => void
}) {
  const visibleChunks = chunks
  const retrievalLabel = retrievalMs === undefined ? undefined : `${Math.round(retrievalMs)} ms retrieval`
  const confirmationLabel = embedding
    ? embedding.kind === 'jev'
      ? 'Retrieval confirmed'
      : embedding.fallbackFrom
        ? 'Jev unavailable · fallback'
        : 'Embedding confirmed'
    : pendingEmbedding
      ? 'Request received'
      : 'Ready for a query'
  const confirmationValue = embedding
    ? embedding.kind === 'jev'
      ? `${embedding.label} · read ${embedding.chunksRead ?? 0} chunks`
      : `${embedding.label} · ${embedding.vectorDimensions}D`
    : pendingEmbedding
      ? `${pendingEmbedding} · embedding queued`
      : 'Vector receipt appears here'

  const toggleOnPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    onToggle?.()
  }

  const toggleFromKeyboard = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    if (event.detail === 0) onToggle?.()
  }

  if (collapsed) {
    return (
      <aside className="source-rail is-collapsed" aria-label="Retrieved evidence">
        <button
          className="evidence-rail-toggle"
          type="button"
          onPointerDown={toggleOnPointerDown}
          onClick={toggleFromKeyboard}
          aria-expanded="false"
          aria-label={`Show ${visibleChunks.length} retrieved chunks`}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M3.5 5.5c3-.8 5.8-.2 8.5 1.7v12c-2.7-1.9-5.5-2.5-8.5-1.7zM20.5 5.5c-3-.8-5.8-.2-8.5 1.7v12c2.7-1.9 5.5-2.5 8.5-1.7z" />
          </svg>
          <span className="rail-toggle-copy">
            <strong>Open to see retrieved chunks</strong>
            <small>
              {visibleChunks.length} {visibleChunks.length === 1 ? 'chunk' : 'chunks'}
              {retrievalLabel ? ` · ${retrievalLabel}` : ''}
            </small>
          </span>
          <svg className="rail-chevron" viewBox="0 0 12 12" aria-hidden="true"><path d="m4 2.5 3.5 3.5L4 9.5" /></svg>
        </button>
      </aside>
    )
  }

  return (
    <aside className={`source-rail ${onToggle ? 'is-expanded' : ''}`} aria-label="Retrieved chunks">
      <div className={`embedding-confirmation ${embedding ? 'is-confirmed' : ''}`} role="status">
        <span aria-hidden="true" />
        <div>
          <small>{confirmationLabel}</small>
          <strong>{confirmationValue}</strong>
        </div>
      </div>
      {emotions && emotions.length > 0 && (
        <div className="emotion-reading" role="status">
          <small>Visitor emotion</small>
          <EmotionTags emotions={emotions} />
        </div>
      )}
      <header className="rail-heading">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3.5 5.5c3-.8 5.8-.2 8.5 1.7v12c-2.7-1.9-5.5-2.5-8.5-1.7zM20.5 5.5c-3-.8-5.8-.2-8.5 1.7v12c2.7-1.9 5.5-2.5 8.5-1.7z" />
        </svg>
        <h2>Retrieved chunks</h2>
        {retrievalLabel && <span className="retrieval-time">{retrievalLabel}</span>}
        {onToggle && (
          <button
            className="evidence-close"
            type="button"
            onPointerDown={toggleOnPointerDown}
            onClick={toggleFromKeyboard}
            aria-label="Collapse retrieved chunks"
          >
            <svg viewBox="0 0 12 12" aria-hidden="true"><path d="m8 2.5-3.5 3.5L8 9.5" /></svg>
          </button>
        )}
      </header>
      <div className="source-list">
        {visibleChunks.map((chunk, index) => (
          <SourceCard key={`${chunk.id ?? chunk.source}-${index}`} chunk={chunk} index={index} />
        ))}
        {visibleChunks.length === 0 && <p className="source-empty">Evidence will appear when retrieval completes.</p>}
      </div>
    </aside>
  )
}

const INTENT_LABELS: Record<ConversationSignals['intent'], string> = {
  facts: 'Factual',
  judgment: 'Evaluative',
  challenge: 'Challenging',
  contact: 'Contact',
  small_talk: 'Small talk',
  off_topic: 'Off-topic',
  manipulation: 'Manipulation',
}
const COVERAGE_LABELS: Record<ConversationSignals['coverage'], string> = {
  direct: 'In portfolio',
  partial: 'Partly in portfolio',
  none: 'Not in portfolio',
}

const confidence = (value: number) => `Jev · ${Math.round(value * 100)}% confident`

// Jev reads each visitor message on its own request: what they want, how they sound,
// whether the portfolio covers it, and how the conversation is going so far.
function AnswerSignals({ signals }: { signals: ConversationSignals }) {
  const mood = signals.mood < 0.35 ? 'low' : signals.mood < 0.65 ? 'mid' : 'high'
  const moodLabel = mood === 'low' ? 'going badly' : mood === 'mid' ? 'neutral' : 'going well'
  return (
    <span className="answer-signals" aria-label="Conversation signals from Jev">
      <span className="signal-chip" title={confidence(signals.intentConfidence)}>
        {INTENT_LABELS[signals.intent]}
      </span>
      <span className={`signal-chip coverage-${signals.coverage}`} title={`Jev · ${Math.round(signals.noneProbability * 100)}% not covered`}>
        {COVERAGE_LABELS[signals.coverage]}
      </span>
      <span className={`signal-mood mood-${mood}`} title={`Chat mood: ${moodLabel}`} aria-label={`Chat mood: ${moodLabel}`}>
        Mood
        <i aria-hidden="true"><b style={{ width: `${Math.max(6, signals.mood * 100)}%` }} /></i>
      </span>
    </span>
  )
}

// The emotions Jev read in the visitor's latest message.
function EmotionTags({ emotions }: { emotions: ConversationSignals['emotions'] }) {
  return (
    <span className="emotion-tags" aria-label={`Jev read: ${emotions.map((e) => e.name).join(' and ')}`}>
      {emotions.map((emotion) => (
        <span
          className="emotion-tag"
          key={emotion.name}
          style={{ '--emotion': emotionColor(emotion.name) } as CSSProperties}
          title={`Jev · ${Math.round(emotion.probability * 100)}%`}
        >
          <i aria-hidden="true" />
          {emotion.name[0].toUpperCase() + emotion.name.slice(1)}
        </span>
      ))}
    </span>
  )
}

function AssistantAnswer({ message, onShowSources }: { message: AssistantMessage; onShowSources?: () => void }) {
  const isWorking = message.status === 'retrieving' || message.status === 'streaming'
  const servedLabel =
    message.servedModelLabel ??
    (message.status === 'complete' && !message.servedModelId ? 'Local corpus guard' : 'Awaiting provider')

  return (
    <article className={`message assistant-message is-${message.status}`} aria-label="RAG answer">
      <div className="assistant-orb" aria-hidden="true">✧</div>
      <div className="assistant-content">
        <div className="answer-copy" aria-live="polite" aria-busy={isWorking}>
          {message.content ? (
            <>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              {isWorking && <span className="stream-cursor" aria-hidden="true" />}
            </>
          ) : message.status === 'error' ? null : (
            <div className="thinking-line">
              <span />
              <span />
              <span />
              <em>Searching Yash&apos;s corpus</em>
            </div>
          )}
          {message.error && (
            <div className="answer-error" role="alert">
              <strong>Request stopped</strong>
              <span>{message.error}</span>
            </div>
          )}
        </div>
        <div className="message-meta">
          <span>{servedLabel}{message.fallbackUsed ? ' · fallback' : ''}</span>
          <span>
            {message.latencies.totalMs === undefined
              ? message.status === 'complete' ? 'Complete' : 'Working…'
              : `${Math.round(message.latencies.totalMs)} ms`}
          </span>
        </div>
        {message.chunks.length > 0 && onShowSources && (
          <button className="answer-sources" type="button" onClick={onShowSources}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3.5 5.5c3-.8 5.8-.2 8.5 1.7v12c-2.7-1.9-5.5-2.5-8.5-1.7zM20.5 5.5c-3-.8-5.8-.2-8.5 1.7v12c2.7-1.9 5.5-2.5 8.5-1.7z" />
            </svg>
            {message.chunks.length} sources · {message.chunks[0]?.score.toFixed(2)}
          </button>
        )}
        {message.signals && <AnswerSignals signals={message.signals} />}
      </div>
    </article>
  )
}

function ChatTranscript({ messages, onShowSources }: { messages: ChatMessage[]; onShowSources?: () => void }) {
  if (messages.length === 0) {
    return (
      <div className="transcript demo-transcript">
        <article className="message user-message" aria-label="Example question">
          <p>What kind of work do you do?</p>
        </article>
        <article className="message assistant-message" aria-label="Example answer">
          <div className="assistant-orb" aria-hidden="true">✧</div>
          <div className="assistant-content">
            <div className="answer-copy">
              <p>
                I&apos;m a full-stack developer focused on clean product engineering, real-time systems,
                search, analytics, and applied AI.
              </p>
            </div>
            <div className="message-meta">
              <span>Portfolio corpus</span>
              <span>Ready</span>
            </div>
          </div>
        </article>
      </div>
    )
  }

  return (
    <div className="transcript">
      {messages.map((message) =>
        message.role === 'user' ? (
          <article className="message user-message" key={message.id} aria-label="Your question">
            <p>{message.content}</p>
          </article>
        ) : (
          <AssistantAnswer key={message.id} message={message} onShowSources={onShowSources} />
        ),
      )}
    </div>
  )
}

type ComposerProps = {
  value: string
  disabled: boolean
  expanded: boolean
  onChange: (value: string) => void
  onSubmit: () => void
  onEngage: () => void
  inputRef: React.RefObject<HTMLTextAreaElement | null>
}

function Composer({ value, disabled, expanded, onChange, onSubmit, onEngage, inputRef }: ComposerProps) {
  const canSubmit = value.trim().length >= 2 && !disabled

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (canSubmit) onSubmit()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (canSubmit) onSubmit()
    }
  }

  return (
    <form className="composer" onSubmit={submit} aria-label="Ask Yash's portfolio">
      <label className="visually-hidden" htmlFor="question-input">Ask about Yash</label>
      {!expanded && (
        <button
          className="chat-mode-invite"
          type="button"
          aria-label="Enter chat mode"
          onClick={() => {
            onEngage()
            inputRef.current?.focus()
          }}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 3v14M6.5 11.5 12 17l5.5-5.5" />
          </svg>
        </button>
      )}
      <div className="composer-input">
        <textarea
          id="question-input"
          ref={inputRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onPointerDown={onEngage}
          onFocus={onEngage}
          placeholder={expanded ? 'Ask about my work…' : 'Ask a question to begin…'}
          rows={1}
          maxLength={QUESTION_LIMIT}
          disabled={disabled}
          aria-describedby={expanded ? 'composer-help composer-count composer-notice' : 'composer-help composer-count'}
        />
        <button type="submit" disabled={!canSubmit} aria-label="Send question">
          <span className="visually-hidden">{disabled ? 'Working' : 'Send'}</span>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M21 3 10.5 13.5M21 3l-6.8 18-3.7-7.5L3 9.8 21 3Z" />
          </svg>
        </button>
      </div>
      {expanded && (
        <p id="composer-notice" className="composer-notice">
          Questions and answers are saved to improve this portfolio.
        </p>
      )}
      <div className="composer-meta">
        <span id="composer-help">Enter to send · Shift + Enter for a new line</span>
        <span id="composer-count" className={value.length > QUESTION_LIMIT * 0.9 ? 'near-limit' : ''}>
          {value.length}/{QUESTION_LIMIT}
        </span>
      </div>
    </form>
  )
}

function App() {
  const [route, setRoute] = useState<PortfolioRoute>(() => routeFromPath(window.location.pathname))
  const [config, setConfig] = useState<PlaygroundConfig | null>(null)
  const [configError, setConfigError] = useState<string>()
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [embedderId, setEmbedderId] = useState('')
  const [modelId, setModelId] = useState('')
  const [topK, setTopK] = useState(3)
  const [historyAware, setHistoryAware] = useState(true)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const chatScrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const activeRequest = useRef<AbortController | null>(null)

  const navigate = useCallback((path: string) => {
    const destination = new URL(path, window.location.origin)
    const nextRoute = routeFromPath(destination.pathname)

    transitionInterface(() => {
      window.history.pushState({}, '', `${destination.pathname}${destination.search}${destination.hash}`)
      setRoute(nextRoute)
    })

    window.setTimeout(() => {
      if (nextRoute !== 'home') {
        document.querySelector<HTMLElement>('.route-page-shell')?.scrollTo({ top: 0, behavior: 'auto' })
        return
      }
      const portfolio = document.querySelector<HTMLElement>('.portfolio-site')
      const target = destination.hash ? document.getElementById(destination.hash.slice(1)) : null
      if (portfolio && target) {
        portfolio.scrollTo({ top: target.offsetTop, behavior: 'smooth' })
      } else {
        portfolio?.scrollTo({ top: 0, behavior: 'auto' })
      }
    }, 60)
  }, [])

  useEffect(() => {
    const syncRoute = () => setRoute(routeFromPath(window.location.pathname))
    window.addEventListener('popstate', syncRoute)
    return () => window.removeEventListener('popstate', syncRoute)
  }, [])

  useEffect(() => {
    document.title = route === 'projects'
      ? 'Projects · Yash Khambhatta'
      : route === 'about'
        ? 'About · Yash Khambhatta'
        : 'Yash Khambhatta · Portfolio'

    if (route !== 'home' || !window.location.hash) return
    const timer = window.setTimeout(() => {
      const portfolio = document.querySelector<HTMLElement>('.portfolio-site')
      const target = document.getElementById(window.location.hash.slice(1))
      if (portfolio && target) portfolio.scrollTop = target.offsetTop
    }, 0)
    return () => window.clearTimeout(timer)
  }, [route])

  useEffect(() => {
    const controller = new AbortController()

    void getConfig(controller.signal)
      .then((nextConfig) => {
        const nextEmbedder = storedChoice(
          STORAGE_KEYS.embedder,
          nextConfig.embedders,
          nextConfig.defaults.embedder,
        )
        const nextModel = storedChoice(STORAGE_KEYS.model, nextConfig.llms, nextConfig.defaults.llm)
        setConfig(nextConfig)
        setEmbedderId(nextEmbedder)
        setModelId(nextModel)
        const savedTopK = Number(window.localStorage.getItem(STORAGE_KEYS.topK))
        setTopK(nextConfig.retrieval.selectableTopK.includes(savedTopK) ? savedTopK : nextConfig.retrieval.topK)
        setHistoryAware(window.localStorage.getItem(STORAGE_KEYS.history) !== 'false')
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setConfigError(error instanceof Error ? error.message : 'The model configuration could not be loaded.')
      })

    return () => controller.abort()
  }, [loadAttempt])

  useEffect(() => {
    const chatScroll = chatScrollRef.current
    chatScroll?.scrollTo({
      top: chatScroll.scrollHeight,
      behavior: isStreaming ? 'smooth' : 'auto',
    })
  }, [messages, isStreaming])

  useEffect(
    () => () => {
      activeRequest.current?.abort()
    },
    [],
  )

  const selectedEmbedder = useMemo(
    () => config?.embedders.find((item) => item.id === embedderId),
    [config, embedderId],
  )
  const selectedModel = useMemo(
    () => config?.llms.find((item) => item.id === modelId),
    [config, modelId],
  )
  const latestAssistant = useMemo(
    () =>
      messages.reduce<AssistantMessage | undefined>(
        (latest, message) => (message.role === 'assistant' ? message : latest),
        undefined,
      ),
    [messages],
  )
  const hasConversation = messages.length > 0
  const railChunks = latestAssistant && latestAssistant.chunks.length > 0
    ? latestAssistant.chunks
    : hasConversation ? [] : PREVIEW_CHUNKS

  const openWorkspace = useCallback(() => {
    if (workspaceOpen) return
    setWorkspaceOpen(true)
    setEvidenceOpen(false)
  }, [workspaceOpen])

  useEffect(() => {
    if (!workspaceOpen) return

    const portfolio = document.querySelector<HTMLElement>('.portfolio-site')
    const playground = document.getElementById('playground')
    if (!portfolio || !playground) return

    const pinPlayground = () => {
      portfolio.scrollTop = playground.offsetTop
    }
    pinPlayground()
    const animationFrame = window.requestAnimationFrame(pinPlayground)
    const transitionTimer = window.setTimeout(pinPlayground, 540)

    return () => {
      window.cancelAnimationFrame(animationFrame)
      window.clearTimeout(transitionTimer)
    }
  }, [evidenceOpen, workspaceOpen])

  useEffect(() => {
    if (!workspaceOpen || question.trim() || messages.length > 0 || isStreaming) return

    const collapseEmptyWorkspace = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null
      if (target?.closest('.portfolio-card')) return
      inputRef.current?.blur()
      if (chatScrollRef.current) chatScrollRef.current.scrollTop = 0
      setWorkspaceOpen(false)
      setEvidenceOpen(false)
    }

    document.addEventListener('pointerdown', collapseEmptyWorkspace)
    return () => document.removeEventListener('pointerdown', collapseEmptyWorkspace)
  }, [isStreaming, messages.length, question, workspaceOpen])



  const clearChat = useCallback(() => {
    activeRequest.current?.abort()
    activeRequest.current = null
    inputRef.current?.blur()
    if (chatScrollRef.current) chatScrollRef.current.scrollTop = 0
    setMessages([])
    setQuestion('')
    setIsStreaming(false)
    setWorkspaceOpen(false)
    setEvidenceOpen(false)
  }, [])

  const toggleEvidence = useCallback(() => {
    setEvidenceOpen((open) => !open)
  }, [])

  const chooseEmbedder = useCallback((id: string) => {
    setEmbedderId(id)
    window.localStorage.setItem(STORAGE_KEYS.embedder, id)
  }, [])

  const chooseModel = useCallback((id: string) => {
    setModelId(id)
    window.localStorage.setItem(STORAGE_KEYS.model, id)
  }, [])

  const chooseTopK = useCallback((value: number) => {
    setTopK(value)
    window.localStorage.setItem(STORAGE_KEYS.topK, String(value))
  }, [])

  const chooseHistoryAware = useCallback((value: boolean) => {
    setHistoryAware(value)
    window.localStorage.setItem(STORAGE_KEYS.history, String(value))
  }, [])

  const submitQuestion = useCallback(async () => {
    const cleanQuestion = question.trim().replace(/\s+/g, ' ')
    if (
      !config ||
      !selectedEmbedder ||
      !selectedModel ||
      cleanQuestion.length < 2 ||
      isStreaming
    ) {
      return
    }

    const history: HistoryItem[] = messages
      .filter((message) => message.content.trim())
      .slice(-6)
      .map((message) => ({ role: message.role, content: message.content.slice(0, 700) }))
    const userMessage: ChatMessage = {
      id: newId('user'),
      role: 'user',
      content: cleanQuestion,
    }
    const answerId = newId('answer')
    const assistantMessage: AssistantMessage = {
      id: answerId,
      role: 'assistant',
      content: '',
      status: 'retrieving',
      embedderId,
      embedderLabel: selectedEmbedder.label,
      topK,
      historyAware,
      requestedModelId: modelId,
      requestedModelLabel: selectedModel.label,
      fallbackUsed: false,
      attempts: [],
      chunks: [],
      latencies: {},
    }
    const controller = new AbortController()
    activeRequest.current = controller
    setWorkspaceOpen(true)
    setEvidenceOpen(false)
    setQuestion('')
    setIsStreaming(true)
    setMessages((current) => [...current, userMessage, assistantMessage])
    let terminalEventSeen = false

    const handleEvent = (event: StreamEvent) => {
      if (event.type === 'done' || event.type === 'error') terminalEventSeen = true
      if (event.type === 'sources') setEvidenceOpen(true)
      setMessages((current) =>
        updateAssistant(current, answerId, (answer) => {
          switch (event.type) {
            case 'meta':
              return { ...answer, requestId: event.requestId }
            case 'embedding':
              return {
                ...answer,
                embedding: {
                  embedder: event.embedder,
                  label: event.label,
                  kind: event.kind,
                  dimensions: event.dimensions,
                  vectorDimensions: event.vectorDimensions,
                  embeddingMs: event.embeddingMs,
                  chunksRead: event.chunksRead,
                  fallbackFrom: event.fallbackFrom,
                },
                latencies: { ...answer.latencies, embeddingMs: event.embeddingMs },
              }
            case 'sources':
              return { ...answer, chunks: event.chunks, latencies: event.latencies }
            case 'model':
              return {
                ...answer,
                status: 'streaming',
                servedModelId: event.servedModel,
                servedModelLabel: optionLabel(config.llms, event.servedModel) ?? event.servedModel,
                fallbackUsed: event.fallbackUsed,
                attempts: event.attempts,
              }
            case 'signals':
              return {
                ...answer,
                signals: {
                  intent: event.intent,
                  intentConfidence: event.intentConfidence,
                  emotions: event.emotions,
                  mood: event.mood,
                  coverage: event.coverage,
                  noneProbability: event.noneProbability,
                },
              }
            case 'token':
              return { ...answer, status: 'streaming', content: answer.content + event.token }
            case 'done':
              return {
                ...answer,
                status: 'complete',
                requestId: event.requestId,
                servedModelId: event.servedModel,
                servedModelLabel:
                  optionLabel(config.llms, event.servedModel) ??
                  event.servedModel ??
                  answer.servedModelLabel,
                fallbackUsed: event.fallbackUsed,
                attempts: event.attempts,
                latencies: event.latencies,
              }
            case 'error':
              return { ...answer, status: 'error', error: event.message }
            case 'usage':
              return answer
            default:
              // Newer servers may add event types; an unknown one must never drop the answer.
              return answer
          }
        }),
      )
    }

    try {
      await streamChat(
        {
          question: cleanQuestion,
          embedder: embedderId,
          model: modelId,
          history,
          topK,
          useHistory: historyAware,
        },
        handleEvent,
        controller.signal,
      )
      if (!terminalEventSeen) {
        setMessages((current) =>
          updateAssistant(current, answerId, (answer) => ({
            ...answer,
            status: 'error',
            error: 'The answer stream ended before the pipeline sent its completion signal.',
          })),
        )
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      const message =
        error instanceof ApiError || error instanceof Error
          ? error.message
          : 'The request could not be completed.'
      setMessages((current) =>
        updateAssistant(current, answerId, (answer) => ({ ...answer, status: 'error', error: message })),
      )
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null
        setIsStreaming(false)
        window.setTimeout(() => inputRef.current?.focus(), 0)
      }
    }
  }, [
    config,
    embedderId,
    historyAware,
    isStreaming,
    messages,
    modelId,
    question,
    selectedEmbedder,
    selectedModel,
    topK,
  ])

  if (route === 'projects') {
    return <div className="route-page-shell"><AllProjectsSection onNavigate={navigate} /></div>
  }

  if (route === 'about') {
    return <div className="route-page-shell"><AboutSection onNavigate={navigate} /></div>
  }

  return (
    <div className="portfolio-site">
      <SectionNavigator />
      <LandingSection onNavigate={navigate} />
      <WorkSection onNavigate={navigate} />
      <section className="portfolio-section rag-section" id="playground" aria-label="Interactive RAG playground">
        {config ? (
          <div className={`app-shell ${workspaceOpen ? 'is-active' : ''}`}>
          <div className="background-art" aria-hidden="true">
            <span className="shape shape-one" />
            <span className="shape shape-two" />
            <span className="shape shape-three" />
          </div>
          <main className={`portfolio-card ${workspaceOpen ? 'is-active' : ''} ${evidenceOpen ? 'evidence-open' : ''}`}>
        <section
          className={`chat-column ${workspaceOpen ? 'is-active' : ''}`}
          aria-labelledby="page-title-chat"
        >
          <div className="header-stage">
            <header className={`chat-header ${workspaceOpen ? 'is-active' : ''}`}>
              <div className="chat-heading">
                <span className="sparkle-mark" aria-hidden="true">✦</span>
                <h1 id="page-title-chat">Chat with <em>my portfolio</em></h1>
              </div>
              <p className="chat-subtitle">I use AI + RAG to answer from my résumé, projects, and experience.</p>
              <ModelControls
                compact={workspaceOpen}
                config={config}
                embedderId={embedderId}
                modelId={modelId}
                topK={topK}
                historyAware={historyAware}
                disabled={isStreaming}
                onEmbedderChange={chooseEmbedder}
                onModelChange={chooseModel}
                onTopKChange={chooseTopK}
                onHistoryAwareChange={chooseHistoryAware}
              />
              <button
                className={`clear-chat ${workspaceOpen ? 'is-active' : ''}`}
                type="button"
                aria-label="Clear chat"
                onClick={clearChat}
                disabled={messages.length === 0 && !question}
              >
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M3 8a5 5 0 1 0 1.45-3.53M3 3.5v3h3" />
                </svg>
                <span>Clear chat</span>
              </button>
            </header>
          </div>
          <div className="chat-scroll" ref={chatScrollRef}>
            <ChatTranscript messages={messages} onShowSources={() => transitionInterface(() => setEvidenceOpen(true))} />
          </div>
          <Composer
            value={question}
            disabled={isStreaming}
            expanded={workspaceOpen}
            onChange={setQuestion}
            onSubmit={() => void submitQuestion()}
            onEngage={openWorkspace}
            inputRef={inputRef}
          />
        </section>
            <RetrievedRail
              chunks={railChunks}
              embedding={latestAssistant?.embedding}
              pendingEmbedding={latestAssistant && !latestAssistant.embedding ? latestAssistant.embedderLabel : undefined}
              retrievalMs={latestAssistant?.latencies.retrievalMs}
              emotions={latestAssistant?.signals?.emotions}
              collapsed={!evidenceOpen}
              onToggle={toggleEvidence}
            />
          </main>
          </div>
        ) : (
          <LoadingScreen
            error={configError}
            onRetry={() => {
              setConfigError(undefined)
              setLoadAttempt((attempt) => attempt + 1)
            }}
          />
        )}
      </section>
    </div>
  )
}

export default App
