import { useApi } from '../hooks/useApi'
import CompanyTable from '../components/CompanyTable'

export default function Shortlist() {
  const { data: companiesData, loading: loadingCompanies } = useApi('/api/companies')
  const { data: filtersData, loading: loadingFilters } = useApi('/api/companies/filters')

  if (loadingCompanies || loadingFilters) {
    return <div className="text-center py-8">加载中...</div>
  }

  if (!companiesData || !filtersData) {
    return <div className="text-red-500 py-8">无法加载数据</div>
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-xl font-semibold">AI速查</h2>
        <p className="text-gray-600 text-sm">
          来自顶级VC投资组合的AI公司 ({companiesData.total} 家)
        </p>
      </div>

      <CompanyTable
        companies={companiesData.companies}
        categories={filtersData.categories}
        stages={filtersData.stages}
      />
    </div>
  )
}