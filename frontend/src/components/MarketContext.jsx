import { useApi } from '../hooks/useApi'

const regimeConfig = {
  risk_on: {
    label: 'Risk-On',
    labelCn: '风险偏好',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
    icon: '🚀',
    description: '市场看涨，利好AI/成长股',
  },
  risk_off: {
    label: 'Risk-Off',
    labelCn: '避险模式',
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    icon: '🛡️',
    description: '市场谨慎，防御性配置',
  },
  transitional: {
    label: 'Transitional',
    labelCn: '过渡期',
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-50',
    borderColor: 'border-yellow-200',
    icon: '⚖️',
    description: '市场方向不明，观望为主',
  },
  high_volatility: {
    label: 'High Vol',
    labelCn: '高波动',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
    icon: '⚡',
    description: '波动加剧，谨慎操作',
  },
  unknown: {
    label: 'Unknown',
    labelCn: '未知',
    color: 'text-gray-600',
    bgColor: 'bg-gray-50',
    borderColor: 'border-gray-200',
    icon: '❓',
    description: '数据不可用',
  },
}

function VixIndicator({ vix }) {
  if (vix === null || vix === undefined) return null
  
  const getVixLevel = (v) => {
    if (v < 15) return { label: '平静', color: 'text-green-600', bg: 'bg-green-500' }
    if (v < 20) return { label: '正常', color: 'text-blue-600', bg: 'bg-blue-500' }
    if (v < 25) return { label: '偏高', color: 'text-yellow-600', bg: 'bg-yellow-500' }
    if (v < 30) return { label: '高', color: 'text-orange-600', bg: 'bg-orange-500' }
    return { label: '极高', color: 'text-red-600', bg: 'bg-red-500' }
  }
  
  const level = getVixLevel(vix)
  const position = Math.min(Math.max((vix / 40) * 100, 0), 100)
  
  return (
    <div className="mt-2">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>VIX恐慌指数</span>
        <span className={`font-medium ${level.color}`}>{vix?.toFixed(1)} ({level.label})</span>
      </div>
      <div className="h-2 bg-gradient-to-r from-green-200 via-yellow-200 to-red-300 rounded-full relative">
        <div 
          className={`absolute w-3 h-3 rounded-full ${level.bg} border-2 border-white shadow -top-0.5`}
          style={{ left: `calc(${position}% - 6px)` }}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-400 mt-0.5">
        <span>10</span>
        <span>20</span>
        <span>30</span>
        <span>40</span>
      </div>
    </div>
  )
}

export default function MarketContext({ compact = false }) {
  const { data, loading, error } = useApi('/api/validation/macro')
  
  if (loading) {
    return (
      <div className={`bg-white rounded-lg shadow p-4 ${compact ? '' : 'col-span-1'}`}>
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-24 mb-2"></div>
          <div className="h-8 bg-gray-200 rounded w-20 mb-2"></div>
          <div className="h-2 bg-gray-200 rounded w-full"></div>
        </div>
      </div>
    )
  }
  
  const regime = data?.regime || 'unknown'
  const config = regimeConfig[regime] || regimeConfig.unknown
  const confidence = (data?.regime_confidence || 0) * 100
  const vix = data?.vix
  const aiSector = data?.ai_sector
  
  return (
    <div className={`bg-white rounded-lg shadow p-4 ${compact ? '' : 'col-span-1'}`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-sm">市场环境</h3>
        <span className="text-xs text-gray-400">
          {data?.timestamp ? new Date(data.timestamp).toLocaleTimeString('zh-CN', { 
            hour: '2-digit', 
            minute: '2-digit' 
          }) : ''}
        </span>
      </div>
      
      {/* Regime badge */}
      <div className={`rounded-lg p-3 ${config.bgColor} border ${config.borderColor} mb-3`}>
        <div className="flex items-center gap-2">
          <span className="text-2xl">{config.icon}</span>
          <div>
            <div className={`font-bold ${config.color}`}>
              {config.labelCn}
            </div>
            <div className="text-xs text-gray-500">{config.label}</div>
          </div>
        </div>
        <div className="text-xs text-gray-600 mt-1">{config.description}</div>
        
        {/* Confidence bar */}
        <div className="mt-2">
          <div className="flex justify-between text-xs text-gray-500 mb-0.5">
            <span>信心度</span>
            <span>{confidence.toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-white rounded-full overflow-hidden">
            <div 
              className={`h-full ${config.color.replace('text-', 'bg-')} rounded-full`}
              style={{ width: `${confidence}%` }}
            />
          </div>
        </div>
      </div>
      
      {/* VIX indicator */}
      <VixIndicator vix={vix} />
      
      {/* AI Sector context */}
      {aiSector && !compact && (
        <div className="mt-3 pt-3 border-t">
          <div className="text-xs text-gray-500 mb-1">AI板块状态</div>
          <div className="flex items-center gap-2">
            <span className={`text-sm font-medium ${
              aiSector.relative_strength === 'outperforming' ? 'text-green-600' :
              aiSector.relative_strength === 'underperforming' ? 'text-red-600' : 'text-gray-600'
            }`}>
              {aiSector.relative_strength === 'outperforming' ? '跑赢大盘 ↑' :
               aiSector.relative_strength === 'underperforming' ? '跑输大盘 ↓' : '持平'}
            </span>
          </div>
          {aiSector.key_drivers && (
            <div className="flex flex-wrap gap-1 mt-1">
              {aiSector.key_drivers.slice(0, 2).map((driver, i) => (
                <span key={i} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                  {driver}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
