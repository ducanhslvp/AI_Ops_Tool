import { useSyncExternalStore } from 'react'

const DESKTOP_QUERY = '(min-width: 1024px)'

export function useIsDesktop() {
  return useSyncExternalStore(
    (callback) => {
      const mediaQuery = window.matchMedia(DESKTOP_QUERY)
      mediaQuery.addEventListener('change', callback)
      return () => mediaQuery.removeEventListener('change', callback)
    },
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => false
  )
}
