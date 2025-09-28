import { Routes, Route, Navigate } from 'react-router-dom'
import Home from './pages/Home.jsx'
import Auth from './pages/Auth.jsx'
import Chat from './pages/Chat.jsx'
import Pay from './pages/Pay.jsx'
import Positions from './pages/Positions.jsx'
import Stats from './pages/Stats.jsx'
import Navbar from './components/Navbar.jsx'
import Footer from './components/Footer.jsx'
// הוספת יבוא
import Account from './pages/Account.jsx'

// בתוך <Routes> הוסף:


export default function App() {
  return (
    <div className="app-shell">
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/auth" element={<Auth />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/pay" element={<Pay />} />
          <Route path="/positions" element={<Positions />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/account" element={<Account />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
