import { useState } from 'react'
import { useApi } from '../hooks/useApi'

function ScorecardMetrics({ scorecard }) {
  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-green-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-green-600">
          {(scorecard.precision_at_k * 100).toFixed(0)}%
        </div>
        <div className="text-sm text-gray-600">Precision@{scorecard.total_predictions}</div>
      </div>
      <div className="bg-blue-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-blue-600">
          {scorecard.avg_lead_time_weeks.toFixed(1)}w
        </div>
        <div className="text-sm text-gray-600">Avg Lead Time</div>
      </div>
      <div className="bg-purple-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-purple-600">
          {scorecard.total_hits}/{scorecard.total_predictions}
        </div>
        <div className="text-sm text-gray-600">Hits</div>
      </div>
      <div className="bg-red-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-red-600">
          {scorecard.total_misses}
        </div>
        <div className="text-sm text-gray-600">Misses</div>
      </div>
    </div>
  )
}

function HitsList({ hits }) {
  if (!hits?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold text-green-700 mb-3">Successful Predictions</h3>
      <div className="space-y-2">
        {hits.map((hit, idx) => (
          <div key={idx} className="bg-green-50 rounded p-3 flex justify-between items-center">
            <div>
              <span className="font-medium">{hit.entity_name}</span>
              <span className="text-sm text-gray-500 ml-2">#{hit.predicted_rank}</span>
            </div>
            <div className="text-sm text-green-600">
              {hit.lead_time_weeks?.toFixed(0)}w lead &rarr; {hit.mainstream_source}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function MissesList({ misses }) {
  if (!misses?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold text-red-700 mb-3">Missed Breakouts</h3>
      <div className="space-y-2">
        {misses.map((miss, idx) => (
          <div key={idx} className="bg-red-50 rounded p-3">
            <span className="font-medium">{miss.entity_name}</span>
            <span className="text-sm text-gray-500 ml-2">
              Broke out {miss.mainstream_date}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function FalsePositivesList({ falsePositives }) {
  if (!falsePositives?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold text-yellow-700 mb-3">False Positives</h3>
      <div className="space-y-2">
        {falsePositives.map((fp, idx) => (
          <div key={idx} className="bg-yellow-50 rounded p-3">
            <span className="font-medium">{fp.entity_name}</span>
            <span className="text-sm text-gray-500 ml-2">
              Score {fp.momentum_score.toFixed(0)} - no mainstream yet
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Backtest() {
  const [predDate, setPredDate] = useState('2024-12-15')
  const [valDate, setValDate] = useState('2025-01-20')
  const [selectedRun, setSelectedRun] = useState(null)
  const [loading, setLoading] = useState(false)

  const { data: runs, refetch: refetchRuns } = useApi('/api/backtest/runs')
  const { data: scorecard, loading: loadingScorecard } = useApi(
    selectedRun ? `/api/backtest/runs/${selectedRun}/scorecard` : null
  )

  const runBacktest = async () => {
    setLoading(true)
    try {
      const resp = await fetch(
        `/api/backtest/runs?prediction_date=${predDate}&validation_date=${valDate}&top_k=20`,
        { method: 'POST' }
      )
      const data = await resp.json()
      setSelectedRun(data.run_id)
      refetchRuns()
    } catch (err) {
      console.error('Backtest failed:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Shadow Mode Backtesting</h2>
      <p className="text-gray-600 mb-6">
        Test trend radar predictions against historical outcomes. Select a prediction date
        and validation date to see how well the system would have detected breakout entities.
      </p>

      {/* Run Configuration */}
      <div className="bg-gray-50 rounded-lg p-4 mb-6">
        <div className="flex gap-4 items-end flex-wrap">
          <div>
            <label className="block text-sm text-gray-600 mb-1">Prediction Date</label>
            <input
              type="date"
              value={predDate}
              onChange={(e) => setPredDate(e.target.value)}
              className="border rounded px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Validation Date</label>
            <input
              type="date"
              value={valDate}
              onChange={(e) => setValDate(e.target.value)}
              className="border rounded px-3 py-2"
            />
          </div>
          <button
            onClick={runBacktest}
            disabled={loading}
            className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? 'Running...' : 'Run Backtest'}
          </button>
        </div>
      </div>

      {/* Previous Runs */}
      {runs?.length > 0 && (
        <div className="mb-6">
          <h3 className="font-semibold mb-2">Previous Runs</h3>
          <div className="flex gap-2 flex-wrap">
            {runs.map(runId => (
              <button
                key={runId}
                onClick={() => setSelectedRun(runId)}
                className={`px-3 py-1 rounded text-sm ${
                  selectedRun === runId
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-200 hover:bg-gray-300'
                }`}
              >
                {runId.replace('backtest_', '')}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Scorecard */}
      {loadingScorecard && <div className="text-center py-8">Loading scorecard...</div>}

      {scorecard && (
        <div>
          <div className="text-sm text-gray-500 mb-4">
            Prediction: {scorecard.prediction_date} &rarr; Validation: {scorecard.validation_date}
          </div>

          <ScorecardMetrics scorecard={scorecard} />
          <HitsList hits={scorecard.hits} />
          <MissesList misses={scorecard.misses} />
          <FalsePositivesList falsePositives={scorecard.false_positives} />
        </div>
      )}

      {/* Empty State */}
      {!selectedRun && !runs?.length && (
        <div className="text-center py-12 text-gray-500">
          No backtest runs yet. Configure dates above and click "Run Backtest" to get started.
        </div>
      )}
    </div>
  )
}