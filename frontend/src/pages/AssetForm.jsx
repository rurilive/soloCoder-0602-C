import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getAsset, createAsset, updateAsset } from '../api/assets'

const CATEGORIES = [
  { value: 'computer', label: '电脑' },
  { value: 'monitor', label: '显示器' },
  { value: 'printer', label: '打印机' },
  { value: 'network_device', label: '网络设备' },
  { value: 'peripheral', label: '外设' },
  { value: 'other', label: '其他' },
]

const emptyForm = {
  name: '',
  category: 'computer',
  brand: '',
  model: '',
  serial_number: '',
  assignee: '',
  location: '',
  notes: '',
  purchase_date: '',
  purchase_price: '',
}

export default function AssetForm() {
  const navigate = useNavigate()
  const { id } = useParams()
  const isEdit = Boolean(id)
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isEdit) {
      getAsset(id).then((res) => {
        const a = res.data
        setForm({
          name: a.name || '',
          category: a.category || 'computer',
          brand: a.brand || '',
          model: a.model || '',
          serial_number: a.serial_number || '',
          assignee: a.assignee || '',
          location: a.location || '',
          notes: a.notes || '',
          purchase_date: a.purchase_date || '',
          purchase_price: a.purchase_price ?? '',
        })
      })
    }
  }, [id])

  const handleChange = (e) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const payload = { ...form }
      if (!payload.assignee) delete payload.assignee
      if (!payload.location) delete payload.location
      if (!payload.notes) delete payload.notes
      if (!payload.purchase_date) delete payload.purchase_date
      if (payload.purchase_price === '' || payload.purchase_price == null) {
        delete payload.purchase_price
      } else {
        payload.purchase_price = parseFloat(payload.purchase_price)
      }
      if (isEdit) {
        await updateAsset(id, payload)
      } else {
        await createAsset(payload)
      }
      navigate('/')
    } catch (err) {
      const msg = err.response?.data?.detail || '操作失败'
      alert(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 style={{ marginBottom: 20 }}>{isEdit ? '编辑资产' : '资产入库'}</h2>
      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <div className="form-group">
              <label>资产名称 *</label>
              <input name="name" value={form.name} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label>类别 *</label>
              <select name="category" value={form.category} onChange={handleChange}>
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>品牌 *</label>
              <input name="brand" value={form.brand} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label>型号 *</label>
              <input name="model" value={form.model} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label>序列号 *</label>
              <input name="serial_number" value={form.serial_number} onChange={handleChange} required />
            </div>
            <div className="form-group">
              <label>使用人</label>
              <input name="assignee" value={form.assignee} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label>存放位置</label>
              <input name="location" value={form.location} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label>购入日期</label>
              <input type="date" name="purchase_date" value={form.purchase_date} onChange={handleChange} />
            </div>
            <div className="form-group">
              <label>购入价格</label>
              <input type="number" step="0.01" name="purchase_price" value={form.purchase_price} onChange={handleChange} />
            </div>
            <div className="form-group full-width">
              <label>备注</label>
              <textarea name="notes" value={form.notes} onChange={handleChange} />
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={() => navigate(-1)}>取消</button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? '提交中...' : (isEdit ? '保存修改' : '确认入库')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
