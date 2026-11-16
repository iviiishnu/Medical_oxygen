import React, { createContext, useContext } from 'react';
import type { ThemePalette } from './colors';

const ThemeContext = createContext<ThemePalette | null>(null);

export const ThemeProvider = ThemeContext.Provider;

export function useThemeColors(fallback: ThemePalette): ThemePalette {
  return useContext(ThemeContext) ?? fallback;
}
