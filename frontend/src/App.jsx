import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'

function App() {
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState('')

  useEffect(() => {
    fetch('/api/dates')
      .then(res => res.json())
      .then(data => {
        setDates(data.dates || [])
        if (data.latest) setSelectedDate(data.latest)
      })
      .catch(() => {})
  }, [])

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
            <h1 className="text-2xl font-bold text-blue-600">CEO智能仪表板</h1>
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="border rounded px-3 py-2"
            >
              {dates.map(d => (
                <option key={d} value={d}>
                  {d.slice(0,4)}-{d.slice(4,6)}-{d.slice(6,8)}
                </option>
              ))}
            </select>
          </div>
        </header>

        {/* Navigation */}
        <nav className="bg-white border-b">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex space-x-8">
              {[
                { path: '/', label: '洞察', icon: '🔥' },
                { path: '/news', label: 'AI新闻', icon: '📰' },
                { path: '/product', label: '产品', icon: '🚀' },
                { path: '/investing', label: '投资', icon: '💰' },
                { path: '/shortlist', label: 'AI速查', icon: '🏢' },
                { path: '/signals', label: '信号雷达', icon: '📡' },
                { path: '/buckets', label: '趋势桶雷达', icon: '🎯' },
              ].map(({ path, label, icon }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) =>
                    `py-4 px-1 border-b-2 font-medium ${
                      isActive
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`
                  }
                >
                  {icon} {label}
                </NavLink>
              ))}
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<div className="text-gray-600">洞察页面 - 开发中</div>} />
            <Route path="/news" element={<div className="text-gray-600">新闻页面 - 开发中</div>} />
            <Route path="/product" element={<div className="text-gray-600">产品页面 - 开发中</div>} />
            <Route path="/investing" element={<div className="text-gray-600">投资页面 - 开发中</div>} />
            <Route path="/shortlist" element={<div className="text-gray-600">速查页面 - 开发中</div>} />
            <Route path="/signals" element={<div className="text-gray-600">信号雷达 - 开发中</div>} />
            <Route path="/buckets" element={<div className="text-gray-600">趋势桶雷达 - 开发中</div>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App