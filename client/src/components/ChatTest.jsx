import { useState, useRef, useEffect } from "react"

export default function ChatTest() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [grade, setGrade] = useState(3)
  const [topic, setTopic] = useState("Fractions")
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return

    setMessages((prev) => [...prev, { role: "user", text }])
    setInput("")
    setLoading(true)

    try {
      const res = await fetch("/api/v1/chat/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, grade, topic }),
      })
      const data = await res.json()

      if (res.ok) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: data.reply,
            meta: `${data.chunks_used} chunks · ${data.model}`,
          },
        ])
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "error", text: data.detail || "Something went wrong" },
        ])
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "error", text: "Network error — is the backend running?" },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex flex-col h-screen max-w-2xl mx-auto">
      {/* Header */}
      <div className="border-b px-4 py-3 flex items-center justify-between bg-card">
        <h1 className="text-lg font-semibold">🧠 PALM RAG Test</h1>
        <div className="flex gap-2 text-sm">
          <select
            value={grade}
            onChange={(e) => setGrade(Number(e.target.value))}
            className="border rounded px-2 py-1 bg-background"
          >
            {[1, 2, 3, 4, 5].map((g) => (
              <option key={g} value={g}>Grade {g}</option>
            ))}
          </select>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Topic"
            className="border rounded px-2 py-1 w-28 bg-background"
          />
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-muted-foreground text-center mt-20 text-sm">
            Ask a math question to test the RAG pipeline
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : msg.role === "error"
                  ? "bg-destructive/10 text-destructive border border-destructive/20"
                  : "bg-muted"
              }`}
            >
              {msg.text}
              {msg.meta && (
                <div className="text-xs opacity-60 mt-1">{msg.meta}</div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-lg px-3 py-2 text-sm">
              <span className="inline-flex gap-1">
                <span className="w-1.5 h-1.5 bg-foreground/40 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-1.5 h-1.5 bg-foreground/40 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-1.5 h-1.5 bg-foreground/40 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t px-4 py-3 flex gap-2 bg-card">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a math question…"
          className="flex-1 border rounded-lg px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          disabled={loading}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          Send
        </button>
      </div>
    </div>
  )
}
