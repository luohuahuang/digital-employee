import { createContext, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  const [dark, setDarkState] = useState(() => {
    try { return localStorage.getItem('de_theme') !== 'light' } catch { return true }
  })

  useEffect(() => {
    const root = document.documentElement
    if (dark) root.classList.add('dark')
    else root.classList.remove('dark')
  }, [dark])

  function setDark(val) {
    setDarkState(val)
    try { localStorage.setItem('de_theme', val ? 'dark' : 'light') } catch {}
  }

  return <ThemeContext.Provider value={{ dark, setDark }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}
