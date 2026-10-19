import type { Row } from './types'
export function currentLocalDateLabel(): string
export function formatClock(value: unknown): string
export function formatDateTime(value: unknown): string
export function formatAge(value: unknown): string
export function formatBytes(value: unknown): string
export function formatDuration(value: unknown): string
export function draftCategoryLabel(value: unknown): string
export function draftDateKey(value: unknown): string
export function ageFromTime(value: unknown): string
export function stageClass(value: unknown): string
export function currentProjectPipeline(
  payload: Row,
  status: Row,
): Record<string, Row> | null
export function categoryFor(value: unknown): string
export function step5FilterKey(item: Row): string
export function runtimeFacts(
  services: Row[],
  status: Row,
): {
  known: boolean
  workbench: boolean
  voice: boolean
  capcut: boolean
  downloading: boolean
  projectRunning: boolean
  projectLabel: string
  offline: boolean
  busy: boolean
}
export function nextActionFor(
  status: Row,
): { title: string; reasons: string[]; action: string } | null
export function describeSourceErrors(errors: Row[]): string[]
export function audioIdentity(item: Row): string
export function productionIdentity(item: Row): string
export function safetyEntries(
  data: Row,
): { title: string; text: string; tone: string }[]
