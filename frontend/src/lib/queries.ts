import { useQuery } from '@tanstack/react-query'
import { api } from './api'

export const keys = {
  overview: ['overview'] as const,
  cases: ['cases'] as const,
  case: (id: string) => ['case', id] as const,
  replay: (id: string) => ['case', id, 'replay'] as const,
  challenges: (id: string) => ['case', id, 'challenges'] as const,
  monitoring: ['monitoring'] as const,
  rings: ['rings'] as const,
  ring: (id: number) => ['ring', id] as const,
  containment: ['containment'] as const,
  evaluation: ['evaluation'] as const,
}

export const useOverview = () => useQuery({ queryKey: keys.overview, queryFn: api.overview })
export const useCases = () => useQuery({ queryKey: keys.cases, queryFn: api.cases })
export const useCase = (id: string | undefined) =>
  useQuery({ queryKey: keys.case(id ?? ''), queryFn: () => api.case(id!), enabled: !!id })
export const useReplay = (id: string) => useQuery({ queryKey: keys.replay(id), queryFn: () => api.replay(id), retry: false })
export const useChallenges = (id: string) => useQuery({ queryKey: keys.challenges(id), queryFn: () => api.challenges(id) })
export const useMonitoring = () => useQuery({ queryKey: keys.monitoring, queryFn: api.monitoring })
export const useRings = () => useQuery({ queryKey: keys.rings, queryFn: api.rings, retry: false })
export const useRing = (id: number | null) =>
  useQuery({ queryKey: keys.ring(id ?? -1), queryFn: () => api.ring(id!), enabled: id != null })
export const useContainment = () => useQuery({ queryKey: keys.containment, queryFn: api.containment, retry: false })
export const useEvaluation = () => useQuery({ queryKey: keys.evaluation, queryFn: api.evaluation })
