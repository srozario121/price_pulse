import { useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { format, formatISO } from 'date-fns';
import type { DateRange } from 'react-day-picker';
import { CalendarIcon, X } from 'lucide-react';
import { usePrices } from '@/hooks/usePrices';
import { formatPrice } from '@/lib/formatPrice';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import type { PriceRecordRead } from '@/api/types';

interface TooltipPayload {
  payload?: PriceRecordRead;
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
}) {
  if (!active || !payload?.length) return null;
  const record = payload[0].payload as PriceRecordRead;
  return (
    <div className="rounded-lg border bg-background p-3 shadow-sm text-sm space-y-1">
      <p className="font-medium">
        {formatPrice(record.price, record.currency ?? 'GBP')}
      </p>
      <p className="text-muted-foreground">
        {format(new Date(record.captured_at), 'dd MMM yyyy HH:mm')}
      </p>
    </div>
  );
}

interface PriceChartProps {
  productId: number;
}

// The prices endpoint caps `limit` at 100 and returns 422 above it. Requesting
// 200 made every single chart request fail, so the component rendered its
// "no price data" empty state for every product forever — the error path and the
// genuinely-empty path looked identical, which is why it went unnoticed.
// Keep this in step with the `le=100` bound on GET /products/{id}/prices.
const MAX_PRICE_POINTS = 100;

export function PriceChart({ productId }: PriceChartProps) {
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);

  const { data, isLoading, isError } = usePrices(productId, {
    fromDt: dateRange?.from ? formatISO(dateRange.from) : undefined,
    toDt: dateRange?.to ? formatISO(dateRange.to) : undefined,
    limit: MAX_PRICE_POINTS,
  });

  const points =
    data?.items.filter((r) => r.price !== null).reverse() ?? [];

  // A short series needs visible marks: a single point draws a zero-length line,
  // so with dots suppressed the chart looks empty even when the data arrived.
  const showDots = points.length <= 30;

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <CalendarIcon className="h-4 w-4" />
              {dateRange?.from
                ? dateRange.to
                  ? `${format(dateRange.from, 'dd MMM')} – ${format(dateRange.to, 'dd MMM yyyy')}`
                  : format(dateRange.from, 'dd MMM yyyy')
                : 'All time'}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="range"
              selected={dateRange}
              onSelect={setDateRange}
              initialFocus
            />
          </PopoverContent>
        </Popover>
        {dateRange && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setDateRange(undefined)}
            aria-label="Clear date range"
          >
            <X className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      {isError ? (
        // Distinct from the empty state on purpose. Collapsing "the request
        // failed" into "there is no data" is what hid the 422 above: the chart
        // confidently reported an absence that was really a broken request.
        <Card>
          <CardContent
            role="alert"
            className="flex items-center justify-center py-12 text-destructive"
          >
            Could not load price history. Try again shortly.
          </CardContent>
        </Card>
      ) : points.length === 0 ? (
        <Card>
          <CardContent className="flex items-center justify-center py-12 text-muted-foreground">
            No price data available for this range.
          </CardContent>
        </Card>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={points}>
            <XAxis
              dataKey="captured_at"
              tickFormatter={(v: string) => format(new Date(v), 'dd MMM')}
              tick={{ fontSize: 12 }}
            />
            <YAxis
              tickFormatter={(v: number) =>
                formatPrice(v, points[0]?.currency ?? 'GBP')
              }
              tick={{ fontSize: 12 }}
              width={80}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="price"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={showDots ? { r: 3 } : false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
