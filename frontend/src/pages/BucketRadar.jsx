import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine, Area, ComposedChart } from 'recharts'

const LIFECYCLE_COLORS = {
  EMERGING: '#22c55e',
  VALIDATING: '#3b82f6',
  ESTABLISHING: '#f59e0b',
  MAINSTREAM: '#6b7280',
}

const HYPE_CYCLE_PHASES = {
  innovation_trigger: { label: '技术萌芽期', color: '#3498db', x: 10 },
  peak_expectations: { label: '期望膨胀期', color: '#e74c3c', x: 30 },
  trough_disillusionment: { label: '泡沫破灭期', color: '#95a5a6', x: 50 },
  slope_enlightenment: { label: '稳步爬升期', color: '#f39c12', x: 70 },
  plateau_productivity: { label: '成熟稳定期', color: '#27ae60', x: 90 },
}

// Generate hype cycle curve data
function generateHypeCycleData() {
  const data = []
  for (let x = 0; x <= 100; x++) {
    const y = (
      30 +
      60 * Math.exp(-((x - 30) ** 2) / 200) -
      20 * Math.exp(-((x - 50) ** 2) / 100) +
      30 * (1 / (1 + Math.exp(-(x - 70) / 10)))
    )
    data.push({ x, y })
  }
  return data
}

const HYPE_CYCLE_CURVE = generateHypeCycleData()

export default function BucketRadar() {
  const [activeTab, setActiveTab] = useState('quadrant')
  const [viewMode, setViewMode] = useState('lifecycle')
  const [scoreType, setScoreType] = useState('heat')
  const [market, setMarket] = useState('us')  // 'us' | 'cn'

  // Load data based on market selection
  const bucketsEndpoint = market === 'cn' ? '/api/buckets/cn/profiles' : '/api/buckets'
  const { data: bucketsData, loading: loadingBuckets } = useApi(bucketsEndpoint)
  const { data: alerts, loading: loadingAlerts } = useApi('/api/buckets/alerts/active')
  const { data: cnMacro } = useApi(market === 'cn' ? '/api/buckets/cn/macro' : null)

  if (loadingBuckets || loadingAlerts) {
    return <div className="text-center py-8">加载中...</div>
  }

  if (!bucketsData || !bucketsData.profiles) {
    return <div className="text-gray-500 py-8">暂无趋势桶数据</div>
  }

  const profiles = bucketsData.profiles

  const tabs = [
    { id: 'quadrant', label: '[Q] 四象限图' },
    { id: 'heatmap', label: '[H] 热力图' },
    { id: 'alerts', label: '[!] 警报' },
    { id: 'gartner', label: '[G] Gartner周期' },
  ]

  // Quadrant scatter data
  const scatterData = profiles.map(p => ({
    ...p,
    x: p.tms,
    y: p.ccs,
  }))

  // Heatmap data (sorted by selected score)
  const heatmapData = [...profiles].sort((a, b) => (b[scoreType] || 0) - (a[scoreType] || 0))

  // Gartner hype cycle bucket positions
  const hypeCycleBuckets = profiles
    .filter(p => p.hype_cycle_phase && p.hype_cycle_phase !== 'unknown')
    .map(p => {
      const phaseInfo = HYPE_CYCLE_PHASES[p.hype_cycle_phase] || { x: 50 }
      const baseY = HYPE_CYCLE_CURVE.find(d => Math.abs(d.x - phaseInfo.x) < 1)?.y || 50
      return {
        ...p,
        x: phaseInfo.x + (Math.random() - 0.5) * 10,
        y: baseY + (Math.random() - 0.5) * 6,
        phase: p.hype_cycle_phase,
        phaseLabel: phaseInfo.label,
        phaseColor: phaseInfo.color,
      }
    })

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
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">趋势桶雷达</h2>

        {/* Market Toggle */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">市场:</span>
          <div className="flex rounded-lg overflow-hidden border">
            <button
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                market === 'us'
                  ? 'bg-blue-500 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-100'
              }`}
              onClick={() => setMarket('us')}
            >
              🇺🇸 US
            </button>
            <button
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                market === 'cn'
                  ? 'bg-red-500 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-100'
              }`}
              onClick={() => setMarket('cn')}
            >
              🇨🇳 CN
            </button>
          </div>
        </div>
      </div>

      {/* CN Macro Indicator (shown when CN market selected) */}
      {market === 'cn' && cnMacro && (
        <div className="mb-4 p-3 bg-gradient-to-r from-red-50 to-yellow-50 rounded-lg border border-red-100">
          <div className="flex items-center gap-4">
            <div>
              <span className="text-sm text-gray-600">MRS-CN 宏观风险:</span>
              <span className={`ml-2 font-semibold ${
                cnMacro.mrs_cn > 0.2 ? 'text-green-600' :
                cnMacro.mrs_cn < -0.2 ? 'text-red-600' : 'text-gray-600'
              }`}>
                {cnMacro.mrs_cn?.toFixed(2)} ({cnMacro.interpretation})
              </span>
            </div>
            <div className="text-xs text-gray-500">
              {cnMacro.mrs_cn > 0.2 ? '📈 Risk-On' :
               cnMacro.mrs_cn < -0.2 ? '📉 Risk-Off' : '➡️ Neutral'}
            </div>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex border-b mb-4">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 font-medium transition-colors ${
              activeTab === tab.id
                ? 'border-b-2 border-blue-500 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'quadrant' && (
        <div>
          {/* View Mode Selector */}
          <div className="flex gap-4 mb-4">
            {[
              { id: 'lifecycle', label: '🔄 生命周期' },
              { id: 'cluster', label: '📊 技术集群' },
              { id: 'nas_overlay', label: '🔥 NAS热度' },
            ].map(mode => (
              <label key={mode.id} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="viewMode"
                  value={mode.id}
                  checked={viewMode === mode.id}
                  onChange={(e) => setViewMode(e.target.value)}
                  className="text-blue-600"
                />
                <span className="text-sm">{mode.label}</span>
              </label>
            ))}
          </div>

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

              {/* Zone explanation */}
              <div className="mt-4 text-xs text-gray-500 flex justify-around">
                <span>💎 右下: Alpha Zone (隐藏宝石)</span>
                <span>⚠️ 左上: Hype Zone (泡沫风险)</span>
              </div>
            </div>

            {/* Quick Stats */}
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="font-semibold mb-3">快速统计</h3>
              <div className="space-y-3">
                <div className="p-3 bg-gray-50 rounded">
                  <div className="text-2xl font-bold">{profiles.length}</div>
                  <div className="text-sm text-gray-600">总趋势桶</div>
                </div>
                <div className="p-3 bg-green-50 rounded">
                  <div className="text-2xl font-bold text-green-600">
                    {profiles.filter(p => p.tms > 50 && p.ccs < 50).length}
                  </div>
                  <div className="text-sm text-gray-600">Alpha Zone</div>
                </div>
                <div className="p-3 bg-red-50 rounded">
                  <div className="text-2xl font-bold text-red-600">
                    {profiles.filter(p => p.tms < 50 && p.ccs > 50).length}
                  </div>
                  <div className="text-sm text-gray-600">Hype Zone</div>
                </div>
                <div className="p-3 bg-orange-50 rounded">
                  <div className="text-2xl font-bold text-orange-600">
                    {(alerts || []).length}
                  </div>
                  <div className="text-sm text-gray-600">活跃警报</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'heatmap' && (
        <div className="bg-white rounded-lg shadow p-4">
          {/* Score Type Selector */}
          <div className="flex gap-4 mb-4">
            {[
              { id: 'heat', label: 'Heat (综合)' },
              { id: 'tms', label: 'TMS (技术)' },
              { id: 'ccs', label: 'CCS (资本)' },
              { id: 'nas', label: 'NAS (新闻)' },
            ].map(type => (
              <label key={type.id} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="scoreType"
                  value={type.id}
                  checked={scoreType === type.id}
                  onChange={(e) => setScoreType(e.target.value)}
                  className="text-blue-600"
                />
                <span className="text-sm">{type.label}</span>
              </label>
            ))}
          </div>

          <h3 className="font-semibold mb-3">趋势桶热力图 ({scoreType.toUpperCase()})</h3>
          <div className="grid grid-cols-8 gap-1">
            {heatmapData.map(p => {
              const value = p[scoreType === 'heat' ? 'heat_score' : scoreType] || 0
              const intensity = Math.min(value / 100, 1)
              const bgColor = `rgba(239, 68, 68, ${0.1 + intensity * 0.8})`

              return (
                <div
                  key={p.bucket_id}
                  className="p-2 rounded text-center cursor-pointer hover:ring-2 hover:ring-blue-400 transition-all"
                  style={{ background: bgColor }}
                  title={`${p.bucket_name}: ${value.toFixed(1)}`}
                >
                  <div className="text-xs font-medium truncate text-white drop-shadow">
                    {p.bucket_name.slice(0, 8)}
                  </div>
                  <div className="text-lg font-bold text-white drop-shadow">
                    {value.toFixed(0)}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {activeTab === 'alerts' && (
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-semibold mb-3">活跃警报</h3>
          {(alerts || []).length === 0 ? (
            <div className="text-gray-500 py-8 text-center">无活跃警报</div>
          ) : (
            <div className="space-y-3">
              {(alerts || []).map((a, idx) => (
                <div
                  key={idx}
                  className={`p-4 rounded-lg ${
                    a.severity === 'high' ? 'bg-red-50 border-l-4 border-red-500' :
                    a.severity === 'medium' ? 'bg-yellow-50 border-l-4 border-yellow-500' :
                    'bg-blue-50 border-l-4 border-blue-500'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="font-semibold">{a.bucket_name}</div>
                      <div className="text-sm text-gray-600">{a.alert_type}</div>
                    </div>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      a.severity === 'high' ? 'bg-red-100 text-red-800' :
                      a.severity === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-blue-100 text-blue-800'
                    }`}>
                      {a.severity}
                    </span>
                  </div>
                  <div className="mt-2 text-sm text-gray-700">{a.message}</div>
                  <div className="mt-2 flex gap-4 text-xs text-gray-500">
                    <span>TMS: {a.tms?.toFixed(0)}</span>
                    <span>CCS: {a.ccs?.toFixed(0)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'gartner' && (
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-semibold mb-3">Gartner 技术成熟度曲线</h3>
          <p className="text-sm text-gray-600 mb-4">
            此视图将每个AI趋势桶定位在经典的Gartner技术成熟度曲线上，帮助分析师理解技术成熟度和投资时机。
          </p>

          <ResponsiveContainer width="100%" height={400}>
            <ComposedChart margin={{ top: 20, right: 20, bottom: 60, left: 40 }}>
              <XAxis
                type="number"
                dataKey="x"
                domain={[0, 100]}
                tickFormatter={() => ''}
              />
              <YAxis
                type="number"
                domain={[0, 120]}
                tickFormatter={() => ''}
              />

              {/* Hype Cycle Curve */}
              <Area
                type="monotone"
                data={HYPE_CYCLE_CURVE}
                dataKey="y"
                fill="rgba(189, 195, 199, 0.2)"
                stroke="#bdc3c7"
                strokeWidth={3}
              />

              {/* Bucket points */}
              <Scatter
                data={hypeCycleBuckets}
                dataKey="y"
              >
                {hypeCycleBuckets.map((entry, idx) => (
                  <Cell
                    key={idx}
                    fill={entry.phaseColor || '#888'}
                  />
                ))}
              </Scatter>

              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const p = payload[0].payload
                    return (
                      <div className="bg-white shadow-lg rounded-lg p-3 border">
                        <div className="font-semibold">{p.bucket_name}</div>
                        <div className="text-sm" style={{ color: p.phaseColor }}>
                          {p.phaseLabel}
                        </div>
                      </div>
                    )
                  }
                  return null
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>

          {/* Phase labels */}
          <div className="flex justify-around mt-4 text-xs">
            {Object.entries(HYPE_CYCLE_PHASES).map(([key, phase]) => (
              <div key={key} className="text-center" style={{ color: phase.color }}>
                <div className="font-semibold">{phase.label}</div>
                <div className="text-gray-500">
                  {hypeCycleBuckets.filter(b => b.phase === key).length} 桶
                </div>
              </div>
            ))}
          </div>

          {/* Legend */}
          <div className="mt-6 p-4 bg-gray-50 rounded-lg">
            <h4 className="font-semibold mb-2">技术成熟度曲线阶段说明</h4>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-600">
                  <th className="py-1">阶段</th>
                  <th className="py-1">特征</th>
                  <th className="py-1">投资建议</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="py-1" style={{ color: '#3498db' }}>技术萌芽期</td>
                  <td className="py-1 text-gray-600">高技术活动，低资本/企业关注</td>
                  <td className="py-1 text-gray-600">早期阶段，高风险/高回报</td>
                </tr>
                <tr>
                  <td className="py-1" style={{ color: '#e74c3c' }}>期望膨胀期</td>
                  <td className="py-1 text-gray-600">最大炒作，资本涌入，估值过高</td>
                  <td className="py-1 text-gray-600">谨慎 - 可能被高估</td>
                </tr>
                <tr>
                  <td className="py-1" style={{ color: '#95a5a6' }}>泡沫破灭期</td>
                  <td className="py-1 text-gray-600">关注度下降，初创公司失败</td>
                  <td className="py-1 text-gray-600">逆向投资机会</td>
                </tr>
                <tr>
                  <td className="py-1" style={{ color: '#f39c12' }}>稳步爬升期</td>
                  <td className="py-1 text-gray-600">企业采用，实际应用</td>
                  <td className="py-1 text-gray-600">增长投资的最佳时机</td>
                </tr>
                <tr>
                  <td className="py-1" style={{ color: '#27ae60' }}>成熟稳定期</td>
                  <td className="py-1 text-gray-600">主流化，市场稳定</td>
                  <td className="py-1 text-gray-600">低风险，稳定回报</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Bucket List (always visible) */}
      <div className="mt-6 bg-white rounded-lg shadow p-4">
        <h3 className="font-semibold mb-3">所有趋势桶</h3>
        <div className="grid grid-cols-4 gap-4">
          {profiles.map(p => (
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