import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Container from '@mui/material/Container'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import { Link as RouterLink, Route, Routes } from 'react-router'

import NewRunPage from './routes/NewRunPage'
import RunPage from './routes/RunPage'

/**
 * Two routes, and the second one carries the run id **in the URL** — that is what makes a
 * mid-run refresh reconnect to the same run rather than start over (AC8b).
 */
export default function App() {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'grey.50' }}>
      <AppBar position="static" elevation={0}>
        <Toolbar>
          <Typography
            variant="h6"
            component={RouterLink}
            to="/"
            data-testid="home-link"
            sx={{ color: 'inherit', textDecoration: 'none' }}
          >
            Research Opportunity Intelligence
          </Typography>
        </Toolbar>
      </AppBar>
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Routes>
          <Route path="/" element={<NewRunPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="*" element={<NewRunPage />} />
        </Routes>
      </Container>
    </Box>
  )
}
