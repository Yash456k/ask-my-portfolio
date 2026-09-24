export type ProjectItem = {
  id: string
  number: string
  date: string
  startedOn: string
  title: string
  eyebrow: string
  role: string
  summary: string
  detail: string
  highlights: readonly string[]
  metrics: readonly string[]
  tags: readonly string[]
  href: string
  repository: string
  linkLabel: string
  external: boolean
}
