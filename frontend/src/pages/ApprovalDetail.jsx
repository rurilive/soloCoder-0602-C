import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getApproval, approveApproval, rejectApproval, addSigner, transferApproval, getAvailableApprovalUsers } from '../api/assets'

const STATUS_MAP = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
  withdrawn: '已撤回',
  escalated: '已升级',
  transferred: '已转审',
}

const TYPE_MAP = {
  allocate: '领用审批',
  scrap: '报废审批',
}

const EVENT_ICON_MAP = {
  submit: '📝',
  approve: '✅',
  reject: '❌',
  add_signer: '➕',
  transfer: '🔄',
  remind: '⏰',
  complete: '🎉',
  withdraw: '↩️',
  escalate: '⬆️',
}

const BRANCH_COLORS = ['#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#f472b6']

function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

function formatCountdown(ms) {
  if (ms <= 0) return '已超时'
  const seconds = Math.floor(ms / 1000)
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (days > 0) return `${days}天${hours}时${minutes}分`
  if (hours > 0) return `${hours}时${minutes}分${secs}秒`
  if (minutes > 0) return `${minutes}分${secs}秒`
  return `${secs}秒`
}

function useCountdown(timeoutAt) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!timeoutAt) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [timeoutAt])
  if (!timeoutAt) return { remaining: null, isTimeout: false, text: null }
  const remaining = new Date(timeoutAt).getTime() - now
  return {
    remaining,
    isTimeout: remaining <= 0,
    text: formatCountdown(remaining),
  }
}

function isRecordTimeout(record, approval) {
  if (!record?.timeout_at) return false
  if (record.status !== 'pending') return false
  if (record.transfer_status === 'transferred') return false
  return new Date(record.timeout_at).getTime() < Date.now()
}

function getLevelState(levelRecords, approval) {
  const hasRejected = levelRecords.some((r) => r.status === 'rejected')
  if (hasRejected) return 'rejected'
  const allApproved = levelRecords.length > 0 && levelRecords.every((r) => {
    if (r.transfer_status === 'transferred') return true
    return r.status === 'approved'
  })
  if (allApproved) return 'approved'
  const isCurrentLevel = levelRecords[0]?.level === approval.current_level
  if (approval.status === 'pending' && isCurrentLevel) return 'current'
  return 'pending'
}

function getApproverState(record) {
  if (record.transfer_status === 'transferred') return 'transferred'
  if (record.status === 'approved') return 'approved'
  if (record.status === 'rejected') return 'rejected'
  if (record.status === 'escalated') return 'current'
  if (record.status === 'withdrawn') return 'rejected'
  return 'pending'
}

function getEscalationBadgeText(rec) {
  const triggerPrefix = rec.escalation_trigger === 'reminder' ? '催办' : '超时'
  switch (rec.escalation_strategy) {
    case 'skip_node':
      return `${triggerPrefix}跳过`
    case 'auto_reject':
      return `${triggerPrefix}自动驳回`
    case 'escalate_to_level':
    default:
      return `${triggerPrefix}升级`
  }
}

function NodeIcon({ state }) {
  if (state === 'approved') {
    return (
      <span className="chain-node-icon chain-node-approved" style={{ color: 'var(--success)' }}>
        ✓
      </span>
    )
  }
  if (state === 'rejected') {
    return (
      <span className="chain-node-icon chain-node-rejected" style={{ color: 'var(--danger)' }}>
        ✗
      </span>
    )
  }
  if (state === 'current') {
    return (
      <span className="chain-node-icon chain-node-current" style={{ color: 'var(--primary)' }}>
        ●
      </span>
    )
  }
  if (state === 'transferred') {
    return (
      <span className="chain-node-icon chain-node-pending" style={{ color: 'var(--warning)' }}>
        🔄
      </span>
    )
  }
  return (
    <span className="chain-node-icon chain-node-pending" style={{ color: 'var(--border)' }}>
      ○
    </span>
  )
}

function getApproverBadgeColor(state) {
  if (state === 'approved') return 'var(--success)'
  if (state === 'rejected') return 'var(--danger)'
  if (state === 'current') return 'var(--primary)'
  if (state === 'transferred') return 'var(--warning)'
  return 'var(--border)'
}

function ApproverRow({ rec, currentUser, onTransfer }) {
  const approverState = getApproverState(rec)
  const countdown = useCountdown(rec.timeout_at)
  const isTimeout = isRecordTimeout(rec)
  const isCurrentUserApprover =
    (rec.approver_name === currentUser?.real_name ||
     rec.approver_name === currentUser?.username) &&
    rec.status === 'pending' &&
    rec.transfer_status !== 'transferred'

  const getCountdownColor = () => {
    if (!countdown.text) return null
    if (countdown.isTimeout) return 'var(--danger)'
    if (countdown.remaining != null && countdown.remaining < 5 * 60 * 1000) return 'var(--warning)'
    return 'var(--text-secondary)'
  }

  const rowBg = isTimeout ? 'rgba(239, 68, 68, 0.06)' :
    isCurrentUserApprover ? 'rgba(13, 110, 253, 0.05)' : 'transparent'
  const rowBorder = isTimeout ? '1px solid var(--danger)' :
    isCurrentUserApprover ? '1px solid var(--primary)' : 'none'

  return (
    <div
      key={rec.id}
      className={`chain-approver-row chain-approver-${approverState}`}
      style={{
        border: rowBorder,
        borderRadius: 6,
        padding: isCurrentUserApprover || isTimeout ? 6 : 0,
        background: rowBg,
        transition: 'all 0.2s ease',
      }}
    >
      <span
        className="chain-approver-icon"
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          marginRight: 8,
          background: getApproverBadgeColor(approverState),
          display: 'inline-block',
        }}
      />
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 500 }}>{rec.approver_name}</span>
          <span className={`status-badge status-${rec.transfer_status === 'transferred' ? 'transferred' : rec.status}`} style={{ fontSize: 11 }}>
            {rec.transfer_status === 'transferred' ? '已转审' : STATUS_MAP[rec.status]}
          </span>
          {rec.is_escalated && (
            <span
              className="status-badge"
              style={{
                fontSize: 11,
                background: 'rgba(168, 85, 247, 0.12)',
                color: 'var(--warning)',
              }}
            >
              ⬆️ {getEscalationBadgeText(rec)}
            </span>
          )}
          {rec.is_added_signer && (
            <span
              className="status-badge"
              style={{
                fontSize: 11,
                background: 'rgba(13, 110, 253, 0.12)',
                color: 'var(--primary)',
              }}
            >
              加签人
            </span>
          )}
          {rec.proxy_source && (
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              ({rec.proxy_source} 代理)
            </span>
          )}
          {rec.added_signer_by && (
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              (由 {rec.added_signer_by} 追加)
            </span>
          )}
          {countdown.text && rec.status === 'pending' && rec.transfer_status !== 'transferred' && (
            <span
              className="status-badge"
              style={{
                fontSize: 11,
                background: countdown.isTimeout ? 'rgba(239, 68, 68, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                color: getCountdownColor(),
                fontWeight: 600,
                marginLeft: 'auto',
              }}
            >
              {countdown.isTimeout ? '⚠️ ' : '⏰ '}{countdown.text}
            </span>
          )}
          {isCurrentUserApprover && (
            <>
              <span
                className="status-badge"
                style={{
                  fontSize: 11,
                  background: 'rgba(13, 110, 253, 0.15)',
                  color: 'var(--primary)',
                }}
              >
                您的待办
              </span>
              <button
                className="btn btn-sm btn-outline"
                style={{
                  marginLeft: 4,
                  fontSize: 12,
                  padding: '2px 10px',
                  borderColor: 'var(--warning)',
                  color: 'var(--warning)',
                }}
                onClick={() => onTransfer && onTransfer(rec)}
              >
                🔄 转审
              </button>
            </>
          )}
        </div>
        {(rec.opinion || rec.acted_at || rec.transferred_to || rec.added_signer_reason || rec.transfer_reason) && (
          <div style={{ marginTop: 4 }}>
            {rec.opinion && (
              <div className="chain-node-opinion" style={{ marginTop: 0 }}>
                意见: {rec.opinion}
              </div>
            )}
            {rec.transferred_to && (
              <div style={{ fontSize: 12, color: 'var(--warning)', marginTop: rec.opinion ? 2 : 0 }}>
                转审给: {rec.transferred_to}
                {rec.transfer_reason && ` (原因: ${rec.transfer_reason})`}
              </div>
            )}
            {rec.transferred_from && rec.status === 'pending' && !rec.transfer_status && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                转审来自: {rec.transferred_from}
                {rec.transfer_reason && ` (原因: ${rec.transfer_reason})`}
              </div>
            )}
            {rec.added_signer_reason && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                加签原因: {rec.added_signer_reason}
              </div>
            )}
            {rec.acted_at && (
              <div className="chain-node-meta" style={{ fontSize: 12, marginTop: 2 }}>
                处理时间: {formatTime(rec.acted_at)}
              </div>
            )}
          </div>
        )}
        {approverState === 'current' && !rec.acted_at && (
          <div className="chain-node-meta" style={{ color: 'var(--primary)', fontSize: 12, fontWeight: 500 }}>
            等待审批中...
          </div>
        )}
        {rec.timeout_at && !rec.acted_at && (
          <div className="chain-node-meta" style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
            超时时间: {formatTime(rec.timeout_at)}
          </div>
        )}
      </div>
    </div>
  )
}

function LevelNodeBlock({ level, records, approval, currentUser, onAddSigner, onTransfer, levelIdx, totalLevels, showConnector }) {
  const state = getLevelState(records, approval)
  const isMulti = records.length > 1
  const role = records[0]?.approver_role
  const partialApproved = approval.status === 'pending' && records.filter((r) => r.transfer_status !== 'transferred').some((r) => r.status === 'approved')
    && records.filter((r) => r.transfer_status !== 'transferred').some((r) => r.status === 'pending')
  const canAddSigner = partialApproved && (
    approval.applicant === currentUser?.real_name ||
    approval.applicant === currentUser?.username ||
    currentUser?.roles?.includes('super_admin') ||
    currentUser?.roles?.includes('asset_admin')
  )
  const inBranch = !!records[0]?.branch_id
  const branchIdx = records[0]?.branch_index ?? 0
  const branchColor = inBranch ? BRANCH_COLORS[branchIdx % BRANCH_COLORS.length] : null

  const hasTimeout = records.some((r) => isRecordTimeout(r))
  const hasEscalated = records.some((r) => r.is_escalated)

  const nodeBorderStyle = hasTimeout
    ? {
        border: '2px solid var(--danger)',
        boxShadow: '0 0 0 3px rgba(239, 68, 68, 0.08)',
      }
    : undefined

  return (
    <div
      className={`approval-chain-node chain-node-${state}`}
      style={{
        ...(inBranch && branchColor ? {
          borderLeft: `4px solid ${branchColor}`,
          borderTopLeftRadius: 0,
          borderBottomLeftRadius: 0,
        } : undefined),
        ...nodeBorderStyle,
        transition: 'all 0.2s ease',
      }}
    >
      {showConnector && <div className="chain-connector" />}
      <NodeIcon state={state} />
      <div className="chain-node-content">
        <div className="chain-node-title" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
          <span>第 {level} 级 - {role}</span>
          {inBranch && (
            <span
              className="status-badge"
              style={{
                fontSize: 11,
                background: branchColor,
                color: '#fff',
              }}
            >
              分支{branchIdx + 1}
            </span>
          )}
          {isMulti && (
            <span className="status-badge status-pending" style={{ fontSize: 11 }}>
              {records.length} 人并行
            </span>
          )}
          {partialApproved && (
            <span
              className="status-badge"
              style={{
                fontSize: 11,
                background: 'rgba(255, 193, 7, 0.15)',
                color: 'var(--warning)',
              }}
            >
              部分通过
            </span>
          )}
          {hasTimeout && (
            <span
              className="status-badge"
              style={{
                fontSize: 11,
                background: 'rgba(239, 68, 68, 0.12)',
                color: 'var(--danger)',
                fontWeight: 600,
              }}
            >
              ⚠️ 已超时
            </span>
          )}
          {hasEscalated && !hasTimeout && (
            <span
              className="status-badge"
              style={{
                fontSize: 11,
                background: 'rgba(168, 85, 247, 0.12)',
                color: 'var(--warning)',
                fontWeight: 600,
              }}
            >
              ⬆️ 已升级
            </span>
          )}
          {canAddSigner && (
            <button
              className="btn btn-sm btn-outline"
              style={{
                marginLeft: 8,
                fontSize: 12,
                padding: '2px 10px',
                borderColor: 'var(--primary)',
                color: 'var(--primary)',
              }}
              onClick={() => onAddSigner && onAddSigner(level, records)}
            >
              ➕ 加签
            </button>
          )}
        </div>
        <div className="chain-level-approvers">
          {records.map((rec) => (
            <ApproverRow
              key={rec.id}
              rec={rec}
              currentUser={currentUser}
              onTransfer={onTransfer}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function GatewayBlock({ label, variant, showConnector, subLabel }) {
  const color = variant === 'start' ? '#6366f1' : '#10b981'
  const bg = variant === 'start' ? '#eef2ff' : '#ecfdf5'
  return (
    <div style={{
      position: 'relative',
      padding: '10px 14px',
      margin: '4px 0',
      border: `2px dashed ${color}`,
      borderRadius: 8,
      background: bg,
    }}>
      {showConnector && (
        <div
          style={{
            position: 'absolute',
            left: 19,
            top: 0,
            transform: 'translateY(-100%)',
            width: 2,
            height: 16,
            background: 'var(--border)',
          }}
        />
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            background: color,
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: 14,
          }}
        >
          {variant === 'start' ? '⇶' : '⏚'}
        </span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, color }}>{label}</div>
          {subLabel && <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{subLabel}</div>}
        </div>
      </div>
    </div>
  )
}

function SubProcessBlock({
  level,
  nodeRecord,
  subRecords,
  approval,
  currentUser,
  onAddSigner,
  onTransfer,
  showConnector,
  nestingLevel,
}) {
  const [collapsed, setCollapsed] = useState(false)
  const state = getLevelState([nodeRecord], approval)

  const getSubProcessState = () => {
    if (!subRecords || subRecords.length === 0) return 'pending'
    const hasRejected = subRecords.some(r => r.status === 'rejected')
    if (hasRejected) return 'rejected'
    const allApproved = subRecords.every(r =>
      r.status === 'approved' || r.status === 'rejected' || r.status === 'withdrawn'
    )
    if (allApproved) return 'approved'
    return 'current'
  }

  const subState = getSubProcessState()
  const subColor = subState === 'approved' ? 'var(--success)' :
    subState === 'rejected' ? 'var(--danger)' :
      subState === 'current' ? 'var(--primary)' : 'var(--border)'

  const subBg = subState === 'approved' ? '#f0fdf4' :
    subState === 'rejected' ? '#fef2f2' :
      subState === 'current' ? '#eff6ff' : 'var(--bg-secondary)'

  const indentWidth = nestingLevel > 0 ? nestingLevel * 24 : 0

  return (
    <div style={{ position: 'relative', marginLeft: indentWidth }}>
      {showConnector && <div className="chain-connector" />}
      <div
        style={{
          position: 'relative',
          padding: '10px 14px',
          margin: '4px 0',
          border: `2px solid ${subColor}`,
          borderRadius: 8,
          background: subBg,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <NodeIcon state={state} />
          <span
            style={{
              width: 28,
              height: 28,
              borderRadius: '50%',
              background: '#f59e0b',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: 14,
            }}
          >
            ⤵
          </span>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 600 }}>
                第 {level} 级 - {nodeRecord.approver_name}
              </span>
              <span
                className={`status-badge status-${nodeRecord.status}`}
                style={{ fontSize: 11 }}
              >
                {STATUS_MAP[nodeRecord.status]}
              </span>
              {nestingLevel > 0 && (
                <span
                  className="status-badge"
                  style={{
                    fontSize: 11,
                    background: 'rgba(245, 158, 11, 0.15)',
                    color: '#92400e',
                  }}
                >
                  嵌套 {nestingLevel} 层
                </span>
              )}
            </div>
            {nodeRecord.opinion && (
              <div className="chain-node-opinion" style={{ marginTop: 4 }}>
                意见: {nodeRecord.opinion}
              </div>
            )}
            {nodeRecord.acted_at && (
              <div className="chain-node-meta" style={{ fontSize: 12, marginTop: 2 }}>
                处理时间: {formatTime(nodeRecord.acted_at)}
              </div>
            )}
          </div>
          <button
            type="button"
            className="btn btn-sm btn-outline"
            onClick={() => setCollapsed(!collapsed)}
            style={{ fontSize: 12 }}
          >
            {collapsed ? '展开 ▼' : '收起 ▲'}
          </button>
        </div>
      </div>

      {!collapsed && subRecords && subRecords.length > 0 && (
        <div style={{ marginTop: 4 }}>
          {(() => {
            const subLevelGroups = {}
            for (const rec of subRecords) {
              if (!subLevelGroups[rec.level]) subLevelGroups[rec.level] = []
              subLevelGroups[rec.level].push(rec)
            }
            const subLevels = Object.keys(subLevelGroups)
              .map(Number)
              .sort((a, b) => a - b)

            return subLevels.map((subLv, subIdx) => (
              <SubProcessLevelNode
                key={subLv}
                level={subLv}
                records={subLevelGroups[subLv]}
                approval={approval}
                currentUser={currentUser}
                onAddSigner={onAddSigner}
                onTransfer={onTransfer}
                levelIdx={subIdx}
                totalLevels={subLevels.length}
                showConnector={subIdx > 0}
                nestingLevel={nestingLevel + 1}
              />
            ))
          })()}
        </div>
      )}
    </div>
  )
}

function SubProcessLevelNode({
  level,
  records,
  approval,
  currentUser,
  onAddSigner,
  onTransfer,
  levelIdx,
  totalLevels,
  showConnector,
  nestingLevel,
}) {
  const firstRec = records[0]
  const hasSubProcess = firstRec.node_type === 'sub_process' &&
    firstRec.sub_process_records &&
    firstRec.sub_process_records.length > 0

  if (hasSubProcess) {
    return (
      <SubProcessBlock
        level={level}
        nodeRecord={firstRec}
        subRecords={firstRec.sub_process_records}
        approval={approval}
        currentUser={currentUser}
        onAddSigner={onAddSigner}
        onTransfer={onTransfer}
        showConnector={showConnector}
        nestingLevel={nestingLevel}
      />
    )
  }

  const indentWidth = nestingLevel > 0 ? nestingLevel * 24 : 0

  return (
    <div style={{ marginLeft: indentWidth }}>
      <LevelNodeBlock
        level={level}
        records={records}
        approval={approval}
        currentUser={currentUser}
        onAddSigner={onAddSigner}
        onTransfer={onTransfer}
        levelIdx={levelIdx}
        totalLevels={totalLevels}
        showConnector={showConnector}
      />
    </div>
  )
}

function buildTimelineSequence(nodes) {
  const levelGroups = {}
  for (const n of nodes) {
    if (!levelGroups[n.level]) levelGroups[n.level] = []
    levelGroups[n.level].push(n)
  }
  const levels = Object.keys(levelGroups).map(Number).sort((a, b) => a - b)

  const sequence = []
  let activeGroupId = null
  let activeBranchesMap = null

  for (const level of levels) {
    const recs = levelGroups[level]
    const first = recs[0]
    const groupId = first.parallel_group_id
    const branchId = first.branch_id
    const nodeType = first.node_type || 'approval'

    if (nodeType === 'sub_process' && first.sub_process_records && first.sub_process_records.length > 0) {
      if (activeGroupId && branchId) {
        if (!activeBranchesMap[branchId]) activeBranchesMap[branchId] = []
        activeBranchesMap[branchId].push(...recs)
        continue
      }
      sequence.push({ type: 'sub_process', level, records: recs })
      continue
    }

    if (nodeType === 'parallel_start') {
      sequence.push({ type: 'gateway', variant: 'start', label: '并行开始', subLabel: '多个分支同时开始审批' })
      activeGroupId = groupId
      activeBranchesMap = {}
      continue
    }

    if (nodeType === 'parallel_end') {
      if (activeBranchesMap) {
        const branchSeq = Object.entries(activeBranchesMap)
          .sort((a, b) => {
            const ai = a[1][0]?.branch_index ?? 0
            const bi = b[1][0]?.branch_index ?? 0
            return ai - bi
          })
          .map(([bid, recs]) => ({ branch_id: bid, records: recs }))
        sequence.push({ type: 'parallel_group', branches: branchSeq })
      }
      sequence.push({ type: 'gateway', variant: 'end', label: '并行结束', subLabel: '所有分支完成后合并继续' })
      activeGroupId = null
      activeBranchesMap = null
      continue
    }

    if (activeGroupId && branchId) {
      if (!activeBranchesMap[branchId]) activeBranchesMap[branchId] = []
      activeBranchesMap[branchId].push(...recs)
      continue
    }

    sequence.push({ type: 'level', level, records: recs })
  }

  return sequence
}

function ChainTimeline({ approval, onAddSigner, onTransfer, currentUser }) {
  const nodes = approval.node_records || []
  const hasChain = nodes.length > 0

  if (!hasChain) {
    return (
      <div className="card">
        <h3 style={{ marginBottom: 16 }}>审批状态</h3>
        <div className="approval-chain-timeline">
          <div className={`approval-chain-node chain-node-${approval.status}`}>
            <NodeIcon state={approval.status === 'pending' ? 'current' : approval.status} />
            <div className="chain-node-content">
              <div className="chain-node-title">
                审批人: {approval.approver || '-'}
              </div>
              <div className="chain-node-meta">
                <span className={`status-badge status-${approval.status}`}>
                  {STATUS_MAP[approval.status]}
                </span>
              </div>
              {approval.approval_opinion && (
                <div className="chain-node-opinion">意见: {approval.approval_opinion}</div>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  const hasParallel = nodes.some((n) => n.parallel_group_id)
  const sequence = hasParallel ? buildTimelineSequence(nodes) : null

  const levelGroups = {}
  for (const node of nodes) {
    if (!levelGroups[node.level]) levelGroups[node.level] = []
    levelGroups[node.level].push(node)
  }
  const levels = Object.keys(levelGroups)
    .map(Number)
    .sort((a, b) => a - b)

  return (
    <div className="card">
      <h3 style={{ marginBottom: 16 }}>
        审批流程
        <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-secondary)', marginLeft: 8 }}>
          共 {approval.total_levels} 级审批
          {hasParallel && <span style={{ marginLeft: 8 }}>（含并行分支）</span>}
        </span>
      </h3>

      {sequence ? (
        <div className="approval-chain-timeline">
          {sequence.map((item, idx) => {
            if (item.type === 'gateway') {
              return (
                <GatewayBlock
                  key={idx}
                  label={item.label}
                  variant={item.variant}
                  subLabel={item.subLabel}
                  showConnector={idx > 0}
                />
              )
            }
            if (item.type === 'sub_process') {
              const nodeRecord = item.records[0]
              return (
                <SubProcessBlock
                  key={idx}
                  level={item.level}
                  nodeRecord={nodeRecord}
                  subRecords={nodeRecord.sub_process_records || []}
                  approval={approval}
                  currentUser={currentUser}
                  onAddSigner={onAddSigner}
                  onTransfer={onTransfer}
                  showConnector={idx > 0}
                  nestingLevel={0}
                />
              )
            }
            if (item.type === 'parallel_group') {
              return (
                <div key={idx} style={{ position: 'relative', margin: '8px 0' }}>
                  {idx > 0 && (
                    <div
                      style={{
                        position: 'absolute',
                        left: 19,
                        top: -4,
                        transform: 'translateY(-100%)',
                        width: 2,
                        height: 12,
                        background: 'var(--border)',
                      }}
                    />
                  )}
                  <div style={{
                    display: 'flex',
                    gap: 12,
                    overflowX: 'auto',
                    padding: '12px 0 12px 48px',
                  }}>
                    {item.branches.map((branch, bi) => {
                      const branchColor = BRANCH_COLORS[bi % BRANCH_COLORS.length]
                      const branchIdx = (branch.records[0]?.branch_index ?? bi)
                      const allDone = branch.records.every((r) => ['approved', 'rejected', 'escalated', 'transferred'].includes(r.status))
                      return (
                        <div
                          key={branch.branch_id}
                          style={{
                            flex: '1 1 0',
                            minWidth: 260,
                            border: `2px solid ${branchColor}`,
                            borderRadius: 10,
                            background: 'var(--bg-primary)',
                            position: 'relative',
                          }}
                        >
                          <div style={{
                            padding: '6px 10px',
                            background: branchColor,
                            color: '#fff',
                            borderTopLeftRadius: 8,
                            borderTopRightRadius: 8,
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                          }}>
                            <span style={{ fontWeight: 600, fontSize: 13 }}>分支 {branchIdx + 1}</span>
                            <span style={{ fontSize: 11, opacity: 0.9 }}>
                              {allDone ? '✓ 已完成' : '⏳ 进行中'}
                            </span>
                          </div>
                          <div style={{ padding: 8 }}>
                            {(() => {
                              const grouped = {}
                              for (const r of branch.records) {
                                if (!grouped[r.level]) grouped[r.level] = []
                                grouped[r.level].push(r)
                              }
                              const bs = Object.keys(grouped).map(Number).sort((a, b) => a - b)
                              return bs.map((lv, li) => {
                                const recs = grouped[lv]
                                const firstRec = recs[0]
                                if (firstRec.node_type === 'sub_process' && firstRec.sub_process_records) {
                                  return (
                                    <SubProcessBlock
                                      key={lv}
                                      level={lv}
                                      nodeRecord={firstRec}
                                      subRecords={firstRec.sub_process_records}
                                      approval={approval}
                                      currentUser={currentUser}
                                      onAddSigner={onAddSigner}
                                      onTransfer={onTransfer}
                                      showConnector={li > 0}
                                      nestingLevel={1}
                                    />
                                  )
                                }
                                const sub = { ...approval }
                                return (
                                  <LevelNodeBlock
                                    key={lv}
                                    level={lv}
                                    records={grouped[lv]}
                                    approval={sub}
                                    currentUser={currentUser}
                                    onAddSigner={onAddSigner}
                                    onTransfer={onTransfer}
                                    levelIdx={li}
                                    totalLevels={bs.length}
                                    showConnector={li > 0}
                                  />
                                )
                              })
                            })()}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            }
            return (
              <LevelNodeBlock
                key={idx}
                level={item.level}
                records={item.records}
                approval={approval}
                currentUser={currentUser}
                onAddSigner={onAddSigner}
                onTransfer={onTransfer}
                levelIdx={idx}
                totalLevels={levels.length}
                showConnector={idx > 0}
              />
            )
          })}
        </div>
      ) : (
        <div className="approval-chain-timeline">
          {levels.map((level, levelIdx) => {
            const records = levelGroups[level]
            const firstRec = records[0]
            if (firstRec.node_type === 'sub_process' && firstRec.sub_process_records) {
              return (
                <SubProcessBlock
                  key={level}
                  level={level}
                  nodeRecord={firstRec}
                  subRecords={firstRec.sub_process_records}
                  approval={approval}
                  currentUser={currentUser}
                  onAddSigner={onAddSigner}
                  onTransfer={onTransfer}
                  showConnector={levelIdx > 0}
                  nestingLevel={0}
                />
              )
            }
            return (
              <LevelNodeBlock
                key={level}
                level={level}
                records={levelGroups[level]}
                approval={approval}
                currentUser={currentUser}
                onAddSigner={onAddSigner}
                onTransfer={onTransfer}
                levelIdx={levelIdx}
                totalLevels={levels.length}
                showConnector={levelIdx > 0}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function ApprovalTimeline({ timeline }) {
  if (!timeline || timeline.length === 0) return null

  return (
    <div className="card">
      <h3 style={{ marginBottom: 16 }}>
        审批时间线
        <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-secondary)', marginLeft: 8 }}>
          共 {timeline.length} 条记录
        </span>
      </h3>
      <div
        style={{
          position: 'relative',
          paddingLeft: 28,
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 9,
            top: 4,
            bottom: 4,
            width: 2,
            background: 'var(--border)',
          }}
        />
        {timeline.map((event, idx) => (
          <div
            key={event.id}
            style={{
              position: 'relative',
              paddingBottom: idx < timeline.length - 1 ? 18 : 0,
            }}
          >
            <div
              style={{
                position: 'absolute',
                left: -28,
                top: 2,
                width: 20,
                height: 20,
                borderRadius: '50%',
                background: 'var(--bg-secondary)',
                border: '2px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
              }}
            >
              {EVENT_ICON_MAP[event.event_type] || '📌'}
            </div>
            <div
              style={{
                background: 'var(--bg-secondary)',
                borderRadius: 8,
                padding: '10px 14px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{event.event_type_cn}</span>
                {event.level && (
                  <span
                    className="status-badge"
                    style={{
                      fontSize: 11,
                      background: 'var(--bg-primary)',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    Level {event.level}
                  </span>
                )}
                {event.status && (
                  <span className={`status-badge status-${event.status}`} style={{ fontSize: 11 }}>
                    {STATUS_MAP[event.status] || event.status}
                  </span>
                )}
                <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
                  {formatTime(event.created_at)}
                </span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>
                <span style={{ fontWeight: 500 }}>{event.operator}</span>
                {event.target_user && (
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {' → '}
                    <span style={{ color: 'var(--primary)', fontWeight: 500 }}>{event.target_user}</span>
                    {event.target_role && (
                      <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                        {' '}({event.target_role})
                      </span>
                    )}
                  </span>
                )}
                {event.operator_id && (
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                    {' '}ID:{event.operator_id}
                  </span>
                )}
              </div>
              {(event.reason || event.opinion) && (
                <div
                  style={{
                    marginTop: 6,
                    fontSize: 13,
                    padding: '6px 10px',
                    background: 'var(--bg-primary)',
                    borderRadius: 4,
                    color: 'var(--text-secondary)',
                    borderLeft: '3px solid var(--primary)',
                  }}
                >
                  {event.reason && (
                    <div>
                      <span style={{ fontWeight: 500 }}>原因：</span>
                      {event.reason}
                    </div>
                  )}
                  {event.opinion && (
                    <div>
                      <span style={{ fontWeight: 500 }}>意见：</span>
                      {event.opinion}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function UserSelectModal({ title, users, onClose, onConfirm, reasonLabel = '原因', showNodeRecordSelect = false, pendingRecords = [] }) {
  const [selectedUserId, setSelectedUserId] = useState('')
  const [reason, setReason] = useState('')
  const [selectedNodeRecordId, setSelectedNodeRecordId] = useState('')

  const handleConfirm = () => {
    if (!selectedUserId) {
      alert('请选择目标用户')
      return
    }
    if (showNodeRecordSelect && !selectedNodeRecordId) {
      alert('请选择要加签的节点')
      return
    }
    onConfirm({
      userId: Number(selectedUserId),
      nodeRecordId: showNodeRecordSelect ? Number(selectedNodeRecordId) : null,
      reason: reason || undefined,
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h3>{title}</h3>
        <div className="form-group" style={{ marginBottom: 14 }}>
          <label>选择目标用户</label>
          <select
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
            style={{ width: '100%' }}
          >
            <option value="">-- 请选择 --</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.real_name || u.username} ({u.department || '-'}
                {u.roles && u.roles.length > 0 && ` - ${u.roles.join(', ')}`})
              </option>
            ))}
          </select>
        </div>
        {showNodeRecordSelect && pendingRecords.length > 0 && (
          <div className="form-group" style={{ marginBottom: 14 }}>
            <label>选择加签节点</label>
            <select
              value={selectedNodeRecordId}
              onChange={(e) => setSelectedNodeRecordId(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="">-- 请选择待审批的节点 --</option>
              {pendingRecords.map((r) => (
                <option key={r.id} value={r.id}>
                  #{r.id} - {r.approver_name} ({r.approver_role})
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>{reasonLabel}（可选）</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={`请输入${reasonLabel}（最多500字）`}
            rows={3}
            maxLength={500}
          />
        </div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button className="btn btn-outline" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={handleConfirm}>确认</button>
        </div>
      </div>
    </div>
  )
}

export default function ApprovalDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [approval, setApproval] = useState(null)
  const [loading, setLoading] = useState(true)
  const [opinion, setOpinion] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [showAddSignerModal, setShowAddSignerModal] = useState(false)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [availableUsers, setAvailableUsers] = useState([])
  const [pendingRecordsForAddSigner, setPendingRecordsForAddSigner] = useState([])
  const [transferTargetRecord, setTransferTargetRecord] = useState(null)
  const [currentUser, setCurrentUser] = useState(null)

  const fetchApproval = async () => {
    try {
      const res = await getApproval(id)
      setApproval(res.data)
    } catch {
      setApproval(null)
    } finally {
      setLoading(false)
    }
  }

  const fetchCurrentUser = async () => {
    try {
      const token = localStorage.getItem('token')
      if (token) {
        try {
          const res = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` },
          })
          if (res.ok) {
            const profile = await res.json()
            const roleCodes = Array.isArray(profile.roles)
              ? profile.roles.map(r => (typeof r === 'string' ? r : r.code)).filter(Boolean)
              : []
            setCurrentUser({
              id: profile.id,
              username: profile.username,
              real_name: profile.real_name || profile.username,
              roles: roleCodes,
            })
            return
          }
        } catch (apiErr) {
          console.warn('API /me failed, falling back to token parse:', apiErr)
        }
        const payload = JSON.parse(atob(token.split('.')[1]))
        setCurrentUser({
          id: payload.user_id || payload.sub,
          username: payload.username || payload.sub,
          real_name: payload.real_name || payload.username || payload.sub,
          roles: payload.roles || [],
        })
      }
    } catch (e) {
      console.error('Failed to parse user from token:', e)
    }
  }

  useEffect(() => {
    fetchApproval()
    fetchCurrentUser()
  }, [id])

  useEffect(() => {
    if (approval?.status !== 'pending') return
    const timer = setInterval(() => {
      fetchApproval()
    }, 30000)
    return () => clearInterval(timer)
  }, [approval?.status, id])

  if (loading) return <div className="empty-state"><p>加载中...</p></div>
  if (!approval) return <div className="empty-state"><p>审批单不存在</p></div>

  const handleApprove = async () => {
    setSubmitting(true)
    try {
      await approveApproval(id, { opinion: opinion || undefined })
      alert('审批通过成功')
      setOpinion('')
      fetchApproval()
    } catch (err) {
      alert(err.response?.data?.detail || '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReject = async () => {
    setSubmitting(true)
    try {
      await rejectApproval(id, { opinion: opinion || undefined })
      alert('审批驳回成功')
      setOpinion('')
      fetchApproval()
    } catch (err) {
      alert(err.response?.data?.detail || '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleAddSigner = async (level, records) => {
    try {
      setModalLoading(true)
      const pendingRecords = records.filter(
        (r) => r.status === 'pending' && r.transfer_status !== 'transferred'
      )
      setPendingRecordsForAddSigner(pendingRecords)
      const res = await getAvailableApprovalUsers()
      setAvailableUsers(res.data.items || res.data || [])
      setShowAddSignerModal(true)
    } finally {
      setModalLoading(false)
    }
  }

  const handleConfirmAddSigner = async ({ userId, nodeRecordId, reason }) => {
    setModalLoading(true)
    try {
      await addSigner(id, {
        node_record_id: nodeRecordId,
        target_user_id: userId,
        reason,
      })
      alert('加签成功')
      setShowAddSignerModal(false)
      fetchApproval()
    } catch (err) {
      alert(err.response?.data?.detail || '加签失败')
    } finally {
      setModalLoading(false)
    }
  }

  const handleTransfer = async (record) => {
    try {
      setModalLoading(true)
      setTransferTargetRecord(record)
      const res = await getAvailableApprovalUsers()
      setAvailableUsers(res.data.items || res.data || [])
      setShowTransferModal(true)
    } finally {
      setModalLoading(false)
    }
  }

  const handleConfirmTransfer = async ({ userId, reason }) => {
    setModalLoading(true)
    try {
      await transferApproval(id, {
        node_record_id: transferTargetRecord.id,
        target_user_id: userId,
        reason,
      })
      alert('转审成功')
      setShowTransferModal(false)
      setTransferTargetRecord(null)
      fetchApproval()
    } catch (err) {
      alert(err.response?.data?.detail || '转审失败')
    } finally {
      setModalLoading(false)
    }
  }

  return (
    <div className="approval-detail">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2>审批详情</h2>
        <button className="btn btn-outline" onClick={() => navigate(-1)}>返回</button>
      </div>

      <div className="card approval-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div>
            <h3 style={{ marginBottom: 8 }}>
              审批单 #{approval.id}
            </h3>
            <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
              {TYPE_MAP[approval.approval_type] || approval.approval_type}
            </span>
          </div>
          <span className={`status-badge status-${approval.status}`}>
            {STATUS_MAP[approval.status]}
          </span>
        </div>
        <div className="detail-grid">
          <div className="detail-item">
            <span className="label">资产名称</span>
            <span className="value">{approval.asset_name || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">资产编号</span>
            <span className="value" style={{ fontFamily: 'monospace' }}>{approval.asset_tag || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">申请人</span>
            <span className="value">{approval.applicant}</span>
          </div>
          <div className="detail-item">
            <span className="label">领用人</span>
            <span className="value">{approval.assignee || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">申请原因</span>
            <span className="value">{approval.reason || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">购入价格</span>
            <span className="value">{approval.purchase_price != null ? `¥${approval.purchase_price}` : '-'}</span>
          </div>
          <div className="detail-item">
            <span className="label">申请时间</span>
            <span className="value">{formatTime(approval.created_at)}</span>
          </div>
          <div className="detail-item">
            <span className="label">更新时间</span>
            <span className="value">{formatTime(approval.updated_at)}</span>
          </div>
        </div>
      </div>

      <ChainTimeline
        approval={approval}
        currentUser={currentUser}
        onAddSigner={handleAddSigner}
        onTransfer={handleTransfer}
      />

      <ApprovalTimeline timeline={approval.timeline} />

      {approval.status === 'pending' && (
        <div className="card approval-actions">
          <h3 style={{ marginBottom: 16 }}>审批操作</h3>
          <div className="form-group" style={{ marginBottom: 16 }}>
            <label>审批意见</label>
            <textarea
              value={opinion}
              onChange={(e) => setOpinion(e.target.value)}
              placeholder="请输入审批意见（可选）"
              rows={3}
            />
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
            <button
              className="btn btn-danger"
              onClick={handleReject}
              disabled={submitting}
            >
              {submitting ? '处理中...' : '驳回'}
            </button>
            <button
              className="btn btn-success"
              onClick={handleApprove}
              disabled={submitting}
            >
              {submitting ? '处理中...' : '通过'}
            </button>
          </div>
        </div>
      )}

      {showAddSignerModal && (
        <UserSelectModal
          title="会签加签"
          users={availableUsers}
          reasonLabel="加签原因"
          showNodeRecordSelect={pendingRecordsForAddSigner.length > 1}
          pendingRecords={pendingRecordsForAddSigner}
          onClose={() => setShowAddSignerModal(false)}
          onConfirm={handleConfirmAddSigner}
        />
      )}

      {showTransferModal && transferTargetRecord && (
        <UserSelectModal
          title={`转审 - 将 ${transferTargetRecord.approver_name} 的待办转审给他人`}
          users={availableUsers.filter((u) => u.id !== currentUser?.id)}
          reasonLabel="转审原因"
          onClose={() => {
            setShowTransferModal(false)
            setTransferTargetRecord(null)
          }}
          onConfirm={handleConfirmTransfer}
        />
      )}
    </div>
  )
}
