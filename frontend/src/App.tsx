import { Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Dashboard } from '@/pages/Dashboard';
import { ProductDetail } from '@/pages/ProductDetail';
import { AlertManager } from '@/pages/AlertManager';

export function App() {
  return (
    <ErrorBoundary>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/products/:id" element={<ProductDetail />} />
          <Route path="/products/:id/alerts" element={<AlertManager />} />
        </Routes>
      </Layout>
    </ErrorBoundary>
  );
}
