import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

/**
 * Bubble chart for entity visualization across pipelines.
 */
export default function BubbleChart({ data }) {
  if (!data || data.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无数据</div>
  }

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload
      return (
        <div className="bg-white shadow-lg rounded-lg p-3 border">
          <div className="font-semibold">{d.name}</div>
          <div className="text-sm text-gray-600">{d.entity_type}</div>
          <div className="text-sm mt-1">
            <span className="text-gray-500">管道数:</span> {d.x}
          </div>
          <div className="text-sm">
            <span className="text-gray-500">总提及:</span> {d.y}
          </div>
          {d.pipeline_breakdown && (
            <div className="text-xs mt-2 text-gray-500">
              {Object.entries(d.pipeline_breakdown).map(([k, v]) => (
                <div key={k}>{k}: {v}</div>
              ))}
            </div>
          )}
        </div>
      )
    }
    return null
  }

  return (
    <ResponsiveContainer width="100%" height={400}>
      <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
        <XAxis
          type="number"
          dataKey="x"
          name="管道数"
          domain={[0, 4]}
          tickCount={4}
          label={{ value: '出现管道数', position: 'bottom', offset: 0 }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name="提及次数"
          label={{ value: '总提及次数', angle: -90, position: 'left' }}
        />
        <ZAxis
          type="number"
          dataKey="size"
          range={[100, 1000]}
        />
        <Tooltip content={<CustomTooltip />} />
        <Scatter data={data}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={entry.color || '#8884d8'} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
