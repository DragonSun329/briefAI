import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { 
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer, 
  Cell, ReferenceLine, Area, ComposedChart, BarChart, Bar, Legend
} from 'recharts'

// Hype cycle phase colors
const PHASE_COLORS = {
  innovation_trigger: '#3498db',
  peak_expectations: '#e74c3c',
  trough_disillusionment: '#95a5a6',
  slope_enlightenment: '#f39c12',
  plateau_productivity: '#27ae60',
  validating: '#9b59b6',
  establishing: '#1abc9c',
}

// Quadrant colors
const QUADRANT_COLORS = {
  hot: '#ef4444',
  mature: '#22c55e',
  hyped: '#f59e0b',
  emerging: '#3b82f6',
}

// Generate hype cycle curve
function generateHypeCurve() {
  const data = []
  for (let x = 0; x <= 100; x += 2) {
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

const HYPE_CURVE = generateHypeCurve()

const PHASE_INFO = {
  innovation_trigger: { 
    label: 'Innovation Trigger', 
    x: 10, 
    description: 'Early R&D, few products, high uncertainty',
    advice: 'High risk/reward - for visionaries only'
  },
  peak_expectations: { 
    label: 'Peak of Inflated Expectations', 
    x: 30, 
    description: 'Media hype, VC frenzy, unrealistic expectations',
    advice: 'Caution - likely overvalued'
  },
  trough_disillusionment: { 
    label: 'Trough of Disillusionment', 
    x: 50, 
    description: 'Failures publicized, shakeout begins',
    advice: 'Contrarian opportunity - find survivors'
  },
  slope_enlightenment: { 
    label: 'Slope of Enlightenment', 
    x: 70, 
    description: 'Best practices emerge, ROI proven',
    advice: 'Best time to invest for growth'
  },
  plateau_productivity: { 
    label: 'Plateau of Productivity', 
    x: 90, 
    description: 'Mainstream adoption, market leaders clear',
    advice: 'Stable returns, lower risk'
  },
  validating: { 
    label: 'Validating', 
    x: 40, 
    description: 'Early validation phase',
    advice: 'Monitor for breakout signals'
  },
  establishing: { 
    label: 'Establishing', 
    x: 65, 
    description: 'Building market presence',
    advice: 'Good entry point'
  },
}

// Vertical icons
const VERTICAL_ICONS = {
  ai_healthcare: '🏥',
  ai_drug_discovery: '💊',
  ai_fintech: '💰',
  ai_trading: '📊',
  ai_education: '📚',
  ai_legal: '⚖️',
  ai_creative: '🎨',
  ai_robotics: '🤖',
  ai_manufacturing: '🏭',
  ai_autonomous_vehicles: '🚗',
  ai_agriculture: '🌾',
  ai_real_estate: '🏠',
  ai_insurance: '🛡️',
  ai_cybersecurity: '🔒',
  ai_hr: '👥',
  ai_sales: '📈',
  ai_marketing: '📣',
  ai_customer_service: '💬',
  ai_supply_chain: '📦',
  ai_construction: '🏗️',
  ai_gaming: '🎮',
  ai_climate: '🌍',
  ai_science: '🔬',
  ai_defense: '🏛️',
  ai_retail: '🛒',
  ai_space: '🚀',
}

export default function VerticalsRadar() {
  const [activeTab, setActiveTab] = useState('gartner')
  const [mode, setMode] = useState('dynamic')  // 'static' | 'dynamic'
  
  // Use dynamic mode by default for real-time computed scores
  const modeParam = mode === 'dynamic' ? '?mode=dynamic' : ''
  
  const { data: hypeCycleData, loading: loadingHype } = useApi(`/api/verticals/hype-cycle${modeParam}`)
  const { data: quadrantData, loading: loadingQuadrant } = useApi(`/api/verticals/quadrant${modeParam}`)
  const { data: alertsData, loading: loadingAlerts } = useApi(`/api/verticals/alerts/active${modeParam}`)
  const { data: overviewData, loading: loadingOverview } = useApi(`/api/verticals${modeParam}`)
  const { data: divergencesData } = useApi(mode === 'dynamic' ? '/api/verticals/divergences' : null)

  const loading = loadingHype || loadingQuadrant || loadingAlerts || loadingOverview

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading AI Verticals...</div>
      </div>
    )
  }

  const verticals = hypeCycleData?.verticals || []
  const quadrants = quadrantData?.verticals || []
  const alerts = alertsData?.alerts || alertsData || []
  const overview = overviewData?.verticals || []
  const divergences = divergencesData?.divergences || []
  const dataMode = overviewData?.mode || 'static'

  const alphaCount = divergences.filter(d => d.divergence_type === 'alpha_opportunity').length
  const bubbleCount = divergences.filter(d => d.divergence_type === 'bubble_warning').length

  const tabs = [
    { id: 'gartner', label: '📈 Gartner Hype Cycle' },
    { id: 'quadrant', label: '🎯 Opportunity Quadrant' },
    { id: 'divergences', label: `⚡ Signals (${alphaCount}α / ${bubbleCount}⚠)` },
    { id: 'list', label: '📋 All Verticals' },
    { id: 'alerts', label: `🔔 Alerts (${alerts.length})` },
  ]

  // Group verticals by phase for Gartner view
  const byPhase = {}
  verticals.forEach(v => {
    const phase = v.phase || 'validating'
    if (!byPhase[phase]) byPhase[phase] = []
    byPhase[phase].push(v)
  })

  // Group by quadrant
  const byQuadrant = { hot: [], mature: [], hyped: [], emerging: [] }
  quadrants.forEach(v => {
    const q = v.quadrant || 'emerging'
    if (byQuadrant[q]) byQuadrant[q].push(v)
  })

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const v = payload[0].payload
      const icon = VERTICAL_ICONS[v.id] || '🔷'
      return (
        <div className="bg-white shadow-xl rounded-lg p-4 border max-w-xs">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xl">{icon}</span>
            <span className="font-bold">{v.name}</span>
          </div>
          <div className="text-sm text-gray-600 mb-2">
            {PHASE_INFO[v.phase]?.label || v.phase}
          </div>
          <div className="text-xs text-gray-500">
            Maturity: {(v.maturity * 100).toFixed(0)}%
          </div>
          {v.companies && v.companies.length > 0 && (
            <div className="mt-2 text-xs">
              <div className="font-medium">Key Players:</div>
              <div className="text-gray-600">{v.companies.slice(0, 3).join(', ')}</div>
            </div>
          )}
        </div>
      )
    }
    return null
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AI Verticals Radar</h1>
          <p className="text-gray-600">
            Track AI adoption across 26 industries - Gartner Hype Cycle + Opportunity Quadrant
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">Data Mode:</span>
          <button
            onClick={() => setMode(mode === 'dynamic' ? 'static' : 'dynamic')}
            className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
              mode === 'dynamic'
                ? 'bg-green-100 text-green-700 border border-green-300'
                : 'bg-gray-100 text-gray-600 border border-gray-300'
            }`}
          >
            {mode === 'dynamic' ? '⚡ Dynamic' : '📁 Static'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 border-b">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Gartner Hype Cycle */}
      {activeTab === 'gartner' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">Gartner Hype Cycle - AI Verticals</h2>
            
            <ResponsiveContainer width="100%" height={450}>
              <ScatterChart margin={{ top: 20, right: 30, bottom: 60, left: 30 }}>
                <XAxis type="number" dataKey="x" domain={[0, 100]} tick={false} />
                <YAxis type="number" dataKey="y" domain={[0, 110]} tick={false} />
                <ZAxis type="number" range={[0, 0]} />
                
                {/* The hype curve background */}
                <Scatter name="curve" data={HYPE_CURVE} fill="none" line={{ stroke: '#3b82f6', strokeWidth: 3 }} legendType="none" />
                
                {/* Vertical points */}
                <ZAxis type="number" range={[150, 150]} zAxisId="verticals" />
                <Scatter 
                  name="verticals" 
                  data={verticals} 
                  zAxisId="verticals"
                  shape={(props) => {
                    const { cx, cy, payload } = props
                    const color = PHASE_COLORS[payload?.phase] || '#888'
                    return <circle cx={cx} cy={cy} r={10} fill={color} stroke="#fff" strokeWidth={2} />
                  }}
                />
                
                <Tooltip content={<CustomTooltip />} />
              </ScatterChart>
            </ResponsiveContainer>

            {/* Phase labels */}
            <div className="flex justify-between px-8 mt-2 text-xs">
              <div className="text-center" style={{ color: PHASE_COLORS.innovation_trigger }}>
                <div className="font-bold">Innovation</div>
                <div className="font-bold">Trigger</div>
              </div>
              <div className="text-center" style={{ color: PHASE_COLORS.peak_expectations }}>
                <div className="font-bold">Peak of</div>
                <div className="font-bold">Expectations</div>
              </div>
              <div className="text-center" style={{ color: PHASE_COLORS.trough_disillusionment }}>
                <div className="font-bold">Trough of</div>
                <div className="font-bold">Disillusionment</div>
              </div>
              <div className="text-center" style={{ color: PHASE_COLORS.slope_enlightenment }}>
                <div className="font-bold">Slope of</div>
                <div className="font-bold">Enlightenment</div>
              </div>
              <div className="text-center" style={{ color: PHASE_COLORS.plateau_productivity }}>
                <div className="font-bold">Plateau of</div>
                <div className="font-bold">Productivity</div>
              </div>
            </div>
          </div>

          {/* Phase breakdown */}
          <div className="grid grid-cols-5 gap-4">
            {Object.entries(PHASE_INFO).slice(0, 5).map(([phase, info]) => (
              <div key={phase} className="bg-white rounded-lg shadow p-4">
                <div className="font-semibold text-sm mb-2" style={{ color: PHASE_COLORS[phase] }}>
                  {info.label}
                </div>
                <div className="space-y-1">
                  {(byPhase[phase] || []).map(v => (
                    <div key={v.id} className="text-xs flex items-center gap-1">
                      <span>{VERTICAL_ICONS[v.id] || '•'}</span>
                      <span className="truncate">{v.name?.replace('AI + ', '')}</span>
                    </div>
                  ))}
                  {(!byPhase[phase] || byPhase[phase].length === 0) && (
                    <div className="text-xs text-gray-400">None</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quadrant View */}
      {activeTab === 'quadrant' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">Opportunity Quadrant</h2>
            <p className="text-sm text-gray-600 mb-4">
              X-axis: Technical Maturity | Y-axis: Hype/Capital Interest
            </p>
            
            <ResponsiveContainer width="100%" height={500}>
              <ScatterChart margin={{ top: 20, right: 20, bottom: 40, left: 40 }}>
                <XAxis
                  type="number"
                  dataKey="x"
                  domain={[0, 100]}
                  label={{ value: 'Technical Maturity →', position: 'bottom', offset: 20 }}
                />
                <YAxis
                  type="number"
                  dataKey="y"
                  domain={[0, 100]}
                  label={{ value: 'Hype/Capital →', angle: -90, position: 'left', offset: 10 }}
                />
                <ReferenceLine x={50} stroke="#e5e7eb" strokeWidth={2} />
                <ReferenceLine y={50} stroke="#e5e7eb" strokeWidth={2} />
                
                {/* Quadrant labels */}
                <text x={75} y={25} textAnchor="middle" fill="#ef4444" fontSize={12} fontWeight="bold">
                  HOT ZONE ⚡
                </text>
                <text x={25} y={25} textAnchor="middle" fill="#f59e0b" fontSize={12} fontWeight="bold">
                  HYPE ZONE 🔥
                </text>
                <text x={75} y={95} textAnchor="middle" fill="#22c55e" fontSize={12} fontWeight="bold">
                  ALPHA ZONE 💎
                </text>
                <text x={25} y={95} textAnchor="middle" fill="#3b82f6" fontSize={12} fontWeight="bold">
                  EMERGING 🌱
                </text>
                
                <Tooltip content={<CustomTooltip />} />
                
                <Scatter 
                  name="quadrants" 
                  data={quadrants} 
                  shape={(props) => {
                    const { cx, cy, payload } = props
                    const color = QUADRANT_COLORS[payload?.quadrant] || '#888'
                    return <circle cx={cx} cy={cy} r={10} fill={color} stroke="#fff" strokeWidth={2} />
                  }}
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          {/* Quadrant breakdown */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-green-50 rounded-lg p-4 border border-green-200">
              <div className="font-bold text-green-700 mb-2">💎 Alpha Zone (Best)</div>
              <div className="text-xs text-green-600 mb-3">High tech, low hype - undervalued</div>
              <div className="space-y-1">
                {byQuadrant.mature.map(v => (
                  <div key={v.id} className="text-sm flex items-center gap-1">
                    <span>{VERTICAL_ICONS[v.id]}</span>
                    <span>{v.name?.replace('AI + ', '')}</span>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="bg-red-50 rounded-lg p-4 border border-red-200">
              <div className="font-bold text-red-700 mb-2">⚡ Hot Zone</div>
              <div className="text-xs text-red-600 mb-3">High tech, high hype - competitive</div>
              <div className="space-y-1">
                {byQuadrant.hot.map(v => (
                  <div key={v.id} className="text-sm flex items-center gap-1">
                    <span>{VERTICAL_ICONS[v.id]}</span>
                    <span>{v.name?.replace('AI + ', '')}</span>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="bg-yellow-50 rounded-lg p-4 border border-yellow-200">
              <div className="font-bold text-yellow-700 mb-2">🔥 Hype Zone (Risky)</div>
              <div className="text-xs text-yellow-600 mb-3">Low tech, high hype - bubble risk</div>
              <div className="space-y-1">
                {byQuadrant.hyped.map(v => (
                  <div key={v.id} className="text-sm flex items-center gap-1">
                    <span>{VERTICAL_ICONS[v.id]}</span>
                    <span>{v.name?.replace('AI + ', '')}</span>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
              <div className="font-bold text-blue-700 mb-2">🌱 Emerging</div>
              <div className="text-xs text-blue-600 mb-3">Early stage - monitor for breakouts</div>
              <div className="space-y-1">
                {byQuadrant.emerging.map(v => (
                  <div key={v.id} className="text-sm flex items-center gap-1">
                    <span>{VERTICAL_ICONS[v.id]}</span>
                    <span>{v.name?.replace('AI + ', '')}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* All Verticals List */}
      {activeTab === 'list' && (
        <div className="bg-white rounded-lg shadow">
          <div className="p-4 border-b">
            <h2 className="text-lg font-semibold">All AI Verticals ({overview.length})</h2>
          </div>
          <div className="divide-y">
            {overview.map(v => (
              <div key={v.vertical_id} className="p-4 hover:bg-gray-50">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{VERTICAL_ICONS[v.vertical_id] || '🔷'}</span>
                    <div>
                      <div className="font-semibold">{v.name}</div>
                      <div className="text-sm text-gray-500">
                        {v.companies?.slice(0, 4).join(', ')}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="text-sm font-medium">Tech Score</div>
                      <div className="text-lg font-bold text-blue-600">
                        {v.tech_momentum_score?.toFixed(0)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-medium">Hype Score</div>
                      <div className="text-lg font-bold text-orange-600">
                        {v.hype_score?.toFixed(0)}
                      </div>
                    </div>
                    <div 
                      className="px-3 py-1 rounded-full text-xs font-medium"
                      style={{ 
                        backgroundColor: `${PHASE_COLORS[v.hype_phase]}20`,
                        color: PHASE_COLORS[v.hype_phase]
                      }}
                    >
                      {PHASE_INFO[v.hype_phase]?.label || v.hype_phase}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Divergence Signals - Alpha & Bubble Detection */}
      {activeTab === 'divergences' && (
        <div className="space-y-6">
          {/* Summary Stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="text-green-600 text-sm font-medium">Alpha Opportunities</div>
              <div className="text-3xl font-bold text-green-700">{alphaCount}</div>
              <div className="text-xs text-green-600">High tech, low hype - undervalued</div>
            </div>
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="text-red-600 text-sm font-medium">Bubble Warnings</div>
              <div className="text-3xl font-bold text-red-700">{bubbleCount}</div>
              <div className="text-xs text-red-600">Low tech, high hype - overvalued</div>
            </div>
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <div className="text-gray-600 text-sm font-medium">Data Mode</div>
              <div className="text-xl font-bold text-gray-700 capitalize">{dataMode}</div>
              <div className="text-xs text-gray-500">
                {dataMode === 'dynamic' ? 'Real-time computed' : 'Static cached'}
              </div>
            </div>
          </div>

          {/* Divergence List */}
          <div className="bg-white rounded-lg shadow">
            <div className="p-4 border-b">
              <h2 className="text-lg font-semibold">Signal Divergences (sorted by magnitude)</h2>
            </div>
            <div className="divide-y">
              {divergences.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  No significant divergences detected
                </div>
              ) : (
                divergences.map((d, idx) => (
                  <div 
                    key={idx} 
                    className={`p-4 ${d.divergence_type === 'alpha_opportunity' ? 'bg-green-50' : 'bg-red-50'}`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">
                          {d.divergence_type === 'alpha_opportunity' ? '⚡' : '⚠️'}
                        </span>
                        <div>
                          <div className="font-semibold">{d.vertical_name}</div>
                          <div className="text-sm text-gray-600">{d.description}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-6">
                        <div className="text-center">
                          <div className="text-xs text-gray-500">Tech</div>
                          <div className="text-lg font-bold text-blue-600">{d.tech_score?.toFixed(0)}</div>
                        </div>
                        <div className="text-center">
                          <div className="text-xs text-gray-500">Hype</div>
                          <div className="text-lg font-bold text-orange-600">{d.hype_score?.toFixed(0)}</div>
                        </div>
                        <div className="text-center">
                          <div className="text-xs text-gray-500">Magnitude</div>
                          <div className={`text-lg font-bold ${d.divergence_type === 'alpha_opportunity' ? 'text-green-600' : 'text-red-600'}`}>
                            {d.magnitude?.toFixed(1)}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Alerts */}
      {activeTab === 'alerts' && (
        <div className="space-y-4">
          {alerts.length === 0 ? (
            <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
              No active alerts
            </div>
          ) : (
            alerts.map((alert, idx) => (
              <div
                key={idx}
                className={`p-4 rounded-lg border-l-4 ${
                  alert.alert_type === 'alpha_opportunity'
                    ? 'bg-green-50 border-green-500'
                    : 'bg-red-50 border-red-500'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">
                      {alert.alert_type === 'alpha_opportunity' ? '💎' : '⚠️'}
                    </span>
                    <span className="font-bold">{alert.bucket_name}</span>
                  </div>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    alert.severity === 'high' 
                      ? 'bg-red-100 text-red-800'
                      : 'bg-yellow-100 text-yellow-800'
                  }`}>
                    {alert.severity}
                  </span>
                </div>
                <div className="text-sm text-gray-700">{alert.message}</div>
                <div className="mt-2 text-xs text-gray-500">
                  Tech: {alert.tms?.toFixed(0)} | Hype: {alert.ccs?.toFixed(0)}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
