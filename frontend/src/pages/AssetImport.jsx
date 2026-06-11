import { useState, useRef } from 'react'
import { importAssets } from '../api/assets'

const STATUS_IDLE = 'idle'
const STATUS_UPLOADING = 'uploading'
const STATUS_DONE = 'done'

export default function AssetImport() {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState(STATUS_IDLE)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const inputRef = useRef(null)

  const handleFileChange = (e) => {
    const selected = e.target.files[0]
    if (selected) {
      if (!selected.name.endsWith('.xlsx') && !selected.name.endsWith('.xls')) {
        setErrorMsg('请选择xlsx格式的文件')
        setFile(null)
        return
      }
      setErrorMsg('')
      setFile(selected)
      setResult(null)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const dropped = e.dataTransfer.files[0]
    if (dropped) {
      if (!dropped.name.endsWith('.xlsx') && !dropped.name.endsWith('.xls')) {
        setErrorMsg('请选择xlsx格式的文件')
        return
      }
      setErrorMsg('')
      setFile(dropped)
      setResult(null)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
  }

  const handleUpload = async () => {
    if (!file) return
    setStatus(STATUS_UPLOADING)
    setProgress(0)
    setResult(null)
    setErrorMsg('')

    try {
      const res = await importAssets(file, (e) => {
        if (e.total) {
          setProgress(Math.round((e.loaded / e.total) * 100))
        }
      })
      setResult(res.data)
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        '导入失败，请检查文件格式或网络连接'
      setErrorMsg(msg)
    } finally {
      setStatus(STATUS_DONE)
    }
  }

  const handleReset = () => {
    setFile(null)
    setStatus(STATUS_IDLE)
    setProgress(0)
    setResult(null)
    setErrorMsg('')
    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  return (
    <div className="import-page">
      <div className="card">
        <h2 style={{ marginBottom: 20 }}>资产批量导入</h2>

        <div
          className={`import-drop-zone ${file ? 'has-file' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <div className="import-drop-zone-content">
            {file ? (
              <>
                <div className="import-file-icon">📄</div>
                <div className="import-file-name">{file.name}</div>
                <div className="import-file-size">
                  {(file.size / 1024).toFixed(1)} KB
                </div>
              </>
            ) : (
              <>
                <div className="import-file-icon">📁</div>
                <div>拖拽xlsx文件到此处，或点击选择文件</div>
              </>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xls"
            onChange={handleFileChange}
            className="import-file-input"
          />
        </div>

        {errorMsg && <div className="import-error-msg">{errorMsg}</div>}

        {status === STATUS_UPLOADING && (
          <div className="import-progress">
            <div className="import-progress-bar">
              <div
                className="import-progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="import-progress-text">上传中... {progress}%</div>
          </div>
        )}

        <div className="import-actions">
          <button
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={!file || status === STATUS_UPLOADING}
          >
            {status === STATUS_UPLOADING ? '上传中...' : '开始导入'}
          </button>
          <button
            className="btn btn-outline"
            onClick={handleReset}
            disabled={status === STATUS_UPLOADING}
          >
            重置
          </button>
        </div>
      </div>

      {result && (
        <div className="card">
          <h3>导入结果</h3>
          <div className="import-stats">
            <div className={`import-stat-card ${result.success ? 'stat-success' : 'stat-error'}`}>
              <div className="stat-value">{result.total_rows}</div>
              <div className="stat-label">总行数</div>
            </div>
            <div className={`import-stat-card ${result.success ? 'stat-success' : 'stat-error'}`}>
              <div className="stat-value">{result.success_count}</div>
              <div className="stat-label">成功导入</div>
            </div>
            <div className={`import-stat-card ${result.errors.length > 0 ? 'stat-error' : 'stat-success'}`}>
              <div className="stat-value">{result.errors.length}</div>
              <div className="stat-label">错误数</div>
            </div>
          </div>

          {result.success && (
            <div className="import-success-msg">
              ✅ 全部校验通过，成功导入 {result.success_count} 条资产
            </div>
          )}

          {result.errors.length > 0 && (
            <div className="import-errors-section">
              <h4>校验错误明细</h4>
              <table className="import-errors-table">
                <thead>
                  <tr>
                    <th>行号</th>
                    <th>错误原因</th>
                  </tr>
                </thead>
                <tbody>
                  {result.errors.map((err, idx) => (
                    <tr key={idx}>
                      <td>{err.row}</td>
                      <td>{err.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3>导入说明</h3>
        <div className="import-help">
          <p><strong>1. 文件格式：</strong>仅支持 .xlsx 格式，第一行为表头。</p>
          <p><strong>2. 表头说明：</strong></p>
          <table className="import-help-table">
            <thead>
              <tr>
                <th>表头名称</th>
                <th>对应字段</th>
                <th>是否必填</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>名称</td><td>资产名称</td><td>是</td></tr>
              <tr><td>类别</td><td>资产类别</td><td>是</td></tr>
              <tr><td>品牌</td><td>品牌</td><td>是</td></tr>
              <tr><td>型号</td><td>型号</td><td>是</td></tr>
              <tr><td>序列号</td><td>序列号</td><td>是</td></tr>
              <tr><td>使用人</td><td>使用人</td><td>否</td></tr>
              <tr><td>位置</td><td>位置</td><td>否</td></tr>
              <tr><td>备注</td><td>备注</td><td>否</td></tr>
              <tr><td>购买日期</td><td>购买日期</td><td>否</td></tr>
              <tr><td>购买价格</td><td>购买价格</td><td>否</td></tr>
            </tbody>
          </table>
          <p><strong>3. 类别可选值：</strong>电脑、显示器、打印机、网络设备、外设、其他</p>
          <p><strong>4. 校验规则：</strong>序列号不可重复（文件内及数据库中），必填字段不可为空，类别需为有效值。</p>
        </div>
      </div>
    </div>
  )
}
