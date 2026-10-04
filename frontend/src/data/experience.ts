export type ExperienceItem = {
  id: string
  year: string
  period: string
  // ISO dates the timeline draws the role across. No end means it is still going.
  start: string
  end?: string
  title: string
  organization: string
  label: string
  summary: string
  detail: string
  proof: readonly { value: string; label: string }[]
  current?: boolean
}

export const experienceItems: readonly ExperienceItem[] = [
  {
    id: 'aivid-fulltime',
    year: '2026',
    period: 'Mar 2026 — Present',
    start: '2026-03-01',
    title: 'Full-stack engineer',
    organization: 'AIVID Techvision',
    label: 'The next chapter',
    summary: 'From shipping features to owning systems.',
    detail: 'Joined in March as an intern. Converted full-time in June. Now working across frontend systems, backend services, platform reliability, and developer experience.',
    proof: [
      { value: 'Mar → Jun', label: 'Intern to full-time' },
      { value: 'End to end', label: 'Product engineering' },
    ],
    current: true,
  },
  {
    id: 'graduation',
    year: '2026',
    period: 'Graduated Jun 2026',
    start: '2022-07-01',
    end: '2026-06-30',
    title: 'B.Tech, Computer Engineering',
    organization: 'Indus University',
    label: 'The foundation',
    summary: 'Learning the theory. Building beyond it.',
    detail: 'Completed my degree while building and shipping production software. The classroom supplied the foundations; real projects put them to work.',
    proof: [
      { value: '9.66 / 10', label: 'Graduating CGPA' },
      { value: '2022–26', label: 'Computer Engineering' },
    ],
  },
  {
    id: 'aivid-internship',
    year: '2024',
    period: 'Sep 2024 — Sep 2025',
    start: '2024-09-01',
    end: '2025-09-30',
    title: 'Full-stack intern',
    organization: 'AIVID Techvision',
    label: 'Into production',
    summary: 'Real users. Real scale. A lot of firsts.',
    detail: 'Built a notification platform, Microsoft Graph workflows, analytics APIs, and shared React systems. My first year turning engineering fundamentals into software people rely on.',
    proof: [
      { value: '100K+', label: 'Analytics records / day' },
      { value: '1,000+', label: 'Roles served / day' },
    ],
  },
]
