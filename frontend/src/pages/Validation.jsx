import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { 
  ResponsiveContainer, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  Cell,
  ScatterChart,
  Scatter,
  CartesianGrid,
  Legend
} from 'recharts'
import MarketContext from '../components/MarketContext'
import AccuracyStats from '../components/AccuracyStats'

// Grade color mapping
const gradeColors = {
  A: '#22c55e', // green-500
  B: '#84cc16', // lime-500
  C: '#eab308', // yellow-500
  D: '#f97316', // orange-500
  F: '#ef4444', // red-500
}

const gradeText = {
  A: '优秀',
  B: '良好',
  C: '合格',
  D: '待改进',
  F: '不合格',
}

function GradeBadge({ grade }) {
  const color = gradeColors[grade] || '#6b7280'
  return (
    <span 
      className="inline-flex items-center justify-center w-8 h-8 rounded-full text-white font-bold text-sm"
      style={{ backgroundColor: color }}
    >
      {grade}
    </span>
  )
}

function ValidationCard({ entity }) {
  const { validation, briefai_signal, market_reality, technicals, ticker } = entity
  const [expanded, setExpanded] = useState(false)
  
  const sentimentColor = briefai_signal?.sentiment > 5 ? 'text-green-600' : 
                         briefai_signal?.sentiment < 5 ? 'text-red-600' : 'text-gray-600'
  
  return (
    <div className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-semibold text-lg">{entity.entity_id?.toUpperCase()}</h3>
          {ticker && <span className="text-xs text-gray-500">${ticker}</span>}
        </div>
        <GradeBadge grade={validation?.grade} />
      </div>
      
      {/* Score bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>验证得分</span>
          <span>{(validation?.score * 100).toFixed(0)}%</span>
        </div>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div 
            className="h-full rounded-full transition-all"
            style={{ 
              width: `${(validation?.score || 0) * 100}%`,
              backgroundColor: gradeColors[validation?.grade] || '#6b7280'
            }}
          />
        </div>
      </div>
      
      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-2 text-sm mb-3">
        <div className="flex items-center gap-1">
          <span className={validation?.direction_aligned ? 'text-green-500' : 'text-red-500'}>
            {validation?.direction_aligned ? '✓' : '✗'}
          </span>
          <span className="text-gray-600">方向一致</span>
        </div>
        <div className="flex items-center gap-1">
          <span className={validation?.technical_confirmed ? 'text-green-500' : 'text-red-500'}>
            {validation?.technical_confirmed ? '✓' : '✗'}
          </span>
          <span className="text-gray-600">技术确认</span>
        </div>
      </div>
      
      {/* Sentiment vs Price */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-gray-50 rounded p-2">
          <div className="text-xs text-gray-500 mb-1">情绪信号</div>
          <div className={`font-semibold ${sentimentColor}`}>
            {briefai_signal?.sentiment?.toFixed(2) || 'N/A'}
          </div>
          <div className="text-xs text-gray-400">
            {briefai_signal?.momentum || 'neutral'}
          </div>
        </div>
        <div className="bg-gray-50 rounded p-2">
          <div className="text-xs text-gray-500 mb-1">价格变动</div>
          <div className={`font-semibold ${
            parseFloat(market_reality?.price_change_5d) > 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            {market_reality?.price_change_5d || 'N/A'}
          </div>
          <div className="text-xs text-gray-400">5日变动</div>
        </div>
      </div>
      
      {/* Expandable details */}
      <button 
        onClick={() => setExpanded(!expanded)}
        className="w-full mt-3 text-xs text-blue-500 hover:text-blue-700"
      >
        {expanded ? '收起详情 ▲' : '展开详情 ▼'}
      </button>
      
      {expanded && (
        <div className="mt-3 pt-3 border-t text-sm">
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div>
              <span className="text-gray-500">RSI(14):</span>
              <span className={`ml-1 font-medium ${
                technicals?.rsi_14 > 70 ? 'text-red-500' : 
                technicals?.rsi_14 < 30 ? 'text-green-500' : 'text-gray-700'
              }`}>
                {technicals?.rsi_14?.toFixed(1) || 'N/A'}
              </span>
            </div>
            <div>
              <span className="text-gray-500">SMA20距离:</span>
              <span className="ml-1 font-medium">{technicals?.sma_20_distance || 'N/A'}</span>
            </div>
          </div>
          <div className="text-xs text-gray-600">
            <div className="font-medium mb-1">验证备注:</div>
            <ul className="list-disc list-inside space-y-0.5">
              {validation?.notes?.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

function GradeDistributionChart({ distribution }) {
  const data = Object.entries(distribution || {}).map(([grade, count]) => ({
    grade,
    count,
    fill: gradeColors[grade] || '#6b7280',
  }))
  
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="font-semibold mb-3">评级分布</h3>
      <ResponsiveContainer width="100%" height={150}>
        <BarChart data={data} layout="vertical">
          <XAxis type="number" />
          <YAxis dataKey="grade" type="category" width={30} />
          <Tooltip 
            formatter={(value, name, props) => [
              `${value} 个实体`,
              `${props.payload.grade}级 (${gradeText[props.payload.grade]})`
            ]}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function SentimentPriceChart({ entities }) {
  // Transform for scatter plot: sentiment vs 5-day price change
  const data = (entities || [])
    .filter(e => e.briefai_signal?.sentiment && e.market_reality?.price_change_5d)
    .map(e => ({
      name: e.entity_id,
      sentiment: e.briefai_signal.sentiment,
      priceChange: parseFloat(e.market_reality.price_change_5d?.replace('%', '')) || 0,
      grade: e.validation?.grade,
    }))
  
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="font-semibold mb-3">情绪 vs 价格变动</h3>
      <ResponsiveContainer width="100%" height={250}>
        <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="sentiment" 
            type="number" 
            domain={[0, 10]} 
            name="Sentiment"
            label={{ value: '情绪', position: 'bottom', offset: 0 }}
          />
          <YAxis 
            dataKey="priceChange" 
            type="number"
            name="Price %"
            label={{ value: '价格%', angle: -90, position: 'left' }}
          />
          <Tooltip 
            formatter={(value, name) => [
              typeof value === 'number' ? value.toFixed(2) : value,
              name === 'sentiment' ? '情绪' : '价格变动%'
            ]}
            labelFormatter={(label) => `${label}`}
          />
          <Legend />
          <Scatter 
            name="实体" 
            data={data} 
            fill="#3b82f6"
          >
            {data.map((entry, index) => (
              <Cell 
                key={`cell-${index}`} 
                fill={gradeColors[entry.grade] || '#6b7280'} 
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Validation() {
  const [minGrade, setMinGrade] = useState(null)
  
  const { data, loading, error, refetch } = useApi(
    `/api/validation/scores?limit=50${minGrade ? `&min_grade=${minGrade}` : ''}`
  )
  
  if (loading) {
    return <div className="text-center py-8">加载验证数据中...</div>
  }
  
  if (error) {
    return (
      <div className="text-center py-8 text-red-500">
        加载失败: {error}
        <button onClick={refetch} className="ml-2 text-blue-500 underline">重试</button>
      </div>
    )
  }
  
  const { summary, grade_distribution, entities, generated_at } = data || {}
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-semibold">信号验证仪表板</h2>
          <p className="text-sm text-gray-500">
            验证时间: {generated_at ? new Date(generated_at).toLocaleString('zh-CN') : 'N/A'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Grade filter */}
          <select
            value={minGrade || ''}
            onChange={(e) => setMinGrade(e.target.value || null)}
            className="border rounded px-3 py-1.5 text-sm"
          >
            <option value="">全部评级</option>
            <option value="A">A级及以上</option>
            <option value="B">B级及以上</option>
            <option value="C">C级及以上</option>
          </select>
          
          <button
            onClick={refetch}
            className="px-4 py-1.5 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm"
          >
            🔄 刷新
          </button>
        </div>
      </div>
      
      {/* Top panels row */}
      <div className="grid grid-cols-4 gap-4">
        {/* Market Context */}
        <MarketContext />
        
        {/* Accuracy Stats */}
        <AccuracyStats />
        
        {/* Summary stats */}
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-semibold mb-3 text-sm">验证摘要</h3>
          <div className="space-y-3">
            <div>
              <div className="text-xs text-gray-500">平均验证得分</div>
              <div className="text-2xl font-bold text-blue-600">
                {((summary?.average_validation_score || 0) * 100).toFixed(0)}%
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="bg-green-50 rounded p-2">
                <div className="text-lg font-semibold text-green-600">
                  {summary?.direction_aligned_pct?.toFixed(0) || 0}%
                </div>
                <div className="text-xs text-gray-500">方向一致</div>
              </div>
              <div className="bg-blue-50 rounded p-2">
                <div className="text-lg font-semibold text-blue-600">
                  {summary?.technical_confirmed_pct?.toFixed(0) || 0}%
                </div>
                <div className="text-xs text-gray-500">技术确认</div>
              </div>
            </div>
          </div>
        </div>
        
        {/* Grade distribution */}
        <GradeDistributionChart distribution={grade_distribution} />
      </div>
      
      {/* Sentiment vs Price scatter */}
      <SentimentPriceChart entities={entities} />
      
      {/* Entity cards grid */}
      <div>
        <h3 className="font-semibold mb-3">实体验证详情 ({entities?.length || 0})</h3>
        <div className="grid grid-cols-4 gap-4">
          {(entities || []).map(entity => (
            <ValidationCard key={entity.entity_id} entity={entity} />
          ))}
        </div>
      </div>
    </div>
  )
}
