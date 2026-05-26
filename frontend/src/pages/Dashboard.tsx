import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useInView } from 'react-intersection-observer';
import { MoreHorizontal, Plus } from 'lucide-react';
import {
  useInfiniteProducts,
  useDeleteProduct,
} from '@/hooks/useProducts';
import { productsApi } from '@/api/client';
import { useQueryClient } from '@tanstack/react-query';
import { useUIStore } from '@/store/uiStore';
import { formatPrice } from '@/lib/formatPrice';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ProductFormDialog } from '@/components/ProductFormDialog';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import type { ProductRead } from '@/api/types';


export function Dashboard() {
  const { activeProductFilter, setActiveProductFilter } = useUIStore();
  const [createOpen, setCreateOpen] = useState(false);
  const [editProduct, setEditProduct] = useState<ProductRead | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteProducts({ isActive: activeProductFilter ?? undefined });

  const { ref: sentinelRef, inView } = useInView();
  const qc = useQueryClient();

  useEffect(() => {
    if (inView && hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [inView, hasNextPage, isFetchingNextPage, fetchNextPage]);

  const allProducts = data?.pages.flatMap((p) => p.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  const deleteMutation = useDeleteProduct();

  const toggleActive = async (product: ProductRead) => {
    await productsApi.update(product.id, { is_active: !product.is_active });
    void qc.invalidateQueries({ queryKey: ['products'] });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Products</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add product
        </Button>
      </div>

      {/* Filter buttons */}
      <div className="flex gap-2">
        <Button
          variant={activeProductFilter === null ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveProductFilter(null)}
        >
          All
        </Button>
        <Button
          variant={activeProductFilter === true ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveProductFilter(true)}
        >
          Active
        </Button>
        <Button
          variant={activeProductFilter === false ? 'default' : 'outline'}
          size="sm"
          onClick={() => setActiveProductFilter(false)}
        >
          Inactive
        </Button>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && total === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
            <p>No products found.</p>
            <Button variant="outline" onClick={() => setCreateOpen(true)}>
              Add your first product
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Product list */}
      {!isLoading && allProducts.length > 0 && (
        <div className="border rounded-lg overflow-hidden divide-y">
          {allProducts.map((product) => (
            <div
              key={product.id}
              className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <Link
                  to={`/products/${product.id}`}
                  className="font-medium hover:underline truncate block"
                >
                  {product.name}
                </Link>
                <div className="flex items-center gap-2 mt-1">
                  <Badge variant="outline" className="text-xs capitalize">
                    {product.source_type}
                  </Badge>
                  <Badge
                    variant={product.is_active ? 'success' : 'secondary'}
                    className="text-xs"
                  >
                    {product.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground hidden sm:block">
                  {formatPrice(null, 'GBP')}
                </span>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <MoreHorizontal className="h-4 w-4" />
                      <span className="sr-only">Actions</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setEditProduct(product)}>
                      Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={() => void toggleActive(product)}
                    >
                      {product.is_active ? 'Deactivate' : 'Activate'}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => setDeleteId(product.id)}
                    >
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Infinite scroll sentinel */}
      <div ref={sentinelRef} className="py-2 flex justify-center">
        {isFetchingNextPage && <Skeleton className="h-8 w-32" />}
      </div>

      {/* Dialogs */}
      <ProductFormDialog
        mode="create"
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
      {editProduct && (
        <ProductFormDialog
          mode="edit"
          product={editProduct}
          open={!!editProduct}
          onOpenChange={(o) => { if (!o) setEditProduct(null); }}
        />
      )}
      <ConfirmDialog
        title="Delete product"
        description="This will permanently delete the product and all its price history and alerts. This action cannot be undone."
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
