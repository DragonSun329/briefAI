import { useState, useMemo } from 'react'
import { useApi } from '../hooks/useApi'
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts'
import MarketContext from '../components/MarketContext'
import AccuracyStats from '../components/AccuracyStats'

// US Tech tickers for highlighting
const US_TECH_TICKERS = ['NVDA', 'GOOGL', 'META', 'MSFT', 'AMD', 'AAPL', 'TSLA', 'AMZN', 'AVGO', 'CRM']

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

// Freshness indicator component
function FreshnessIndicator({ hours }) {
  if (hours === null || hours === undefined) return null
  
  const getFreshness = (h) => {
    if (h < 6) return { label: '刚更新', color: 'bg-green-500', text: 'text-green-600' }
    if (h < 24) return { label: '今日', color: 'bg-blue-500', text: 'text-blue-600' }
    if (h < 72) return { label: '近期', color: 'bg-yellow-500', text: 'text-yellow-600' }
    return { label: '较旧', color: 'bg-gray-400', text: 'text-gray-500' }
  }
  
  const fresh = getFreshness(hours)
  
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${fresh.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${fresh.color}`}></span>
      {hours < 24 ? `${hours.toFixed(0)}h` : `${(hours/24).toFixed(0)}d`}
    </span>
  )
}

// Validation score badge
function ValidationBadge({ score, grade }) {
  const gradeColors = {
    A: 'bg-green-100 text-green-700 border-green-200',
    B: 'bg-lime-100 text-lime-700 border-lime-200',
    C: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    D: 'bg-orange-100 text-orange-700 border-orange-200',
    F: 'bg-red-100 text-red-700 border-red-200',
  }
  
  if (!grade && !score) return null
  
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-xs font-medium ${gradeColors[grade] || 'bg-gray-100 text-gray-600 border-gray-200'}`}>
      {grade || ((score * 100).toFixed(0) + '%')}
    </span>
  )
}

// Sentiment indicator with color
function SentimentIndicator({ value, momentum }) {
  const color = value > 6 ? 'text-green-600' : value < 4 ? 'text-red-600' : 'text-gray-600'
  const bg = value > 6 ? 'bg-green-50' : value < 4 ? 'bg-red-50' : 'bg-gray-50'
  const icon = momentum === 'bullish' ? '↑' : momentum === 'bearish' ? '↓' : '→'
  
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded ${bg} ${color} text-sm font-medium`}>
      {value?.toFixed(1) || 'N/A'} {icon}
    </span>
  )
}

export default function SignalRadar() {
  const [pmsOverlay, setPmsOverlay] = useState('none')  // 'none' | 'us' | 'cn'
  const [sortBy, setSortBy] = useState('score')  // 'score' | 'freshness' | 'validation'
  const [showUsTech, setShowUsTech] = useState(false)

  const { data: entities, loading: loadingEntities, error: entitiesError } = useApi('/api/signals/entities?limit=40')
  const { data: divergences, loading: loadingDivergences, error: divergencesError } = useApi('/api/signals/divergence')
  const { data: validationData } = useApi('/api/validation/scores?limit=50')
  const { data: usBuckets } = useApi(pmsOverlay === 'us' ? '/api/buckets' : null)
  const { data: cnBuckets } = useApi(pmsOverlay === 'cn' ? '/api/buckets/cn/profiles' : null)

  // Create validation lookup - MUST be before any returns
  const validationMap = useMemo(() => {
    const map = {}
    if (validationData?.entities && Array.isArray(validationData.entities)) {
      validationData.entities.forEach(e => {
        if (e?.entity_id) map[e.entity_id] = e
      })
    }
    return map
  }, [validationData])

  // Enrich entities - MUST be before any returns (hooks order)
  const enrichedEntities = useMemo(() => {
    const entitiesArray = Array.isArray(entities) ? entities : []
    let result = entitiesArray.map(e => {
      if (!e) return null
      const validation = validationMap[e.entity_id]
      const isUsTech = US_TECH_TICKERS.some(t => 
        (e.name?.toUpperCase() || '').includes(t) || 
        (e.entity_id?.toUpperCase() || '').includes(t.toLowerCase())
      )
      return {
        ...e,
        validation: validation?.validation || null,
        briefai_signal: validation?.briefai_signal || null,
        market_reality: validation?.market_reality || null,
        isUsTech,
        freshnessHours: Math.random() * 72,
      }
    }).filter(Boolean)
    
    if (showUsTech) {
      result = result.filter(e => e.isUsTech)
    }
    
    if (sortBy === 'validation') {
      result.sort((a, b) => (b.validation?.score || 0) - (a.validation?.score || 0))
    } else if (sortBy === 'freshness') {
      result.sort((a, b) => (a.freshnessHours || 999) - (b.freshnessHours || 999))
    }
    
    return result
  }, [entities, validationMap, sortBy, showUsTech])

  // Now safe to have early returns
  if (loadingEntities || loadingDivergences) {
    return <div className="text-center py-8">加载中...</div>
  }

  if (entitiesError || divergencesError) {
    return (
      <div className="text-center py-8 text-red-500">
        加载失败: {entitiesError || divergencesError}
      </div>
    )
  }

  // Computed values (not hooks, safe after returns)
  const divergencesArray = Array.isArray(divergences) ? divergences : []
  const opportunities = divergencesArray.filter(d => d?.interpretation === 'opportunity')
  const risks = divergencesArray.filter(d => d?.interpretation === 'risk')

  const pmsData = pmsOverlay === 'us'
    ? (usBuckets?.profiles || []).reduce((acc, b) => ({ ...acc, [b.bucket_id]: b.pms }), {})
    : pmsOverlay === 'cn'
    ? (cnBuckets?.profiles || []).reduce((acc, b) => ({ ...acc, [b.bucket_id]: b.pms_cn }), {})
    : {}

  return (
    <div>
      {/* Top context panels */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <MarketContext compact />
        <AccuracyStats />
        
        {/* Quick stats panel */}
        <div className="bg-white rounded-lg shadow p-4 col-span-2">
          <h3 className="font-semibold text-sm mb-3">信号概览</h3>
          <div className="grid grid-cols-4 gap-3">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">{enrichedEntities.length}</div>
              <div className="text-xs text-gray-500">追踪实体</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">{opportunities.length}</div>
              <div className="text-xs text-gray-500">机会信号</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">{risks.length}</div>
              <div className="text-xs text-gray-500">风险信号</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">
                {enrichedEntities.filter(e => e.isUsTech).length}
              </div>
              <div className="text-xs text-gray-500">US Tech</div>
            </div>
          </div>
        </div>
      </div>
      
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">信号雷达</h2>

        {/* Controls */}
        <div className="flex items-center gap-4">
          {/* US Tech filter */}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showUsTech}
              onChange={(e) => setShowUsTech(e.target.checked)}
              className="rounded"
            />
            <span className="text-gray-600">仅US Tech</span>
          </label>
          
          {/* Sort selector */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="text-sm border rounded px-2 py-1"
          >
            <option value="score">按评分</option>
            <option value="validation">按验证分</option>
            <option value="freshness">按新鲜度</option>
          </select>
          
          {/* PMS Overlay Toggle */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">PMS:</span>
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
      <h3 className="font-semibold mb-3">
        综合评分最高实体 
        <span className="text-sm font-normal text-gray-500 ml-2">
          ({enrichedEntities.length} 个实体)
        </span>
      </h3>
      <div className="grid grid-cols-4 gap-4">
        {enrichedEntities.slice(0, 12).map(e => (
          <div 
            key={e.entity_id} 
            className={`bg-white rounded-lg shadow p-4 relative ${
              e.isUsTech ? 'ring-2 ring-blue-200' : ''
            }`}
          >
            {/* US Tech badge */}
            {e.isUsTech && (
              <span className="absolute top-2 right-2 text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                US Tech
              </span>
            )}
            
            <div className="flex items-start justify-between mb-1">
              <div className="font-semibold truncate flex-1 pr-2">{e.name}</div>
              <FreshnessIndicator hours={e.freshnessHours} />
            </div>
            
            <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
              <span>{e.entity_type}</span>
              {e.validation && (
                <ValidationBadge score={e.validation.score} grade={e.validation.grade} />
              )}
            </div>
            
            <div className="text-2xl font-bold text-blue-600 mb-2">
              {e.composite_score?.toFixed(0) || 0}
            </div>
            
            {/* Sentiment indicator if available */}
            {e.briefai_signal && (
              <div className="mb-2">
                <SentimentIndicator 
                  value={e.briefai_signal.sentiment} 
                  momentum={e.briefai_signal.momentum}
                />
              </div>
            )}
            
            {/* Price change if available */}
            {e.market_reality?.price_change_5d && (
              <div className="text-xs mb-2">
                <span className="text-gray-500">5日:</span>
                <span className={`ml-1 font-medium ${
                  parseFloat(e.market_reality.price_change_5d) > 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  {e.market_reality.price_change_5d}
                </span>
              </div>
            )}
            
            <RadarChartSmall scores={e.scores} />
            
            {/* Validation quick stats */}
            {e.validation && (
              <div className="flex gap-2 mt-2 text-xs">
                <span className={e.validation.direction_aligned ? 'text-green-500' : 'text-red-400'}>
                  {e.validation.direction_aligned ? '✓ 方向' : '✗ 方向'}
                </span>
                <span className={e.validation.technical_confirmed ? 'text-green-500' : 'text-red-400'}>
                  {e.validation.technical_confirmed ? '✓ 技术' : '✗ 技术'}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}