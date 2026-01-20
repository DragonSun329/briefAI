import { useApi } from '../hooks/useApi'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts'

const LIFECYCLE_COLORS = {
  EMERGING: '#22c55e',
  VALIDATING: '#3b82f6',
  ESTABLISHING: '#f59e0b',
  MAINSTREAM: '#6b7280',
}

export default function BucketRadar() {
  const { data: bucketsData, loading: loadingBuckets } = useApi('/api/buckets')
  const { data: alerts, loading: loadingAlerts } = useApi('/api/buckets/alerts/active')

  if (loadingBuckets || loadingAlerts) {
    return <div className="text-center py-8">加载中...</div>
  }

  if (!bucketsData || !bucketsData.profiles) {
    return <div className="text-gray-500 py-8">暂无趋势桶数据</div>
  }

  const scatterData = bucketsData.profiles.map(p => ({
    ...p,
    x: p.tms,
    y: p.ccs,
  }))

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const p = payload[0].payload
      return (
        <div className="bg-white shadow-lg rounded-lg p-3 border">
          <div className="font-semibold">{p.bucket_name}</div>
          <div className="text-sm text-gray-600">{p.lifecycle_state}</div>
          <div className="text-xs mt-1">
            <div>TMS: {p.tms?.toFixed(1)}</div>
            <div>CCS: {p.ccs?.toFixed(1)}</div>
            <div>NAS: {p.nas?.toFixed(1)}</div>
            <div>Heat: {p.heat_score?.toFixed(1)}</div>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">趋势桶雷达</h2>

      <div className="grid grid-cols-3 gap-6">
        {/* Quadrant Chart */}
        <div className="col-span-2 bg-white rounded-lg shadow p-4">
          <h3 className="font-semibold mb-3">技术动量 vs 资本共识</h3>
          <ResponsiveContainer width="100%" height={400}>
            <ScatterChart margin={{ top: 20, right: 20, bottom: 40, left: 40 }}>
              <XAxis
                type="number"
                dataKey="x"
                domain={[0, 100]}
                label={{ value: 'TMS (技术动量)', position: 'bottom' }}
              />
              <YAxis
                type="number"
                dataKey="y"
                domain={[0, 100]}
                label={{ value: 'CCS (资本共识)', angle: -90, position: 'left' }}
              />
              <ReferenceLine x={50} stroke="#ccc" strokeDasharray="3 3" />
              <ReferenceLine y={50} stroke="#ccc" strokeDasharray="3 3" />
              <Tooltip content={<CustomTooltip />} />
              <Scatter data={scatterData}>
                {scatterData.map((entry, idx) => (
                  <Cell
                    key={idx}
                    fill={LIFECYCLE_COLORS[entry.lifecycle_state] || '#999'}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-2 text-xs">
            {Object.entries(LIFECYCLE_COLORS).map(([state, color]) => (
              <div key={state} className="flex items-center gap-1">
                <div className="w-3 h-3 rounded-full" style={{ background: color }} />
                <span>{state}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Alerts */}
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-semibold mb-3">活跃警报</h3>
          <div className="space-y-2">
            {(alerts || []).slice(0, 10).map((a, idx) => (
              <div
                key={idx}
                className={`p-2 rounded text-sm ${
                  a.severity === 'high' ? 'bg-red-50 border-l-2 border-red-500' :
                  a.severity === 'medium' ? 'bg-yellow-50 border-l-2 border-yellow-500' :
                  'bg-blue-50 border-l-2 border-blue-500'
                }`}
              >
                <div className="font-medium">{a.bucket_name}</div>
                <div className="text-xs text-gray-600">{a.alert_type}</div>
                <div className="text-xs text-gray-500 mt-1">{a.message}</div>
              </div>
            ))}
            {(!alerts || alerts.length === 0) && (
              <div className="text-gray-500 text-sm">无活跃警报</div>
            )}
          </div>
        </div>
      </div>

      {/* Bucket List */}
      <div className="mt-6 bg-white rounded-lg shadow p-4">
        <h3 className="font-semibold mb-3">所有趋势桶</h3>
        <div className="grid grid-cols-4 gap-4">
          {bucketsData.profiles.map(p => (
            <div
              key={p.bucket_id}
              className="border rounded-lg p-3 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ background: LIFECYCLE_COLORS[p.lifecycle_state] || '#999' }}
                />
                <span className="font-medium truncate">{p.bucket_name}</span>
              </div>
              <div className="grid grid-cols-2 gap-1 text-xs text-gray-600">
                <div>TMS: {p.tms?.toFixed(0)}</div>
                <div>CCS: {p.ccs?.toFixed(0)}</div>
                <div>NAS: {p.nas?.toFixed(0)}</div>
                <div>Heat: {p.heat_score?.toFixed(0)}</div>
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {p.entity_count} 实体 | {p.article_count} 文章
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}