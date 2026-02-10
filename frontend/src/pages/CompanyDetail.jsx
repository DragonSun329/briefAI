import { useParams, Link, useSearchParams } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useApi } from '../hooks/useApi'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts'

/**
 * Format large numbers for display.
 */
function formatNumber(num, prefix = '') {
  if (!num || num === 0) return '-'
  if (num >= 1e12) return `${prefix}${(num / 1e12).toFixed(2)}T`
  if (num >= 1e9) return `${prefix}${(num / 1e9).toFixed(2)}B`
  if (num >= 1e6) return `${prefix}${(num / 1e6).toFixed(1)}M`
  if (num >= 1e3) return `${prefix}${(num / 1e3).toFixed(1)}K`
  return `${prefix}${num.toLocaleString()}`
}

/**
 * Stock price header with key metrics.
 */
function StockHeader({ quote, name, ticker }) {
  if (!quote) return null

  const isPositive = quote.change >= 0
  const changeColor = isPositive ? 'text-green-600' : 'text-red-600'
  const changeSign = isPositive ? '+' : ''

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{name}</h1>
          <p className="text-gray-500">{ticker} · NASDAQ</p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold">${quote.price?.toFixed(2)}</div>
          <div className={`text-lg ${changeColor}`}>
            {changeSign}${quote.change?.toFixed(2)} ({changeSign}{quote.change_pct?.toFixed(2)}%)
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <span className="text-gray-500">Prev Close</span>
          <div className="font-medium">${quote.prev_close?.toFixed(2)}</div>
        </div>
        <div>
          <span className="text-gray-500">Open</span>
          <div className="font-medium">${quote.open_price?.toFixed(2)}</div>
        </div>
        <div>
          <span className="text-gray-500">Day Range</span>
          <div className="font-medium">${quote.day_low?.toFixed(2)} - ${quote.day_high?.toFixed(2)}</div>
        </div>
        <div>
          <span className="text-gray-500">52W Range</span>
          <div className="font-medium">${quote.week_52_low?.toFixed(2)} - ${quote.week_52_high?.toFixed(2)}</div>
        </div>
        <div>
          <span className="text-gray-500">Volume</span>
          <div className="font-medium">{formatNumber(quote.volume)}</div>
        </div>
        <div>
          <span className="text-gray-500">Avg Volume</span>
          <div className="font-medium">{formatNumber(quote.avg_volume)}</div>
        </div>
        <div>
          <span className="text-gray-500">Market Cap</span>
          <div className="font-medium">{formatNumber(quote.market_cap, '$')}</div>
        </div>
        <div>
          <span className="text-gray-500">P/E Ratio</span>
          <div className="font-medium">{quote.pe_ratio?.toFixed(2) || '-'}</div>
        </div>
      </div>
    </div>
  )
}

/**
 * Stock price chart.
 */
function StockChart({ history, period, onPeriodChange, loading, error, onRetry }) {
  const periods = ['1d', '5d', '1mo', '6mo', 'ytd', '1y', '5y', 'max']

  // Period buttons component (reused in all states)
  const PeriodButtons = () => (
    <div className="flex gap-1">
      {periods.map(p => (
        <button
          key={p}
          onClick={() => onPeriodChange(p)}
          disabled={loading}
          className={`px-3 py-1 text-sm rounded ${
            period === p
              ? 'bg-blue-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {p.toUpperCase()}
        </button>
      ))}
    </div>
  )

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Price History</h2>
          <PeriodButtons />
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          <span className="ml-2 text-gray-500 text-sm">Loading chart...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Price History</h2>
          <PeriodButtons />
        </div>
        <div className="text-center py-8">
          <p className="text-gray-500 mb-3">Unable to load price data</p>
          <button
            onClick={onRetry}
            className="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!history || history.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Price History</h2>
          <PeriodButtons />
        </div>
        <div className="text-center text-gray-500 py-8">
          No price history available for this period
        </div>
      </div>
    )
  }

  const isPositive = history.length > 1 && history[history.length - 1].close >= history[0].close
  const chartColor = isPositive ? '#10B981' : '#EF4444'

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Price History</h2>
        <div className="flex gap-1">
          {periods.map(p => (
            <button
              key={p}
              onClick={() => onPeriodChange(p)}
              className={`px-3 py-1 text-sm rounded ${
                period === p
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={history}>
          <defs>
            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={chartColor} stopOpacity={0.3}/>
              <stop offset="95%" stopColor={chartColor} stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12 }}
            tickFormatter={(val) => val.slice(5)}
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fontSize: 12 }}
            tickFormatter={(val) => `$${val}`}
          />
          <Tooltip
            formatter={(val) => [`$${val.toFixed(2)}`, 'Price']}
            labelFormatter={(label) => `Date: ${label}`}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke={chartColor}
            fillOpacity={1}
            fill="url(#colorPrice)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Prediction markets section.
 */
function PredictionMarkets({ markets }) {
  if (!markets || markets.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Related Prediction Markets</h2>
        <p className="text-gray-500 text-center py-4">No prediction markets found for this company</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-lg font-semibold mb-4">Related Prediction Markets</h2>
      <div className="space-y-4">
        {markets.slice(0, 5).map((market, idx) => {
          const probColor = market.probability > 50 ? 'text-green-600' : market.probability > 30 ? 'text-orange-500' : 'text-red-500'
          return (
            <div key={idx} className="border-b pb-4 last:border-0">
              <div className="flex justify-between items-start">
                <div className="flex-1 pr-4">
                  <p className="font-medium text-gray-900">{market.question}</p>
                  <div className="flex items-center gap-2 mt-1 text-sm text-gray-500">
                    <span className="bg-gray-100 px-2 py-0.5 rounded">{market.source}</span>
                    {market.volume > 0 && <span>Vol: {formatNumber(market.volume, '$')}</span>}
                  </div>
                </div>
                <div className={`text-2xl font-bold ${probColor}`}>
                  {market.probability?.toFixed(0)}%
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Product Reviews section.
 */
function ProductReviews({ reviews }) {
  if (!reviews) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Product Reviews</h2>
        <p className="text-gray-500 text-center py-4">No review data available for this company</p>
      </div>
    )
  }

  const scoreColor = reviews.consensus_score >= 90 ? 'text-green-600' :
                     reviews.consensus_score >= 80 ? 'text-green-500' :
                     reviews.consensus_score >= 70 ? 'text-yellow-600' :
                     'text-red-500'

  const confidenceBadge = {
    high: 'bg-green-100 text-green-700',
    medium: 'bg-yellow-100 text-yellow-700',
    low: 'bg-gray-100 text-gray-600',
  }[reviews.confidence] || 'bg-gray-100 text-gray-600'

  const confidenceLabel = {
    high: 'High Confidence',
    medium: 'Medium Confidence',
    low: 'Low Confidence',
  }[reviews.confidence] || 'Unknown'

  const formatCount = (count) => {
    if (count >= 1000) return `${(count / 1000).toFixed(1)}k`
    return count.toLocaleString()
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Product Reviews</h2>
        <span className={`text-xs px-2 py-1 rounded ${confidenceBadge}`}>
          {confidenceLabel}
        </span>
      </div>

      {/* Summary score */}
      <div className="flex items-center gap-6 mb-6 pb-4 border-b">
        <div className="text-center">
          <div className={`text-4xl font-bold ${scoreColor}`}>
            {reviews.consensus_score.toFixed(0)}
          </div>
          <div className="text-sm text-gray-500">Consensus Score</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-semibold text-gray-800">
            {reviews.average_rating.toFixed(1)}/5
          </div>
          <div className="text-sm text-gray-500">Avg Rating</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-semibold text-gray-800">
            {formatCount(reviews.total_reviews)}
          </div>
          <div className="text-sm text-gray-500">Total Reviews</div>
        </div>
      </div>

      {/* Per-source breakdown */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-gray-700 mb-2">Review Sources</h3>
        {reviews.sources.map((source, idx) => {
          const starWidth = (source.rating / 5) * 100
          return (
            <div key={idx} className="flex items-center justify-between py-2 border-b last:border-0">
              <div className="flex items-center gap-3">
                <span className="font-medium text-gray-800 w-28">{source.source}</span>
                <div className="flex items-center gap-2">
                  {/* Star rating visual */}
                  <div className="relative w-24 h-4">
                    <div className="absolute inset-0 flex">
                      {[1, 2, 3, 4, 5].map(i => (
                        <svg key={i} className="w-4 h-4 text-gray-200" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                        </svg>
                      ))}
                    </div>
                    <div className="absolute inset-0 flex overflow-hidden" style={{ width: `${starWidth}%` }}>
                      {[1, 2, 3, 4, 5].map(i => (
                        <svg key={i} className="w-4 h-4 text-yellow-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                        </svg>
                      ))}
                    </div>
                  </div>
                  <span className="text-sm font-medium text-gray-700">{source.rating.toFixed(1)}</span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-500">
                  {formatCount(source.review_count)} reviews
                </span>
                {source.url && (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline text-sm"
                  >
                    View
                  </a>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Last updated */}
      {reviews.last_updated && (
        <div className="mt-4 text-xs text-gray-400 text-right">
          Last updated: {reviews.last_updated}
        </div>
      )}
    </div>
  )
}

/**
 * Recent news section.
 */
function RecentNews({ news }) {
  if (!news || news.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Recent News</h2>
        <p className="text-gray-500 text-center py-4">No recent news found</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-lg font-semibold mb-4">Recent News</h2>
      <div className="space-y-4">
        {news.slice(0, 5).map((article, idx) => (
          <div key={idx} className="border-b pb-4 last:border-0">
            <div className="flex justify-between items-start">
              <div className="flex-1">
                {article.url ? (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-blue-600 hover:underline"
                  >
                    {article.title}
                  </a>
                ) : (
                  <p className="font-medium text-gray-900">{article.title}</p>
                )}
                {article.summary && (
                  <p className="text-sm text-gray-600 mt-1 line-clamp-2">{article.summary}</p>
                )}
                <div className="flex items-center gap-2 mt-1 text-sm text-gray-500">
                  <span>{article.source}</span>
                  <span>·</span>
                  <span>{article.date}</span>
                </div>
              </div>
              {article.score > 0 && (
                <span className={`ml-2 px-2 py-1 rounded text-sm ${
                  article.score >= 8 ? 'bg-green-100 text-green-700' :
                  article.score >= 6 ? 'bg-orange-100 text-orange-700' :
                  'bg-red-100 text-red-700'
                }`}>
                  {article.score.toFixed(1)}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * Company info sidebar.
 */
function CompanyInfo({ company }) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">Company Info</h2>

      <dl className="space-y-3 text-sm">
        {company.ticker && (
          <div>
            <dt className="text-gray-500">Ticker</dt>
            <dd className="font-medium">{company.ticker}</dd>
          </div>
        )}
        <div>
          <dt className="text-gray-500">Category</dt>
          <dd className="font-medium">{company.category_zh}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Funding Stage</dt>
          <dd className="font-medium">{company.funding_stage_zh}</dd>
        </div>
        {company.total_funding && (
          <div>
            <dt className="text-gray-500">Total Funding</dt>
            <dd className="font-medium">{formatNumber(company.total_funding, '$')}</dd>
          </div>
        )}
        {company.employee_count && (
          <div>
            <dt className="text-gray-500">Employees</dt>
            <dd className="font-medium">{company.employee_count}</dd>
          </div>
        )}
        {company.founded_year && (
          <div>
            <dt className="text-gray-500">Founded</dt>
            <dd className="font-medium">{company.founded_year}</dd>
          </div>
        )}
        {company.country && (
          <div>
            <dt className="text-gray-500">Country</dt>
            <dd className="font-medium">{company.country}</dd>
          </div>
        )}
        {company.cb_rank && (
          <div>
            <dt className="text-gray-500">CB Rank</dt>
            <dd className="font-medium">#{company.cb_rank.toLocaleString()}</dd>
          </div>
        )}
        {company.website && (
          <div>
            <dt className="text-gray-500">Website</dt>
            <dd>
              <a
                href={company.website.startsWith('http') ? company.website : `https://${company.website}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                {company.website.replace(/^https?:\/\//, '').replace(/\/$/, '')}
              </a>
            </dd>
          </div>
        )}
      </dl>

      {company.description && (
        <div className="mt-4 pt-4 border-t">
          <p className="text-sm text-gray-600 line-clamp-5">{company.description}</p>
        </div>
      )}
    </div>
  )
}

/**
 * Main company detail page.
 */
export default function CompanyDetail() {
  const { companyId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const [period, setPeriod] = useState(searchParams.get('period') || '1mo')
  const [stockHistory, setStockHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState(false)
  const [historyCache, setHistoryCache] = useState({}) // Cache: { period: historyData[] }
  const [retryCount, setRetryCount] = useState(0) // Trigger refetch

  // Load company data (instant - no yfinance call)
  const { data: company, loading, error } = useApi(
    companyId ? `/api/companies/${companyId}` : null
  )

  // Lazy-load stock history when company loads and has a ticker
  useEffect(() => {
    if (!company?.ticker) {
      setStockHistory([])
      return
    }

    // Check cache first
    const cacheKey = `${companyId}-${period}`
    if (historyCache[cacheKey]) {
      setStockHistory(historyCache[cacheKey])
      setHistoryError(false)
      return
    }

    const fetchHistory = async () => {
      setHistoryLoading(true)
      setHistoryError(false)
      try {
        const response = await fetch(`/api/companies/${companyId}/history?period=${period}`)
        if (response.ok) {
          const data = await response.json()
          const history = data.history || []
          setStockHistory(history)
          // Cache the result
          setHistoryCache(prev => ({ ...prev, [cacheKey]: history }))
        } else {
          setStockHistory([])
          setHistoryError(true)
        }
      } catch (err) {
        console.error('Failed to load stock history:', err)
        setStockHistory([])
        setHistoryError(true)
      } finally {
        setHistoryLoading(false)
      }
    }

    fetchHistory()
  }, [companyId, company?.ticker, period, retryCount])

  const handlePeriodChange = (newPeriod) => {
    setPeriod(newPeriod)
    setSearchParams({ period: newPeriod })
  }

  const handleRetry = () => {
    // Clear cache for this period and refetch
    const cacheKey = `${companyId}-${period}`
    setHistoryCache(prev => {
      const newCache = { ...prev }
      delete newCache[cacheKey]
      return newCache
    })
    setRetryCount(c => c + 1)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-600">Loading company data...</span>
      </div>
    )
  }

  if (error || !company) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 mb-4">Failed to load company: {error}</p>
        <Link to="/shortlist" className="text-blue-600 hover:underline">
          &larr; Back to AI Shortlist
        </Link>
      </div>
    )
  }

  return (
    <div>
      {/* Back link */}
      <Link to="/shortlist" className="text-blue-600 hover:underline text-sm mb-4 inline-block">
        &larr; Back to AI Shortlist
      </Link>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main content */}
        <div className="lg:col-span-2">
          {/* Stock header (if publicly traded) */}
          {company.stock_quote && (
            <StockHeader
              quote={company.stock_quote}
              name={company.name}
              ticker={company.ticker}
            />
          )}

          {/* For companies without stock quote, show name header */}
          {!company.stock_quote && (
            <div className="bg-white rounded-lg shadow p-6 mb-6">
              <h1 className="text-2xl font-bold text-gray-900">{company.name}</h1>
              <p className="text-gray-500">
                {company.ticker ? `${company.ticker} · Public Company` : 'Private Company'}
              </p>
            </div>
          )}

          {/* Price chart (lazy-loaded with caching) */}
          {company.ticker && (
            <StockChart
              history={stockHistory}
              period={period}
              onPeriodChange={handlePeriodChange}
              loading={historyLoading}
              error={historyError}
              onRetry={handleRetry}
            />
          )}

          {/* Product reviews */}
          <ProductReviews reviews={company.review_details} />

          {/* Prediction markets */}
          <PredictionMarkets markets={company.prediction_markets} />

          {/* Recent news */}
          <RecentNews news={company.recent_news} />
        </div>

        {/* Sidebar */}
        <div className="lg:col-span-1">
          <CompanyInfo company={company} />
        </div>
      </div>
    </div>
  )
}
