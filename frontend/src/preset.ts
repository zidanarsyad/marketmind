// PrimeVue Aura in the dossier palette (styles/main.css): jade as the primary colour and cool mineral greys as
// surfaces. The charts keep their own validated palette (marketmind/reporting/charts.py), so data colours never compete
// with interface colours.
import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'

const jade = {
  50: '#edf8f5',
  100: '#d3efe7',
  200: '#a9ddcf',
  300: '#7bd3be',
  400: '#3fbfa4',
  500: '#179c84',
  600: '#0b6e5f',
  700: '#08594d',
  800: '#07463d',
  900: '#06362f',
  950: '#03211d',
}

export const MarketMindPreset = definePreset(Aura, {
  semantic: {
    primary: jade,
    colorScheme: {
      light: {
        surface: {
          0: '#ffffff',
          50: '#f6f8f7',
          100: '#f2f4f3',
          200: '#d6dedb',
          300: '#b4c1bc',
          400: '#8da19b',
          500: '#6f837d',
          600: '#5e716c',
          700: '#3c504b',
          800: '#263834',
          900: '#172925',
          950: '#102320',
        },
        primary: { color: '{primary.600}', contrastColor: '#ffffff', hoverColor: '{primary.700}', activeColor: '{primary.800}' },
        highlight: { background: '{primary.50}', focusBackground: '{primary.100}', color: '{primary.700}', focusColor: '{primary.800}' },
        text: { color: '{surface.950}', hoverColor: '{surface.950}', mutedColor: '{surface.600}', hoverMutedColor: '{surface.700}' },
      },
      dark: {
        surface: {
          0: '#ffffff',
          50: '#e4edea',
          100: '#c9d6d2',
          200: '#b5c4bf',
          300: '#8da19b',
          400: '#6f837d',
          500: '#52665f',
          600: '#33473f',
          700: '#22322e',
          800: '#1a2824',
          900: '#111d1a',
          950: '#0b1513',
        },
        primary: { color: '{primary.400}', contrastColor: '{surface.950}', hoverColor: '{primary.300}', activeColor: '{primary.200}' },
        highlight: { background: 'rgba(63, 191, 164, 0.16)', focusBackground: 'rgba(63, 191, 164, 0.24)', color: '{primary.200}', focusColor: '{primary.100}' },
        text: { color: '{surface.50}', hoverColor: '{surface.0}', mutedColor: '{surface.300}', hoverMutedColor: '{surface.200}' },
      },
    },
  },
})
