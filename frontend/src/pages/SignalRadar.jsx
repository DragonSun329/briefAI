import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts'

function RadarChartSmall({ scores }) {
  if (!scores || scores.length === 0) return null

  const data = scores.map(s => ({
    category: s.category,
    value: s.value,  // Already 0-100 scale
  }))

  return (
    <ResponsiveContainer width="100%" height={150}>
      <RadarChart data={data}>
        <PolarGrid />
        <PolarAngleAxis dataKey="category" tick={{ fontSize: 9 }} />
        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} />
        <Radar dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
      </RadarChart>
    </ResponsiveContainer>
  )
}

export default function SignalRadar() {
  const [pmsOverlay, setPmsOverlay] = useState('none')  // 'none' | 'us' | 'cn'

  const { data: entities, loading: loadingEntities } = useApi('/api/signals/entities?limit=20')
  const { data: divergences, loading: loadingDivergences } = useApi('/api/signals/divergence')
  const { data: usBuckets } = useApi(pmsOverlay === 'us' ? '/api/buckets' : null)
  const { data: cnBuckets } = useApi(pmsOverlay === 'cn' ? '/api/buckets/cn/profiles' : null)

  if (loadingEntities || loadingDivergences) {
    return <div className="text-center py-8">加载中...</div>
  }

  const opportunities = (divergences || []).filter(d => d.interpretation === 'opportunity')
  const risks = (divergences || []).filter(d => d.interpretation === 'risk')

  // Get PMS data for overlay
  const pmsData = pmsOverlay === 'us'
    ? (usBuckets?.profiles || []).reduce((acc, b) => ({ ...acc, [b.bucket_id]: b.pms }), {})
    : pmsOverlay === 'cn'
    ? (cnBuckets?.profiles || []).reduce((acc, b) => ({ ...acc, [b.bucket_id]: b.pms_cn }), {})
    : {}

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">信号雷达</h2>

        {/* PMS Overlay Toggle */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">PMS Overlay:</span>
          <div className="flex rounded-lg overflow-hidden border">
            {['none', 'us', 'cn'].map(v => (
              <button
                key={v}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  pmsOverlay === v
                    ? 'bg-green-500 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-100'
                }`}
                onClick={() => setPmsOverlay(v)}
              >
                {v === 'none' ? 'OFF' : v.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* PMS Overlay Info */}
      {pmsOverlay !== 'none' && Object.keys(pmsData).length > 0 && (
        <div className="mb-4 p-3 bg-green-50 rounded-lg border border-green-100">
          <div className="text-sm text-gray-600 mb-2">
            PMS {pmsOverlay.toUpperCase()} 市场信号叠加 (Top 5 buckets)
          </div>
          <div className="flex gap-4 flex-wrap">
            {Object.entries(pmsData)
              .filter(([_, v]) => v != null)
              .sort(([,a], [,b]) => (b || 0) - (a || 0))
              .slice(0, 5)
              .map(([bucket, value]) => (
                <div key={bucket} className="flex items-center gap-1">
                  <span className="text-xs text-gray-500">{bucket.replace(/-cn$/, '')}:</span>
                  <span className={`text-sm font-semibold ${
                    value > 70 ? 'text-green-600' : value < 30 ? 'text-red-600' : 'text-gray-600'
                  }`}>
                    {value?.toFixed(0)}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* Opportunities */}
        <div className="bg-green-50 rounded-lg p-4">
          <h3 className="font-semibold text-green-700 mb-3">机会信号 ({opportunities.length})</h3>
          <div className="space-y-2">
            {opportunities.slice(0, 5).map((d, idx) => (
              <div key={idx} className="bg-white p-2 rounded shadow-sm">
                <div className="font-medium">{d.entity_name}</div>
                <div className="text-xs text-gray-600">
                  {d.signal_a} vs {d.signal_b}: {d.divergence_score?.toFixed(2)}
                </div>
              </div>
            ))}
            {opportunities.length === 0 && <div className="text-sm text-gray-500">暂无机会信号</div>}
          </div>
        </div>

        {/* Risks */}
        <div className="bg-red-50 rounded-lg p-4">
          <h3 className="font-semibold text-red-700 mb-3">风险信号 ({risks.length})</h3>
          <div className="space-y-2">
            {risks.slice(0, 5).map((d, idx) => (
              <div key={idx} className="bg-white p-2 rounded shadow-sm">
                <div className="font-medium">{d.entity_name}</div>
                <div className="text-xs text-gray-600">
                  {d.signal_a} vs {d.signal_b}: {d.divergence_score?.toFixed(2)}
                </div>
              </div>
            ))}
            {risks.length === 0 && <div className="text-sm text-gray-500">暂无风险信号</div>}
          </div>
        </div>
      </div>

      {/* Top Entities */}
      <h3 className="font-semibold mb-3">综合评分最高实体</h3>
      <div className="grid grid-cols-4 gap-4">
        {(entities || []).slice(0, 8).map(e => (
          <div key={e.entity_id} className="bg-white rounded-lg shadow p-4">
            <div className="font-semibold mb-1 truncate">{e.name}</div>
            <div className="text-xs text-gray-500 mb-2">{e.entity_type}</div>
            <div className="text-2xl font-bold text-blue-600 mb-2">
              {e.composite_score?.toFixed(0) || 0}
            </div>
            <RadarChartSmall scores={e.scores} />
          </div>
        ))}
      </div>
    </div>
  )
}