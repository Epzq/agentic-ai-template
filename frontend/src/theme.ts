import { createTheme } from '@mui/material/styles'

/**
 * Deliberately close to the MUI default. The demo's job is to make retrieved evidence
 * legible, not to have a look; every hour spent here is an hour not spent on WI-2.5's
 * evidence chips, which are the thing the product is actually judged on.
 */
export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1b5e6f' },
  },
  shape: { borderRadius: 8 },
  typography: {
    h4: { fontWeight: 600 },
    h6: { fontWeight: 600 },
  },
})
