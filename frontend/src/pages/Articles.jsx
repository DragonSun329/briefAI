import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import ArticleCard from '../components/ArticleCard'

export default function Articles({ date, pipeline }) {
  const [searchTerm, setSearchTerm] = useState('')
  const { data, loading, error } = useApi(
    date ? `/api/articles/${pipeline}?date=${date}` : null
  )

  if (loading) return <div className="text-center py-8">加载中...</div>
  if (error) return <div className="text-red-500 py-8">错误: {error}</div>
  if (!data) return null

  const filteredArticles = (data.articles || []).filter(a =>
    a.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    a.source.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const pipelineNames = {
    news: 'AI新闻',
    product: '产品',
    investing: '投资',
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">
          {pipelineNames[pipeline]} ({data.total} 篇)
        </h2>
        <input
          type="text"
          placeholder="搜索文章..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="border rounded px-3 py-2 w-64"
        />
      </div>

      <div className="space-y-2">
        {filteredArticles.map(article => (
          <ArticleCard
            key={article.id}
            article={article}
            pipeline={pipeline}
          />
        ))}
      </div>

      {filteredArticles.length === 0 && (
        <div className="text-center text-gray-500 py-8">
          没有找到匹配的文章
        </div>
      )}
    </div>
  )
}