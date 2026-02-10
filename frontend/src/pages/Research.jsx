import { useState, useEffect, useRef } from 'react'

function Research({ date }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sources, setSources] = useState(null)
  const [useWebSearch, setUseWebSearch] = useState(false)
  const messagesEndRef = useRef(null)

  // Load sources on mount
  useEffect(() => {
    if (date) {
      fetch(`/api/research/sources?date=${date}`)
        .then(res => res.json())
        .then(setSources)
        .catch(console.error)
    }
  }, [date])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    if (!input.trim() || loading) return

    const userMessage = { role: 'user', content: input, timestamp: new Date().toISOString() }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`/api/research/chat?date=${date}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: input,
          use_web_search: useWebSearch,
          include_history: true
        })
      })
      const data = await res.json()

      const assistantMessage = {
        role: 'assistant',
        content: data.response,
        citations: data.citations,
        timestamp: data.timestamp,
        used_web_search: data.used_web_search
      }
      setMessages(prev => [...prev, assistantMessage])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.message}`,
        timestamp: new Date().toISOString()
      }])
    } finally {
      setLoading(false)
    }
  }

  const clearChat = async () => {
    await fetch(`/api/research/history?date=${date}`, { method: 'DELETE' })
    setMessages([])
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-200px)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold">Research Assistant</h2>
          <p className="text-sm text-gray-500">
            Ask questions about today's AI briefings
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useWebSearch}
              onChange={(e) => setUseWebSearch(e.target.checked)}
              className="rounded"
            />
            <span>Web Search (Perplexity)</span>
            {useWebSearch && <span className="text-orange-500 text-xs">~$0.006/query</span>}
          </label>
          <button
            onClick={clearChat}
            className="px-3 py-1 text-sm text-gray-600 hover:text-red-600"
          >
            Clear Chat
          </button>
        </div>
      </div>

      {/* Sources Summary */}
      {sources && (
        <div className="mb-4 p-3 bg-blue-50 rounded-lg text-sm">
          <div className="font-medium text-blue-800">
            Loaded {sources.total_sources} articles from {Object.keys(sources.by_pipeline).length} pipelines
          </div>
          <div className="text-blue-600 mt-1">
            {Object.entries(sources.by_pipeline).map(([k, v]) => (
              <span key={k} className="mr-3">{k}: {v}</span>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto border rounded-lg p-4 bg-gray-50 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 py-8">
            <p className="text-lg mb-2">Ask me about today's AI news</p>
            <p className="text-sm">Example questions:</p>
            <div className="mt-2 space-y-1 text-sm">
              <p className="cursor-pointer hover:text-blue-500" onClick={() => setInput('What are the main AI trends today?')}>
                "What are the main AI trends today?"
              </p>
              <p className="cursor-pointer hover:text-blue-500" onClick={() => setInput('Tell me about vLLM funding')}>
                "Tell me about vLLM funding"
              </p>
              <p className="cursor-pointer hover:text-blue-500" onClick={() => setInput('百度文心和豆包有什么区别？')}>
                "百度文心和豆包有什么区别？"
              </p>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg p-3 ${
                msg.role === 'user'
                  ? 'bg-blue-500 text-white'
                  : 'bg-white border shadow-sm'
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.content}</div>

              {/* Citations */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <div className="text-xs font-medium text-gray-500 mb-2">Sources:</div>
                  <div className="space-y-2">
                    {msg.citations.map((cite, cidx) => (
                      <div key={cidx} className="text-xs bg-gray-50 p-2 rounded">
                        <a
                          href={cite.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-blue-600 hover:underline"
                        >
                          {cite.title}
                        </a>
                        <div className="text-gray-500 mt-1">{cite.source_name}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Web search indicator */}
              {msg.used_web_search && (
                <div className="mt-2 text-xs text-orange-500">
                  + Web search results
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border shadow-sm rounded-lg p-3">
              <div className="flex items-center gap-2 text-gray-500">
                <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
                <span>Researching...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="mt-4 flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask about AI trends, companies, or specific articles..."
          className="flex-1 border rounded-lg p-3 resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          rows={2}
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </div>
    </div>
  )
}

export default Research
