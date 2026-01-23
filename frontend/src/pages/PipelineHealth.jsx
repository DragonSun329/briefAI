import { useApi } from '../hooks/useApi'

function StatusBadge({ status }) {
  const colors = {
    fresh: 'bg-green-100 text-green-800',
    done: 'bg-green-100 text-green-800',
    ok: 'bg-green-100 text-green-800',
    stale: 'bg-yellow-100 text-yellow-800',
    warning: 'bg-yellow-100 text-yellow-800',
    error: 'bg-red-100 text-red-800',
    never_run: 'bg-gray-100 text-gray-800',
  }
  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${colors[status] || 'bg-gray-100'}`}>
      {status}
    </span>
  )
}

function OverallStatus({ health }) {
  const statusColors = {
    healthy: 'bg-green-500',
    degraded: 'bg-yellow-500',
    critical: 'bg-red-500',
  }

  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className={`${statusColors[health.overall_status]} rounded-lg p-4 text-center text-white`}>
        <div className="text-2xl font-bold uppercase">{health.overall_status}</div>
        <div className="text-sm opacity-90">System Status</div>
      </div>
      <div className="bg-green-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-green-600">{health.healthy_count}</div>
        <div className="text-sm text-gray-600">Healthy</div>
      </div>
      <div className="bg-yellow-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-yellow-600">{health.warning_count}</div>
        <div className="text-sm text-gray-600">Warnings</div>
      </div>
      <div className="bg-red-50 rounded-lg p-4 text-center">
        <div className="text-3xl font-bold text-red-600">{health.error_count}</div>
        <div className="text-sm text-gray-600">Errors</div>
      </div>
    </div>
  )
}

function ScrapersTable({ scrapers }) {
  if (!scrapers?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold mb-3">Scrapers</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Name</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Status</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Last Run</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Records</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Freshness</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {scrapers.map((s) => (
              <tr key={s.name}>
                <td className="px-4 py-2 whitespace-nowrap font-medium">{s.name}</td>
                <td className="px-4 py-2 whitespace-nowrap">
                  <StatusBadge status={s.status} />
                </td>
                <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-500">
                  {s.last_run ? new Date(s.last_run).toLocaleString() : 'Never'}
                </td>
                <td className="px-4 py-2 whitespace-nowrap text-sm">{s.record_count}</td>
                <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-500">
                  {s.freshness_hours}h threshold
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function PipelinesTable({ pipelines }) {
  if (!pipelines?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold mb-3">Pipelines</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Name</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Status</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Last Run</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Outputs</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Location</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {pipelines.map((p) => (
              <tr key={p.name}>
                <td className="px-4 py-2 whitespace-nowrap font-medium">{p.name}</td>
                <td className="px-4 py-2 whitespace-nowrap">
                  <StatusBadge status={p.status} />
                </td>
                <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-500">
                  {p.last_run ? new Date(p.last_run).toLocaleString() : 'Never'}
                </td>
                <td className="px-4 py-2 whitespace-nowrap text-sm">{p.output_count}</td>
                <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-500 font-mono">
                  {p.output_location || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DatabasesTable({ databases }) {
  if (!databases?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold mb-3">Databases</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Name</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Health</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Size</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Records</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Tables</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {databases.map((d) => (
              <tr key={d.name}>
                <td className="px-4 py-2 whitespace-nowrap font-medium font-mono">{d.name}</td>
                <td className="px-4 py-2 whitespace-nowrap">
                  <StatusBadge status={d.health} />
                </td>
                <td className="px-4 py-2 whitespace-nowrap text-sm">{d.size_mb.toFixed(2)} MB</td>
                <td className="px-4 py-2 whitespace-nowrap text-sm">{d.record_count.toLocaleString()}</td>
                <td className="px-4 py-2 whitespace-nowrap text-sm">{d.table_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CachesTable({ caches }) {
  if (!caches?.length) return null

  return (
    <div className="mb-6">
      <h3 className="font-semibold mb-3">Caches</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Name</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Size</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Files</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Oldest</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Newest</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {caches.map((c) => (
              <tr key={c.name}>
                <td className="px-4 py-2 whitespace-nowrap font-medium">{c.name}</td>
                <td className="px-4 py-2 whitespace-nowrap text-sm">{c.size_mb.toFixed(2)} MB</td>
                <td className="px-4 py-2 whitespace-nowrap text-sm">{c.file_count}</td>
                <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-500">
                  {c.oldest_file ? new Date(c.oldest_file).toLocaleDateString() : '-'}
                </td>
                <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-500">
                  {c.newest_file ? new Date(c.newest_file).toLocaleDateString() : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function PipelineHealth() {
  const { data: health, loading, error, refetch } = useApi('/api/health/pipeline-status')

  if (loading) {
    return <div className="text-center py-12">Loading system health...</div>
  }

  if (error) {
    return (
      <div className="text-center py-12 text-red-600">
        Error loading system health: {error.message || 'Unknown error'}
      </div>
    )
  }

  if (!health) {
    return <div className="text-center py-12 text-gray-500">No health data available</div>
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">Pipeline Health Dashboard</h2>
        <button
          onClick={refetch}
          className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 text-sm"
        >
          Refresh
        </button>
      </div>

      <p className="text-gray-600 mb-6">
        Monitor the health of scrapers, pipelines, databases, and caches.
        Last checked: {new Date(health.checked_at).toLocaleString()}
      </p>

      <OverallStatus health={health} />
      <ScrapersTable scrapers={health.scrapers} />
      <PipelinesTable pipelines={health.pipelines} />
      <DatabasesTable databases={health.databases} />
      <CachesTable caches={health.caches} />
    </div>
  )
}