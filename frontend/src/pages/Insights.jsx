import { useApi } from '../hooks/useApi'
import StatCard from '../components/StatCard'
import BubbleChart from '../components/BubbleChart'

export default function Insights({ date }) {
  const { data, loading, error } = useApi(date ? `/api/insights?date=${date}` : null)

  if (loading) return <div className="text-center py-8">加载中...</div>
  if (error) return <div className="text-red-500 py-8">错误: {error}</div>
  if (!data) return null

  const { summary, bubble_data, hot_entities } = data

  return (
    <div>
      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard
          icon="📰"
          label="AI新闻"
          value={summary.pipeline_counts.news}
          color="blue"
        />
        <StatCard
          icon="🚀"
          label="产品"
          value={summary.pipeline_counts.product}
          color="green"
        />
        <StatCard
          icon="💰"
          label="投资"
          value={summary.pipeline_counts.investing}
          color="orange"
        />
        <StatCard
          icon="🔗"
          label="跨管道实体"
          value={summary.cross_pipeline_entities}
          color="purple"
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-5 gap-6">
        {/* Bubble Chart */}
        <div className="col-span-3 bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-4">实体跨管道分布</h2>
          <BubbleChart data={bubble_data} />
        </div>

        {/* Hot Entities */}
        <div className="col-span-2 bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-4">热门实体</h2>
          <div className="space-y-2">
            {(hot_entities || []).map((e, idx) => (
              <div
                key={e.entity_name}
                className="flex items-center justify-between p-2 bg-gray-50 rounded"
              >
                <div>
                  <span className="text-gray-400 text-sm mr-2">#{idx + 1}</span>
                  <span className="font-medium">{e.entity_name}</span>
                  <span className="text-xs text-gray-500 ml-2">({e.entity_type})</span>
                </div>
                <div className="text-sm">
                  <span className="text-blue-600 font-semibold">{e.total_mentions}</span>
                  <span className="text-gray-400 ml-1">次</span>
                  <span className="text-gray-300 mx-1">|</span>
                  <span className="text-green-600">{e.pipeline_count}</span>
                  <span className="text-gray-400 ml-1">管道</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}