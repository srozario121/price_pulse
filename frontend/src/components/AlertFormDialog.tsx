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
import { useCreateAlert, useUpdateAlert } from '@/hooks/useAlerts';
import type { AlertRead } from '@/api/types';

const schema = z
  .object({
    threshold_price: z.coerce.number().positive('Must be a positive number'),
    direction: z.enum(['above', 'below']),
    channel: z.enum(['email', 'webhook', 'whatsapp']),
    webhook_url: z.string().url('Must be a valid URL').optional().or(z.literal('')),
    whatsapp_number: z
      .string()
      .regex(/^\+[1-9]\d{7,14}$/, 'Must be E.164 format e.g. +447911123456')
      .optional()
      .or(z.literal('')),
    is_active: z.boolean().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.channel === 'webhook' && !data.webhook_url) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Webhook URL is required for webhook channel',
        path: ['webhook_url'],
      });
    }
    if (data.channel === 'whatsapp' && !data.whatsapp_number) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'WhatsApp number is required for WhatsApp channel',
        path: ['whatsapp_number'],
      });
    }
  });

type FormValues = z.infer<typeof schema>;

interface AlertFormDialogProps {
  productId: number;
  mode: 'create' | 'edit';
  alert?: AlertRead;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AlertFormDialog({
  productId,
  mode,
  alert,
  open,
  onOpenChange,
}: AlertFormDialogProps) {
  const createMutation = useCreateAlert();
  const updateMutation = useUpdateAlert(alert?.id ?? 0);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      threshold_price: 0,
      direction: 'below',
      channel: 'email',
      webhook_url: '',
      whatsapp_number: '',
      is_active: true,
    },
  });

  const channel = form.watch('channel');

  useEffect(() => {
    if (mode === 'edit' && alert) {
      form.reset({
        threshold_price: Number(alert.threshold_price),
        direction: alert.direction,
        channel: alert.channel,
        webhook_url: alert.webhook_url ?? '',
        whatsapp_number: alert.whatsapp_number ?? '',
        is_active: alert.is_active,
      });
    } else if (mode === 'create') {
      form.reset({
        threshold_price: 0,
        direction: 'below',
        channel: 'email',
        webhook_url: '',
        whatsapp_number: '',
        is_active: true,
      });
    }
  }, [mode, alert, form, open]);

  const onSubmit = async (values: FormValues) => {
    try {
      if (mode === 'create') {
        await createMutation.mutateAsync({
          product_id: productId,
          threshold_price: values.threshold_price,
          direction: values.direction,
          channel: values.channel,
          webhook_url: values.webhook_url || null,
          whatsapp_number: values.whatsapp_number || null,
          is_active: values.is_active,
        });
      } else {
        await updateMutation.mutateAsync({
          threshold_price: values.threshold_price,
          direction: values.direction,
          channel: values.channel,
          webhook_url: values.webhook_url || null,
          whatsapp_number: values.whatsapp_number || null,
          is_active: values.is_active,
        });
      }
      toast.success('Alert saved');
      onOpenChange(false);
    } catch (err: unknown) {
      const e = err as { detail?: string };
      toast.error(e.detail ?? 'Failed to save alert');
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? 'Add Alert' : 'Edit Alert'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="threshold_price"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Threshold Price</FormLabel>
                  <FormControl>
                    <Input type="number" step="0.01" placeholder="9.99" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="direction"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Direction</FormLabel>
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="below">Below (alert when price drops)</SelectItem>
                      <SelectItem value="above">Above (alert when price rises)</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="channel"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Notification Channel</FormLabel>
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="email">Email</SelectItem>
                      <SelectItem value="webhook">Webhook</SelectItem>
                      <SelectItem value="whatsapp">WhatsApp</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            {channel === 'webhook' && (
              <FormField
                control={form.control}
                name="webhook_url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Webhook URL</FormLabel>
                    <FormControl>
                      <Input placeholder="https://hooks.example.com/..." {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            {channel === 'whatsapp' && (
              <FormField
                control={form.control}
                name="whatsapp_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>WhatsApp Number</FormLabel>
                    <FormControl>
                      <Input placeholder="+447911123456" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
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
