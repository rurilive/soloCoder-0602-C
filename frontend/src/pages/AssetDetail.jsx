import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { getAsset, getAssetLogs, allocateAsset, returnAsset, scrapAsset } from '../api/assets'

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

export default function AssetDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [asset, setAsset] = useState(null)
  const [logs, setLogs] = useState([])
  const [showAllocateModal, setShowAllocateModal] = useState(false)
  const [showScrapModal, setShowScrapModal] = useState(false)
  const [assignee, setAssignee] = useState('')
  const [scrapNote, setScrapNote] = useState('')

  const fetchData = async () => {
    const [assetRes, logsRes] = await Promise.all([getAsset(id), getAssetLogs(id)])
    setAsset(assetRes.data)
    setLogs(logsRes.data)
  }

  useEffect(() => { fetchData() }, [id])

  if (!asset) return <div className="empty-state"><p>加载中...</p></div>

  const qrUrl = `${window.location.origin}/assets/tag/${asset.asset_tag}`

  const handleAllocate = async () => {
    if (!assignee.trim()) return alert('请输入领用人')
    try {
      await allocateAsset(id, { assignee: assignee.trim() })
      setShowAllocateModal(false)
      setAssignee('')
      fetchData()
    } catch (err) {
      alert(err.response?.data?.detail || '领用失败')
    }
  }

  const handleReturn = async () => {
    try {
      await returnAsset(id, { notes: '' })
      fetchData()
    } catch (err) {
      alert(err.response?.data?.detail || '归还失败')
    }
  }

  const handleScrap = async () => {
    try {
      await scrapAsset(id, { notes: scrapNote || '资产报废' })
      setShowScrapModal(false)
      setScrapNote('')
      fetchData()
    } catch (err) {
      alert(err.response?.data?.detail || '报废失败')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2>资产详情</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          {asset.status === 'in_stock' && (
            <button className="btn btn-primary" onClick={() => setShowAllocateModal(true)}>领用</button>
          )}
          {asset.status === 'returned' && (
            <button className="btn btn-primary" onClick={() => setShowAllocateModal(true)}>领用</button>
          )}
          {asset.status === 'allocated' && (
            <button className="btn btn-success" onClick={handleReturn}>归还</button>
          )}
          {asset.status !== 'scrapped' && (
            <button className="btn btn-danger" onClick={() => setShowScrapModal(true)}>报废</button>
          )}
          <button className="btn btn-outline" onClick={() => navigate(`/assets/${id}/edit`)}>编辑</button>
          <button className="btn btn-outline" onClick={() => navigate(-1)}>返回</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16 }}>
        <div>
          <div className="card">
            <h3 style={{ marginBottom: 16 }}>基本信息</h3>
            <div className="detail-grid">
              <div className="detail-item">
                <span className="label">资产编号</span>
                <span className="value" style={{ fontFamily: 'monospace' }}>{asset.asset_tag}</span>
              </div>
              <div className="detail-item">
                <span className="label">名称</span>
                <span className="value">{asset.name}</span>
              </div>
              <div className="detail-item">
                <span className="label">类别</span>
                <span className="value">{CATEGORY_MAP[asset.category]}</span>
              </div>
              <div className="detail-item">
                <span className="label">状态</span>
                <span className={`status-badge status-${asset.status}`}>
                  {STATUS_MAP[asset.status]}
                </span>
              </div>
              <div className="detail-item">
                <span className="label">品牌</span>
                <span className="value">{asset.brand}</span>
              </div>
              <div className="detail-item">
                <span className="label">型号</span>
                <span className="value">{asset.model}</span>
              </div>
              <div className="detail-item">
                <span className="label">序列号</span>
                <span className="value" style={{ fontFamily: 'monospace' }}>{asset.serial_number}</span>
              </div>
              <div className="detail-item">
                <span className="label">使用人</span>
                <span className="value">{asset.assignee || '-'}</span>
              </div>
              <div className="detail-item">
                <span className="label">存放位置</span>
                <span className="value">{asset.location || '-'}</span>
              </div>
              <div className="detail-item">
                <span className="label">购入日期</span>
                <span className="value">{asset.purchase_date || '-'}</span>
              </div>
              <div className="detail-item">
                <span className="label">购入价格</span>
                <span className="value">{asset.purchase_price != null ? `¥${asset.purchase_price}` : '-'}</span>
              </div>
              <div className="detail-item">
                <span className="label">备注</span>
                <span className="value">{asset.notes || '-'}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginBottom: 16 }}>操作记录</h3>
            {logs.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>暂无操作记录</p>
            ) : (
              <ul className="log-timeline">
                {logs.map((log) => (
                  <li key={log.id}>
                    <div className="log-action">{log.action}</div>
                    <div className="log-meta">
                      操作人: {log.operator} | {log.detail || ''} | {new Date(log.created_at).toLocaleString('zh-CN')}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="card" style={{ height: 'fit-content' }}>
          <h3 style={{ marginBottom: 16, textAlign: 'center' }}>资产二维码</h3>
          <div className="qr-container">
            <QRCodeSVG value={qrUrl} size={200} />
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', textAlign: 'center' }}>
              扫描二维码查看资产信息
            </p>
            <p style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
              {asset.asset_tag}
            </p>
          </div>
        </div>
      </div>

      {showAllocateModal && (
        <div className="modal-overlay" onClick={() => setShowAllocateModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>资产领用</h3>
            <div className="form-group" style={{ marginBottom: 16 }}>
              <label>领用人 *</label>
              <input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="请输入领用人姓名" />
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button className="btn btn-outline" onClick={() => setShowAllocateModal(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleAllocate}>确认领用</button>
            </div>
          </div>
        </div>
      )}

      {showScrapModal && (
        <div className="modal-overlay" onClick={() => setShowScrapModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>资产报废</h3>
            <p style={{ color: 'var(--danger)', marginBottom: 16, fontSize: 14 }}>
              ⚠ 报废操作不可撤销，请确认
            </p>
            <div className="form-group" style={{ marginBottom: 16 }}>
              <label>报废原因</label>
              <textarea value={scrapNote} onChange={(e) => setScrapNote(e.target.value)} placeholder="请输入报废原因" />
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button className="btn btn-outline" onClick={() => setShowScrapModal(false)}>取消</button>
              <button className="btn btn-danger" onClick={handleScrap}>确认报废</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
