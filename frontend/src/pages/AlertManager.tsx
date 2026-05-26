import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Plus, Pencil, Trash2 } from 'lucide-react';
import { format } from 'date-fns';
import { useAlerts, useDeleteAlert } from '@/hooks/useAlerts';
import { useUIStore } from '@/store/uiStore';
import { formatPrice } from '@/lib/formatPrice';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';
import { AlertFormDialog } from '@/components/AlertFormDialog';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import type { AlertRead } from '@/api/types';

export function AlertManager() {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);
  const { activeAlertFilter, setActiveAlertFilter } = useUIStore();

  const [createOpen, setCreateOpen] = useState(false);
  const [editAlert, setEditAlert] = useState<AlertRead | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  const { data, isLoading } = useAlerts(productId, {
    isActive: activeAlertFilter ?? undefined,
  });
  const deleteMutation = useDeleteAlert();

  const alerts = data?.items ?? [];

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <Link
        to={`/products/${productId}`}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to product
      </Link>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Price Alerts</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add alert
        </Button>
      </div>

      {/* Filter buttons */}
      <div className="flex gap-2">
        <Button
          variant={activeAlertFilter === null ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveAlertFilter(null)}
        >
          All
        </Button>
        <Button
          variant={activeAlertFilter === true ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveAlertFilter(true)}
        >
          Active
        </Button>
        <Button
          variant={activeAlertFilter === false ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveAlertFilter(false)}
        >
          Inactive
        </Button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && alerts.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
            <p>No alerts found.</p>
            <Button variant="outline" onClick={() => setCreateOpen(true)}>
              Add your first alert
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Alert list */}
      {!isLoading && alerts.length > 0 && (
        <div className="border rounded-lg overflow-hidden divide-y">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="flex items-center justify-between p-4 hover:bg-muted/50"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">
                    {formatPrice(alert.threshold_price, 'GBP')}
                  </span>
                  <Badge
                    variant={alert.direction === 'below' ? 'success' : 'warning'}
                    className="capitalize"
                  >
                    {alert.direction}
                  </Badge>
                  <Badge variant="outline" className="capitalize">
                    {alert.channel}
                  </Badge>
                  <Badge
                    variant={alert.is_active ? 'success' : 'secondary'}
                  >
                    {alert.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
                {alert.notified_at && (
                  <p className="text-xs text-muted-foreground">
                    Last notified:{' '}
                    {format(new Date(alert.notified_at), 'dd MMM yyyy HH:mm')}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setEditAlert(alert)}
                >
                  <Pencil className="h-4 w-4" />
                  <span className="sr-only">Edit</span>
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive"
                  onClick={() => setDeleteId(alert.id)}
                >
                  <Trash2 className="h-4 w-4" />
                  <span className="sr-only">Delete</span>
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Dialogs */}
      <AlertFormDialog
        productId={productId}
        mode="create"
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
      {editAlert && (
        <AlertFormDialog
          productId={productId}
          mode="edit"
          alert={editAlert}
          open={!!editAlert}
          onOpenChange={(o) => { if (!o) setEditAlert(null); }}
        />
      )}
      <ConfirmDialog
        title="Delete alert"
        description="This alert will be permanently deleted."
        open={deleteId !== null}
        onOpenChange={(o) => { if (!o) setDeleteId(null); }}
        onConfirm={() => {
          if (deleteId !== null) {
            deleteMutation.mutate(deleteId, {
              onSuccess: () => setDeleteId(null),
            });
          }
        }}
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
