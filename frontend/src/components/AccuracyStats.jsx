import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'

const COLORS = {
  funding: '#3b82f6',      // blue
  product_launch: '#22c55e', // green
  breakout: '#f59e0b',     // amber
  other: '#6b7280',        // gray
}

const eventTypeLabels = {
  funding: '融资',
  product_launch: '产品发布',
  breakout: '突破',
}

function AccuracyRing({ accuracy }) {
  const pct = (accuracy || 0) * 100
  const data = [
    { name: 'correct', value: pct },
    { name: 'incorrect', value: 100 - pct },
  ]
  
  return (
    <div className="relative w-24 h-24 mx-auto">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            innerRadius={30}
            outerRadius={40}
            startAngle={90}
            endAngle={-270}
            dataKey="value"
            stroke="none"
          >
            <Cell fill="#22c55e" />
            <Cell fill="#e5e7eb" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold text-green-600">{pct.toFixed(0)}%</span>
      </div>
    </div>
  )
}

function EventTypeBreakdown({ byEventType }) {
  if (!byEventType) return null
  
  const data = Object.entries(byEventType).map(([type, stats]) => ({
    name: eventTypeLabels[type] || type,
    type,
    correct: stats.correct || 0,
    incorrect: stats.incorrect || 0,
    total: (stats.correct || 0) + (stats.incorrect || 0),
    accuracy: stats.correct / ((stats.correct || 0) + (stats.incorrect || 0) + 0.001),
  }))
  
  return (
    <div className="space-y-2">
      {data.map(({ name, type, correct, total, accuracy }) => (
        <div key={type} className="flex items-center gap-2">
          <div 
            className="w-2 h-2 rounded-full" 
            style={{ backgroundColor: COLORS[type] || COLORS.other }}
          />
          <span className="text-xs text-gray-600 flex-1">{name}</span>
          <span className="text-xs font-medium">
            {correct}/{total}
          </span>
          <span className="text-xs text-green-600 font-medium w-10 text-right">
            {(accuracy * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  )
}

export default function AccuracyStats({ detailed = false }) {
  const [horizon, setHorizon] = useState(60)
  
  const { data, loading, error } = useApi(`/api/predictions/accuracy?horizon=${horizon}`)
  const { data: horizons } = useApi('/api/predictions/horizons')
  
  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-24 mb-2"></div>
          <div className="h-24 bg-gray-200 rounded-full w-24 mx-auto mb-2"></div>
          <div className="h-3 bg-gray-200 rounded w-full"></div>
        </div>
      </div>
    )
  }
  
  if (error || !data?.success) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="font-semibold text-sm mb-2">预测准确度</h3>
        <div className="text-center text-gray-500 text-sm py-4">
          数据暂不可用
        </div>
      </div>
    )
  }
  
  const { 
    accuracy, 
    detection_rate, 
    avg_lead_time, 
    total_predictions,
    correct_predictions,
    by_event_type,
    generated_at 
  } = data
  
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-sm">预测准确度</h3>
        {horizons?.horizons?.length > 1 && (
          <select
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
            className="text-xs border rounded px-1 py-0.5"
          >
            {horizons.horizons.map(h => (
              <option key={h.days} value={h.days}>{h.days}天</option>
            ))}
          </select>
        )}
      </div>
      
      {/* Main accuracy ring */}
      <AccuracyRing accuracy={accuracy} />
      
      {/* Stats */}
      <div className="grid grid-cols-2 gap-2 mt-3 text-center">
        <div className="bg-blue-50 rounded p-2">
          <div className="text-lg font-semibold text-blue-600">
            {(detection_rate * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-gray-500">检测率</div>
        </div>
        <div className="bg-purple-50 rounded p-2">
          <div className="text-lg font-semibold text-purple-600">
            {avg_lead_time?.toFixed(0) || 0}天
          </div>
          <div className="text-xs text-gray-500">平均提前</div>
        </div>
      </div>
      
      {/* Event type breakdown */}
      <div className="mt-3 pt-3 border-t">
        <div className="text-xs text-gray-500 mb-2">按事件类型</div>
        <EventTypeBreakdown byEventType={by_event_type} />
      </div>
      
      {/* Predictions summary */}
      <div className="mt-3 pt-3 border-t text-xs text-gray-500 text-center">
        {correct_predictions || 0} / {total_predictions || 0} 预测正确
        <br />
        <span className="text-gray-400">
          {horizon}天窗口 · 数据截至 {generated_at ? new Date(generated_at).toLocaleDateString('zh-CN') : 'N/A'}
        </span>
      </div>
      
      {/* Link to backtest */}
      {detailed && (
        <a 
          href="/backtest" 
          className="block mt-3 text-center text-xs text-blue-500 hover:text-blue-700"
        >
          查看完整回测报告 →
        </a>
      )}
    </div>
  )
}
