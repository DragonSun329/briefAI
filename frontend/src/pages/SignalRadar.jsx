import { useApi } from '../hooks/useApi'
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts'

function RadarChartSmall({ scores }) {
  if (!scores || scores.length === 0) return null

  const data = scores.map(s => ({
    category: s.category,
    value: s.value * 100,
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
  const { data: entities, loading: loadingEntities } = useApi('/api/signals/entities?limit=20')
  const { data: divergences, loading: loadingDivergences } = useApi('/api/signals/divergence')

  if (loadingEntities || loadingDivergences) {
    return <div className="text-center py-8">加载中...</div>
  }

  const opportunities = (divergences || []).filter(d => d.interpretation === 'opportunity')
  const risks = (divergences || []).filter(d => d.interpretation === 'risk')

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">信号雷达</h2>

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
              {(e.composite_score * 100).toFixed(0)}
            </div>
            <RadarChartSmall scores={e.scores} />
          </div>
        ))}
      </div>
    </div>
  )
}