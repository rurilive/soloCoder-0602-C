import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAssets } from '../api/assets'

const STATUS_MAP = {
  in_stock: '在库',
  allocated: '已领用',
  returned: '已归还',
  scrapped: '已报废',
}

const CATEGORY_MAP = {
  computer: '电脑',
  monitor: '显示器',
  printer: '打印机',
  network_device: '网络设备',
  peripheral: '外设',
  other: '其他',
}

export default function AssetList() {
  const navigate = useNavigate()
  const [assets, setAssets] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [category, setCategory] = useState('')
  const pageSize = 20

  const fetchAssets = async () => {
    const params = { page, page_size: pageSize }
    if (keyword) params.keyword = keyword
    if (status) params.status = status
    if (category) params.category = category
    const res = await getAssets(params)
    setAssets(res.data.items)
    setTotal(res.data.total)
  }

  useEffect(() => { fetchAssets() }, [page, status, category])

  const handleSearch = (e) => {
    e.preventDefault()
    setPage(1)
    fetchAssets()
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <div className="toolbar">
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: 12, flex: 1 }}>
          <input
            type="text"
            placeholder="搜索资产名称、编号、品牌、序列号、使用人..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <button type="submit" className="btn btn-primary">搜索</button>
        </form>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
          <option value="">全部状态</option>
          {Object.entries(STATUS_MAP).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1) }}>
          <option value="">全部类别</option>
          {Object.entries(CATEGORY_MAP).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      <div className="card">
        {assets.length === 0 ? (
          <div className="empty-state">
            <p>暂无资产数据</p>
            <button className="btn btn-primary" onClick={() => navigate('/assets/new')}>
              入库新资产
            </button>
          </div>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>资产编号</th>
                  <th>名称</th>
                  <th>类别</th>
                  <th>品牌/型号</th>
                  <th>序列号</th>
                  <th>使用人</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((a) => (
                  <tr key={a.id}>
                    <td>{a.asset_tag}</td>
                    <td>{a.name}</td>
                    <td>{CATEGORY_MAP[a.category] || a.category}</td>
                    <td>{a.brand} {a.model}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: 13 }}>{a.serial_number}</td>
                    <td>{a.assignee || '-'}</td>
                    <td>
                      <span className={`status-badge status-${a.status}`}>
                        {STATUS_MAP[a.status]}
                      </span>
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button className="btn btn-outline btn-sm" onClick={() => navigate(`/assets/${a.id}`)}>
                          详情
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {totalPages > 1 && (
              <div className="pagination">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
                <span>第 {page} / {totalPages} 页 (共 {total} 条)</span>
                <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
