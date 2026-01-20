import { useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
} from '@tanstack/react-table'

/**
 * Format funding amount for display.
 */
function formatFunding(millions) {
  if (!millions || millions === 0) return '-'
  if (millions >= 1000) return `$${(millions / 1000).toFixed(1)}B`
  return `$${millions}M`
}

/**
 * Sortable company table with TanStack Table.
 */
export default function CompanyTable({ companies, categories, stages }) {
  const [sorting, setSorting] = useState([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [stageFilter, setStageFilter] = useState('')

  const columns = useMemo(() => [
    {
      accessorKey: 'name',
      header: '公司',
      cell: ({ row }) => (
        <div>
          <div className="font-medium">{row.original.name}</div>
          {row.original.website && (
            <a
              href={row.original.website}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:underline"
            >
              网站
            </a>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'category_zh',
      header: '类别',
      cell: ({ getValue }) => (
        <span className="bg-blue-50 text-blue-700 text-xs px-2 py-1 rounded">
          {getValue()}
        </span>
      ),
    },
    {
      accessorKey: 'funding_stage_zh',
      header: '阶段',
      cell: ({ getValue }) => (
        <span className="bg-gray-100 text-gray-700 text-xs px-2 py-1 rounded">
          {getValue()}
        </span>
      ),
    },
    {
      accessorKey: 'funding_millions',
      header: '融资 $M',
      cell: ({ getValue }) => formatFunding(getValue()),
      sortDescFirst: true,
    },
    {
      accessorKey: 'revenue_millions',
      header: '营收 $M',
      cell: ({ getValue }) => formatFunding(getValue()),
      sortDescFirst: true,
    },
    {
      accessorKey: 'founded_year',
      header: '成立',
      cell: ({ getValue }) => getValue() || '-',
    },
    {
      accessorKey: 'cb_rank',
      header: 'CB排名',
      cell: ({ getValue }) => {
        const val = getValue()
        return val && val < 999999 ? val.toLocaleString() : '-'
      },
    },
    {
      accessorKey: 'source_count',
      header: '来源数',
      sortDescFirst: true,
    },
  ], [])

  const filteredData = useMemo(() => {
    let data = companies || []
    if (categoryFilter) {
      data = data.filter(c => c.category === categoryFilter)
    }
    if (stageFilter) {
      data = data.filter(c => c.funding_stage === stageFilter)
    }
    return data
  }, [companies, categoryFilter, stageFilter])

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 50 } },
  })

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-4">
        <input
          type="text"
          placeholder="搜索公司..."
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="border rounded px-3 py-2 w-64"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="border rounded px-3 py-2"
        >
          <option value="">全部类别</option>
          {(categories || []).map(c => (
            <option key={c.id} value={c.id}>{c.name_zh}</option>
          ))}
        </select>
        <select
          value={stageFilter}
          onChange={(e) => setStageFilter(e.target.value)}
          className="border rounded px-3 py-2"
        >
          <option value="">全部阶段</option>
          {(stages || []).map(s => (
            <option key={s.id} value={s.id}>{s.name_zh}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto bg-white rounded-lg shadow">
        <table className="w-full">
          <thead className="bg-gray-50 border-b">
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id}>
                {hg.headers.map(header => (
                  <th
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className="px-4 py-3 text-left text-sm font-semibold text-gray-700 cursor-pointer hover:bg-gray-100"
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {{
                        asc: ' ↑',
                        desc: ' ↓',
                      }[header.column.getIsSorted()] ?? ''}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map(row => (
              <tr key={row.id} className="border-b hover:bg-gray-50">
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className="px-4 py-3 text-sm">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-4">
        <div className="text-sm text-gray-600">
          显示 {table.getRowModel().rows.length} / {filteredData.length} 条
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            上一页
          </button>
          <span className="px-3 py-1">
            第 {table.getState().pagination.pageIndex + 1} / {table.getPageCount()} 页
          </span>
          <button
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            className="px-3 py-1 border rounded disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  )
}
