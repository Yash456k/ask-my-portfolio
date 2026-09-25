export type ProjectItem = {
  id: string
  number: string
  date: string
  startedOn: string
  title: string
  eyebrow: string
  oneLiner: string
  description: string
  hooks: readonly string[]
  points: readonly string[]
  tags: readonly string[]
  href: string
  repository: string
  linkLabel: string
  external: boolean
}
