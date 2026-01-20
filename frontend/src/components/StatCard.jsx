/**
 * Stat card for displaying metric values.
 */
export default function StatCard({ icon, label, value, color = 'blue' }) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    orange: 'bg-orange-50 text-orange-600',
    purple: 'bg-purple-50 text-purple-600',
  }

  return (
    <div className={`rounded-lg p-4 ${colorClasses[color]}`}>
      <div className="flex items-center gap-2 text-sm font-medium mb-1">
        <span>{icon}</span>
        <span>{label}</span>
      </div>
      <div className="text-3xl font-bold">{value}</div>
    </div>
  )
}
