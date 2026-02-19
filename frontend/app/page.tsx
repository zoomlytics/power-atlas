'use client'

import { useState, useEffect } from 'react'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export default function Home() {
  const [healthStatus, setHealthStatus] = useState<{status: string, message?: string} | null>(null)
  const [query, setQuery] = useState('MATCH (n:Person) RETURN n')
  const [results, setResults] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  useEffect(() => {
    checkHealth()
  }, [])

  const checkHealth = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/health`)
      const data = await response.json()
      setHealthStatus(data)
    } catch (err) {
      setHealthStatus({
        status: 'error',
        message: 'Cannot connect to backend'
      })
    }
  }

  const runQuery = async () => {
    setLoading(true)
    setError(null)
    setResults(null)
    setSuccessMessage(null)
    
    try {
      const response = await fetch(`${BACKEND_URL}/cypher`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query, params: {} }),
      })
      
      const data = await response.json()
      
      if (!response.ok) {
        setError(data.detail || 'Query execution failed')
      } else {
        setResults(data)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to connect to backend')
    } finally {
      setLoading(false)
    }
  }

  const seedGraph = async () => {
    setLoading(true)
    setError(null)
    setSuccessMessage(null)
    
    try {
      const response = await fetch(`${BACKEND_URL}/seed`, {
        method: 'POST',
      })
      
      const data = await response.json()
      
      if (!response.ok) {
        setError(data.detail || 'Seeding failed')
      } else {
        setSuccessMessage(data.message || 'Graph seeded successfully!')
        checkHealth()
      }
    } catch (err: any) {
      setError(err.message || 'Failed to connect to backend')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto p-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Power Atlas</h1>
          <p className="text-gray-600">Graph Database Explorer with Apache AGE</p>
        </div>

        {/* Health Status */}
        <div className="mb-8 p-4 rounded-lg border bg-white">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Backend Status</h2>
              <p className="text-sm text-gray-600">
                {healthStatus?.message || 'Checking...'}
              </p>
            </div>
            <div className={`px-3 py-1 rounded-full text-sm font-medium ${
              healthStatus?.status === 'ok' 
                ? 'bg-green-100 text-green-800' 
                : 'bg-red-100 text-red-800'
            }`}>
              {healthStatus?.status || 'unknown'}
            </div>
          </div>
        </div>

        {/* Success Message */}
        {successMessage && (
          <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
            <h3 className="text-green-800 font-semibold mb-1">Success</h3>
            <p className="text-green-700 text-sm">{successMessage}</p>
          </div>
        )}

        {/* Seed Button */}
        <div className="mb-6">
          <button
            onClick={seedGraph}
            disabled={loading || healthStatus?.status !== 'ok'}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            {loading ? 'Loading...' : 'Seed Demo Graph'}
          </button>
          <p className="text-sm text-gray-600 mt-2">
            Creates 3 Person nodes (Alice, Bob, Charlie) with KNOWS relationships
          </p>
        </div>

        {/* Query Interface */}
        <div className="bg-white p-6 rounded-lg border">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Execute Cypher Query</h2>
          
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full h-32 p-3 border rounded-md font-mono text-sm mb-4"
            placeholder="Enter your Cypher query here..."
          />
          
          <button
            onClick={runQuery}
            disabled={loading || !query.trim() || healthStatus?.status !== 'ok'}
            className="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            {loading ? 'Running...' : 'Run Query'}
          </button>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <h3 className="text-red-800 font-semibold mb-1">Error</h3>
            <p className="text-red-700 text-sm">{error}</p>
          </div>
        )}

        {/* Results Display */}
        {results && (
          <div className="mt-6 bg-white p-6 rounded-lg border">
            <h3 className="text-lg font-semibold text-gray-900 mb-3">
              Results ({results.count} rows)
            </h3>
            <pre className="bg-gray-50 p-4 rounded-md overflow-x-auto text-sm">
              {JSON.stringify(results.results, null, 2)}
            </pre>
          </div>
        )}

        {/* Example Queries */}
        <div className="mt-8 bg-blue-50 p-6 rounded-lg border border-blue-200">
          <h3 className="text-lg font-semibold text-blue-900 mb-3">Example Queries</h3>
          <ul className="space-y-2 text-sm">
            <li className="font-mono text-blue-800">MATCH (n:Person) RETURN n</li>
            <li className="font-mono text-blue-800">MATCH (a:Person)-[r:KNOWS]-&gt;(b:Person) RETURN a, r, b</li>
            <li className="font-mono text-blue-800">MATCH (p:Person) WHERE p.age &gt; 30 RETURN p</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
