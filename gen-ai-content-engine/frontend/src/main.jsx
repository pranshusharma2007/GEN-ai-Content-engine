import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import './index.css'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import AuthGate from './components/auth/AuthGate.jsx'
import { setTokenGetter } from './lib/api.js'
import { auth, isFirebaseConfigured } from './lib/firebase.js'

// Wire the API client's token source without importing AuthContext (avoids a cycle).
setTokenGetter(async () => {
  if (!isFirebaseConfigured || !auth?.currentUser) return null
  return auth.currentUser.getIdToken()
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <AuthGate>
        <App />
      </AuthGate>
    </AuthProvider>
  </StrictMode>,
)
