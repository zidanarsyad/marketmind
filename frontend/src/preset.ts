// PrimeVue Aura, recoloured to the palette of MarketMind's charts (marketmind/reporting/charts.py): the chart blue as
// the primary colour and warm neutral greys as surfaces, so components, charts and the HTML report read as one system.
import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'

const blue = {
  50: '#eef5fd',
  100: '#cde2fb',
  200: '#9ec5f4',
  300: '#6da7ec',
  400: '#3987e5',
  500: '#2a78d6',
  600: '#256abf',
  700: '#184f95',
  800: '#0d366b',
  900: '#0a2a54',
  950: '#061a35',
}

export const MarketMindPreset = definePreset(Aura, {
  semantic: {
    primary: blue,
    colorScheme: {
      light: {
        surface: {
          0: '#ffffff',
          50: '#fcfcfb',
          100: '#f3f2ee',
          200: '#e1e0d9',
          300: '#c3c2b7',
          400: '#a3a29a',
          500: '#898781',
          600: '#6b6a65',
          700: '#52514e',
          800: '#383835',
          900: '#222221',
          950: '#0b0b0b',
        },
        primary: { color: '{primary.600}', contrastColor: '#ffffff', hoverColor: '{primary.700}', activeColor: '{primary.800}' },
        highlight: { background: '{primary.50}', focusBackground: '{primary.100}', color: '{primary.700}', focusColor: '{primary.800}' },
        text: { color: '{surface.800}', hoverColor: '{surface.950}', mutedColor: '{surface.500}', hoverMutedColor: '{surface.600}' },
      },
      dark: {
        surface: {
          0: '#ffffff',
          50: '#f0efec',
          100: '#e1e0d9',
          200: '#c3c2b7',
          300: '#a3a29a',
          400: '#898781',
          500: '#6b6a65',
          600: '#52514e',
          700: '#383835',
          800: '#2c2c2a',
          900: '#1a1a19',
          950: '#121211',
        },
        primary: { color: '{primary.400}', contrastColor: '{surface.950}', hoverColor: '{primary.300}', activeColor: '{primary.200}' },
        text: { color: '{surface.50}', hoverColor: '{surface.0}', mutedColor: '{surface.400}', hoverMutedColor: '{surface.300}' },
      },
    },
  },
})
