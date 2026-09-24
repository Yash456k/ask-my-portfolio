export type ModelOption = {
  id: string
  label: string
  description: string
  provider?: 'groq' | 'openrouter'
}

export type EmbedderOption = ModelOption & {
  kind?: 'embedding' | 'jev'
  dimensions: number
  optimization: {
    portfolioTuned: boolean
    queryTransform: string
    minimumScore: number
  }
}

export type PlaygroundConfig = {
  version: number
  defaults: {
    embedder: string
    llm: string
  }
  embedders: EmbedderOption[]
  llms: ModelOption[]
  retrieval: {
    topK: number
    selectableTopK: number[]
    historyAware: boolean
  }
}

export type HistoryItem = {
  role: 'user' | 'assistant'
  content: string
}

export type RetrievedChunk = {
  id?: string | number
  title: string
  source: string
  content: string
  score: number
}

export type EmbeddingConfirmation = {
  embedder: string
  kind?: 'embedding' | 'jev'
  label: string
  dimensions: number
  vectorDimensions: number
  embeddingMs: number
  chunksRead?: number
  fallbackFrom?: string
}

export type Latencies = {
  embeddingMs?: number
  retrievalMs?: number
  firstTokenMs?: number
  generationMs?: number
  totalMs?: number
}

export type FallbackAttempt = {
  model?: string
  reason?: string
  status?: number
  [key: string]: unknown
}

export type ConversationSignals = {
  intent: 'facts' | 'judgment' | 'challenge' | 'contact' | 'small_talk' | 'off_topic' | 'manipulation'
  intentConfidence: number
  tone: 'curious' | 'neutral' | 'impressed' | 'skeptical' | 'frustrated' | 'hostile'
  toneConfidence: number
  mood: number
  coverage: 'direct' | 'partial' | 'none'
  noneProbability: number
}

export type StreamEvent =
  | {
      type: 'meta'
      requestId: string
      embedder: string
      requestedModel: string
      requestReceived: {
        embedder: string
        model: string
        topK: number
        historyAware: boolean
      }
    }
  | ({ type: 'embedding' } & EmbeddingConfirmation)
  | {
      type: 'sources'
      chunks: RetrievedChunk[]
      latencies: Latencies
    }
  | {
      type: 'model'
      servedModel: string
      fallbackUsed: boolean
      attempts: FallbackAttempt[]
    }
  | ({ type: 'signals' } & ConversationSignals)
  | { type: 'token'; token: string }
  | { type: 'usage'; usage: unknown }
  | {
      type: 'done'
      requestId: string
      requestedModel: string
      servedModel: string | null
      fallbackUsed: boolean
      attempts: FallbackAttempt[]
      latencies: Latencies
    }
  | { type: 'error'; code: string; message: string }

export type UserMessage = {
  id: string
  role: 'user'
  content: string
}

export type AssistantMessage = {
  id: string
  role: 'assistant'
  content: string
  status: 'retrieving' | 'streaming' | 'complete' | 'error'
  embedderId: string
  embedderLabel: string
  topK: number
  historyAware: boolean
  requestedModelId: string
  requestedModelLabel: string
  servedModelId?: string | null
  servedModelLabel?: string
  fallbackUsed: boolean
  attempts: FallbackAttempt[]
  chunks: RetrievedChunk[]
  latencies: Latencies
  embedding?: EmbeddingConfirmation
  signals?: ConversationSignals
  requestId?: string
  error?: string
}

export type ChatMessage = UserMessage | AssistantMessage
