import { useState, useEffect } from 'react'
import { useApi } from '../hooks/useApi'

function StatCard({ label, value, color = 'blue' }) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    yellow: 'bg-yellow-50 text-yellow-600',
    red: 'bg-red-50 text-red-600',
    purple: 'bg-purple-50 text-purple-600',
  }

  return (
    <div className={`rounded-lg p-4 text-center ${colors[color]}`}>
      <div className="text-3xl font-bold">{value}</div>
      <div className="text-sm text-gray-600">{label}</div>
    </div>
  )
}

function RecommendationBadge({ recommendation }) {
  const colors = {
    ALERT: 'bg-red-100 text-red-800 border-red-200',
    INVESTIGATE: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    MONITOR: 'bg-blue-100 text-blue-800 border-blue-200',
    IGNORE: 'bg-gray-100 text-gray-800 border-gray-200',
  }

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium border ${colors[recommendation] || colors.IGNORE}`}>
      {recommendation}
    </span>
  )
}

function ConflictBadge({ intensity }) {
  const colors = {
    HIGH: 'bg-red-50 text-red-700',
    MEDIUM: 'bg-yellow-50 text-yellow-700',
    LOW: 'bg-green-50 text-green-700',
  }

  return (
    <span className={`px-2 py-1 rounded text-xs ${colors[intensity] || colors.LOW}`}>
      {intensity} conflict
    </span>
  )
}

function EntityTypeBadge({ type }) {
  const isOSS = type === 'OSS_PROJECT'
  return (
    <span className={`px-2 py-1 rounded text-xs ${isOSS ? 'bg-purple-50 text-purple-700' : 'bg-blue-50 text-blue-700'}`}>
      {isOSS ? 'OSS' : 'SaaS'}
    </span>
  )
}

function ConvictionRow({ score, onSelect }) {
  const gap = Math.abs(
    (score.signal_breakdown?.technical_velocity || 0) -
    (score.signal_breakdown?.commercial_maturity || 0)
  )

  return (
    <tr
      className="hover:bg-gray-50 cursor-pointer border-b"
      onClick={() => onSelect(score)}
    >
      <td className="px-4 py-3">
        <div className="font-medium">{score.entity_name}</div>
        <div className="flex gap-2 mt-1">
          <EntityTypeBadge type={score.entity_type} />
          <ConflictBadge intensity={score.conflict_intensity} />
        </div>
      </td>
      <td className="px-4 py-3 text-center">
        <div className="text-2xl font-bold text-blue-600">
          {score.conviction_score?.toFixed(0) || 0}
        </div>
      </td>
      <td className="px-4 py-3 text-center">
        <div className="text-sm">
          <span className="text-green-600">{score.signal_breakdown?.technical_velocity || 0}</span>
          <span className="text-gray-400 mx-1">/</span>
          <span className="text-orange-600">{score.signal_breakdown?.commercial_maturity || 0}</span>
        </div>
        <div className="text-xs text-gray-500">Tech / Commercial</div>
      </td>
      <td className="px-4 py-3 text-center">
        <RecommendationBadge recommendation={score.recommendation} />
      </td>
      <td className="px-4 py-3 text-sm text-gray-600 max-w-xs truncate">
        {score.verdict?.synthesis || '-'}
      </td>
    </tr>
  )
}

function DetailModal({ score, onClose }) {
  if (!score) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h2 className="text-xl font-bold">{score.entity_name}</h2>
              <div className="flex gap-2 mt-1">
                <EntityTypeBadge type={score.entity_type} />
                <RecommendationBadge recommendation={score.recommendation} />
              </div>
            </div>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-2xl">
              &times;
            </button>
          </div>

          {/* Scores */}
          <div className="grid grid-cols-4 gap-3 mb-6">
            <StatCard label="Conviction" value={score.conviction_score?.toFixed(0) || 0} color="blue" />
            <StatCard label="Technical" value={score.signal_breakdown?.technical_velocity || 0} color="green" />
            <StatCard label="Commercial" value={score.signal_breakdown?.commercial_maturity || 0} color="yellow" />
            <StatCard label="Brand Safety" value={score.signal_breakdown?.brand_safety || 0} color="purple" />
          </div>

          {/* Bull Thesis */}
          {score.verdict?.bull_thesis && (
            <div className="mb-4">
              <h3 className="font-semibold text-green-700 mb-2">Bull Thesis</h3>
              <p className="text-sm bg-green-50 p-3 rounded">{score.verdict.bull_thesis}</p>
            </div>
          )}

          {/* Bear Thesis */}
          {score.verdict?.bear_thesis && (
            <div className="mb-4">
              <h3 className="font-semibold text-red-700 mb-2">Bear Thesis</h3>
              <p className="text-sm bg-red-50 p-3 rounded">{score.verdict.bear_thesis}</p>
            </div>
          )}

          {/* Synthesis */}
          {score.verdict?.synthesis && (
            <div className="mb-4">
              <h3 className="font-semibold text-blue-700 mb-2">Synthesis</h3>
              <p className="text-sm bg-blue-50 p-3 rounded">{score.verdict.synthesis}</p>
            </div>
          )}

          {/* Key Uncertainty */}
          {score.verdict?.key_uncertainty && (
            <div className="mb-4">
              <h3 className="font-semibold text-gray-700 mb-2">Key Uncertainty</h3>
              <p className="text-sm bg-gray-50 p-3 rounded">{score.verdict.key_uncertainty}</p>
            </div>
          )}

          {/* Metadata */}
          <div className="text-xs text-gray-500 mt-4 pt-4 border-t">
            Analyzed: {score.analyzed_at} | Model: {score.llm_model || 'N/A'}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Conviction() {
  const [filter, setFilter] = useState({ recommendation: '', entityType: '', conflict: '' })
  const [selectedScore, setSelectedScore] = useState(null)

  const { data: stats } = useApi('/api/conviction/stats')
  const { data: alerts } = useApi('/api/conviction/alerts')

  // Build query string for filtering
  const queryParams = new URLSearchParams()
  if (filter.recommendation) queryParams.set('recommendation', filter.recommendation)
  if (filter.entityType) queryParams.set('entity_type', filter.entityType)
  if (filter.conflict) queryParams.set('conflict', filter.conflict)
  queryParams.set('limit', '50')

  const { data: scores, loading } = useApi(`/api/conviction/scores?${queryParams.toString()}`)

  return (
    <div>
      <h2 className="text-xl font-semibold mb-2">Conviction Scores</h2>
      <p className="text-gray-600 mb-6">
        Adversarial analysis combining Hype-Man (bull) and Skeptic (bear) perspectives.
      </p>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-5 gap-4 mb-6">
          <StatCard label="Total Entities" value={stats.total_entities} color="blue" />
          <StatCard label="Avg Conviction" value={stats.average_conviction?.toFixed(0) || 0} color="green" />
          <StatCard label="Alerts" value={stats.by_recommendation?.ALERT || 0} color="red" />
          <StatCard label="Investigate" value={stats.by_recommendation?.INVESTIGATE || 0} color="yellow" />
          <StatCard label="Monitor" value={stats.by_recommendation?.MONITOR || 0} color="purple" />
        </div>
      )}

      {/* Alerts Banner */}
      {alerts?.alerts?.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-red-700 mb-2">Active Alerts ({alerts.total})</h3>
          <div className="flex gap-2 flex-wrap">
            {alerts.alerts.map((alert, idx) => (
              <button
                key={idx}
                onClick={() => setSelectedScore(alert)}
                className="px-3 py-1 bg-white rounded border border-red-200 text-sm hover:bg-red-100"
              >
                {alert.entity_name} ({alert.conviction_score?.toFixed(0)})
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4 mb-4">
        <select
          value={filter.recommendation}
          onChange={(e) => setFilter({ ...filter, recommendation: e.target.value })}
          className="border rounded px-3 py-2"
        >
          <option value="">All Recommendations</option>
          <option value="ALERT">Alert</option>
          <option value="INVESTIGATE">Investigate</option>
          <option value="MONITOR">Monitor</option>
          <option value="IGNORE">Ignore</option>
        </select>

        <select
          value={filter.entityType}
          onChange={(e) => setFilter({ ...filter, entityType: e.target.value })}
          className="border rounded px-3 py-2"
        >
          <option value="">All Types</option>
          <option value="OSS_PROJECT">OSS Projects</option>
          <option value="COMMERCIAL_SAAS">Commercial SaaS</option>
        </select>

        <select
          value={filter.conflict}
          onChange={(e) => setFilter({ ...filter, conflict: e.target.value })}
          className="border rounded px-3 py-2"
        >
          <option value="">All Conflict Levels</option>
          <option value="HIGH">High Conflict</option>
          <option value="MEDIUM">Medium Conflict</option>
          <option value="LOW">Low Conflict</option>
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-8">Loading...</div>
      ) : (
        <div className="bg-white rounded-lg border overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Entity</th>
                <th className="px-4 py-3 text-center text-sm font-medium text-gray-700">Conviction</th>
                <th className="px-4 py-3 text-center text-sm font-medium text-gray-700">Scores</th>
                <th className="px-4 py-3 text-center text-sm font-medium text-gray-700">Action</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">Synthesis</th>
              </tr>
            </thead>
            <tbody>
              {scores?.scores?.map((score, idx) => (
                <ConvictionRow key={idx} score={score} onSelect={setSelectedScore} />
              ))}
              {(!scores?.scores || scores.scores.length === 0) && (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-gray-500">
                    No conviction scores yet. Run analysis from the API.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail Modal */}
      <DetailModal score={selectedScore} onClose={() => setSelectedScore(null)} />
    </div>
  )
}