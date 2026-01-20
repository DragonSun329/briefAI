import { useState } from 'react'

/**
 * Article card with expandable summary.
 */
export default function ArticleCard({ article, pipeline }) {
  const [expanded, setExpanded] = useState(false)

  const { title, url, source, weighted_score, paraphrased_content, content, focus_tags } = article

  const summary = paraphrased_content || content || ''
  const truncated = summary.length > 200 ? summary.slice(0, 200) + '...' : summary

  const scoreColor = weighted_score >= 8 ? 'bg-green-500' : weighted_score >= 6 ? 'bg-orange-500' : 'bg-red-500'

  const pipelineColors = {
    news: 'border-l-blue-500',
    product: 'border-l-green-500',
    investing: 'border-l-orange-500',
  }

  return (
    <div className={`bg-white rounded-lg shadow-sm border-l-4 ${pipelineColors[pipeline] || 'border-l-gray-300'} p-4 mb-3`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-gray-900 hover:text-blue-600 line-clamp-2"
        >
          {title}
        </a>
        <span className={`${scoreColor} text-white text-xs px-2 py-1 rounded-full whitespace-nowrap`}>
          {weighted_score?.toFixed(1) || '0.0'}
        </span>
      </div>

      <div className="text-sm text-gray-500 mb-2">
        来源: {source}
      </div>

      {focus_tags?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {focus_tags.slice(0, 5).map(tag => (
            <span key={tag} className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="text-sm text-gray-700">
        {expanded ? summary : truncated}
        {summary.length > 200 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-1 text-blue-600 hover:underline"
          >
            {expanded ? '收起' : '展开'}
          </button>
        )}
      </div>
    </div>
  )
}
