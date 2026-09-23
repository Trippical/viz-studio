import { Link, Route, Routes } from 'react-router-dom';
import { DashboardPage } from './pages/DashboardPage';
import { TreePage } from './pages/TreePage';

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>viz-site</h1>
        <nav>
          <Link to="/">Dashboards</Link>
          <Link to="/charts">Charts</Link>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<TreePage kind="dashboards" />} />
          <Route path="/charts" element={<TreePage kind="charts" />} />
          <Route path="/d/*" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}
