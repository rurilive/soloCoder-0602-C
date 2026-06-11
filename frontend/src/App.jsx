import { Routes, Route, NavLink } from 'react-router-dom'
import AssetList from './pages/AssetList'
import AssetForm from './pages/AssetForm'
import AssetDetail from './pages/AssetDetail'
import AssetScan from './pages/AssetScan'
import AssetTagRedirect from './pages/AssetTagRedirect'
import AssetImport from './pages/AssetImport'

export default function App() {
  return (
    <div className="app-layout">
      <header className="app-header">
        <h1>企业内部资产管理系统</h1>
        <nav>
          <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>资产列表</NavLink>
          <NavLink to="/assets/new" className={({ isActive }) => isActive ? 'active' : ''}>资产入库</NavLink>
          <NavLink to="/import" className={({ isActive }) => isActive ? 'active' : ''}>批量导入</NavLink>
          <NavLink to="/scan" className={({ isActive }) => isActive ? 'active' : ''}>扫码查询</NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<AssetList />} />
          <Route path="/assets/new" element={<AssetForm />} />
          <Route path="/assets/tag/:tag" element={<AssetTagRedirect />} />
          <Route path="/assets/:id/edit" element={<AssetForm />} />
          <Route path="/assets/:id" element={<AssetDetail />} />
          <Route path="/import" element={<AssetImport />} />
          <Route path="/scan" element={<AssetScan />} />
        </Routes>
      </main>
    </div>
  )
}
