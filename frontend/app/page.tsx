'use client'

import { useState, useEffect, useCallback } from 'react'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export default function Home() {
  const [healthStatus, setHealthStatus] = useState<{status: string, message?: string} | null>(null)

  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/health`)
      const data = await response.json()
      setHealthStatus(data)
    } catch (err: unknown) {
      setHealthStatus({
        status: 'error',
        message: 'Cannot connect to backend'
      })
    }
  }, [])

  useEffect(() => {
    checkHealth()
  }, [checkHealth])

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto p-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Power Atlas</h1>
          <p className="text-gray-600">Graph Explorer</p>
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

        <div className="bg-white p-6 rounded-lg border">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Graph Integration</h2>
          <p className="text-gray-700 text-sm">
            Backend graph APIs are currently placeholder-only while Neo4j integration is finalized.
            Use the scripts in <code>pipelines/</code> to run Neo4j + GDS ingestion and query workflows.
          </p>
        </div>
      </div>
    </div>
  )
}
