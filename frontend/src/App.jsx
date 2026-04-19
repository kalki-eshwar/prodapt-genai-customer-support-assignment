import { useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setResult(null)

    if (!query.trim()) {
      setError('Please enter a customer complaint.')
      return
    }

    setIsLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/respond`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query, mode: 'strict' }),
      })

      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.error || 'Failed to generate response')
      }
      setResult(payload)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="header-block">
        <p className="eyebrow">AI-Assisted Support Workflow</p>
        <h1>Customer Support Response Generator</h1>
        <p>
          Draft consistent replies from local company policies using BM25 retrieval and
          Sarvam LLM generation.
        </p>
      </header>

      <section className="card">
        <form onSubmit={handleSubmit} className="form-grid">
          <label htmlFor="query">Customer complaint</label>
          <textarea
            id="query"
            rows="5"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Example: My product arrived late and damaged. Can I get a refund?"
          />

          <p className="hint">Strict policy mode (temperature 0.2, max_tokens 150)</p>

          <button type="submit" disabled={isLoading}>
            {isLoading ? 'Generating...' : 'Generate Draft Response'}
          </button>
        </form>

        {error && <p className="error-box">{error}</p>}

        {result && (
          <div className="result-grid">
            <article>
              <h2>AI Response</h2>
              <p className="response-text">{result.response}</p>
            </article>

            <article>
              <h2>Generation Details</h2>
              <p>Mode: {result.used_mode}</p>
              <p>
                Temperature: {result.parameters.temperature}, Max tokens:{' '}
                {result.parameters.max_tokens}
              </p>
              <p>Best BM25 score: {result.best_score.toFixed(3)}</p>
            </article>

            <article>
              <h2>Retrieved Policy Documents</h2>
              <ul className="sources-list">
                {result.documents.map((doc, index) => (
                  <li key={`${doc.trouble}-${index}`}>
                    <h3>
                      {doc.trouble} <span>({doc.score.toFixed(3)})</span>
                    </h3>
                    <p><strong>Category:</strong> {doc.category}</p>
                    <p><strong>Solution:</strong> {doc.solution}</p>
                    <p><strong>Alternate Solution:</strong> {doc.alternate_solution}</p>
                    <p><strong>Company Response:</strong> {doc.company_response}</p>
                  </li>
                ))}
              </ul>
            </article>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
