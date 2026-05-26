import { useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { useProduct } from '@/hooks/useProducts';
import { useAlerts } from '@/hooks/useAlerts';
import { useScrapeProduct } from '@/hooks/useScrape';
import { useUIStore } from '@/store/uiStore';
import { PriceChart } from '@/components/PriceChart';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

export function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);
  const navigate = useNavigate();
  const { setSelectedProductId } = useUIStore();

  const { data: product, isLoading, isError } = useProduct(productId);
  const { data: alertsData } = useAlerts(productId, { isActive: true });
  const scrapeMutation = useScrapeProduct();

  useEffect(() => {
    setSelectedProductId(productId);
    return () => setSelectedProductId(null);
  }, [productId, setSelectedProductId]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !product) {
    return (
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Product not found</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            This product does not exist or has been removed.
          </p>
          <Button onClick={() => navigate('/')}>Back to Dashboard</Button>
        </CardContent>
      </Card>
    );
  }

  const activeAlertCount = alertsData?.total ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1 flex-1 min-w-0">
          <h1 className="text-2xl font-bold truncate">{product.name}</h1>
          <a
            href={product.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-muted-foreground hover:underline flex items-center gap-1 truncate"
          >
            {product.url}
            <ExternalLink className="h-3 w-3 flex-shrink-0" />
          </a>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="capitalize">
              {product.source_type}
            </Badge>
            <Badge variant={product.is_active ? 'success' : 'secondary'}>
              {product.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </div>
        </div>
        <Button
          onClick={() => scrapeMutation.mutate(productId)}
          disabled={scrapeMutation.isPending}
          size="sm"
        >
          {scrapeMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          Scrape Now
        </Button>
      </div>

      {/* Price Chart */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Price History</h2>
        <PriceChart productId={productId} />
      </div>

      {/* Alerts summary */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Price Alerts</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {activeAlertCount > 0
              ? `${activeAlertCount} active alert${activeAlertCount !== 1 ? 's' : ''}`
              : 'No active alerts'}
          </p>
          <Button asChild size="sm" variant="outline">
            <Link to={`/products/${productId}/alerts`}>Manage alerts</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
