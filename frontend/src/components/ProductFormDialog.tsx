import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useCreateProduct, useUpdateProduct } from '@/hooks/useProducts';
import { useSources } from '@/hooks/useSources';
import type { ProductRead } from '@/api/types';

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  url: z.string().url('Must be a valid URL'),
  source_type: z.string().min(1, 'Source type is required'),
  css_selector: z.string().optional(),
  css_selector_currency: z.string().optional(),
  is_active: z.boolean().optional(),
});

type FormValues = z.infer<typeof schema>;

interface ProductFormDialogProps {
  mode: 'create' | 'edit';
  product?: ProductRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ProductFormDialog({
  mode,
  product,
  open,
  onOpenChange,
}: ProductFormDialogProps) {
  const createMutation = useCreateProduct();
  const updateMutation = useUpdateProduct(product?.id ?? 0);
  const { data: sources } = useSources();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      url: '',
      source_type: 'generic',
      css_selector: '',
      css_selector_currency: '',
      is_active: true,
    },
  });

  const sourceType = form.watch('source_type');

  useEffect(() => {
    if (mode === 'edit' && product) {
      form.reset({
        name: product.name,
        url: product.url,
        source_type: product.source_type,
        css_selector: product.css_selector ?? '',
        css_selector_currency: product.css_selector_currency ?? '',
        is_active: product.is_active,
      });
    } else if (mode === 'create') {
      form.reset({
        name: '',
        url: '',
        source_type: 'generic',
        css_selector: '',
        css_selector_currency: '',
        is_active: true,
      });
    }
  }, [mode, product, form, open]);

  const onSubmit = async (values: FormValues) => {
    const payload = {
      ...values,
      css_selector: values.css_selector || null,
      css_selector_currency: values.css_selector_currency || null,
    };
    try {
      if (mode === 'create') {
        await createMutation.mutateAsync(payload);
      } else {
        await updateMutation.mutateAsync(payload);
      }
      toast.success('Product saved');
      onOpenChange(false);
    } catch (err: unknown) {
      const e = err as { detail?: string };
      toast.error(e.detail ?? 'Failed to save product');
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {mode === 'create' ? 'Add Product' : 'Edit Product'}
          </DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Product name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>URL</FormLabel>
                  <FormControl>
                    <Input placeholder="https://..." {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="source_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Source Type</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select source type" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {(sources ?? []).map((preset) => (
                        <SelectItem key={preset.key} value={preset.key}>
                          {preset.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            {sourceType === 'generic' && (
              <>
                <FormField
                  control={form.control}
                  name="css_selector"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>CSS Selector</FormLabel>
                      <FormControl>
                        <Input placeholder=".price" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="css_selector_currency"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>CSS Selector (Currency)</FormLabel>
                      <FormControl>
                        <Input placeholder=".currency" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isPending}>
                {isPending ? 'Saving…' : 'Save'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
