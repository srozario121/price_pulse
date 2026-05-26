import { describe, it, expect, beforeEach } from 'vitest';
import { useUIStore } from '../../src/store/uiStore';

// Reset store between tests
beforeEach(() => {
  useUIStore.setState({
    selectedProductId: null,
    colorScheme: 'system',
    activeProductFilter: null,
    activeAlertFilter: null,
  });
});

describe('uiStore', () => {
  it('setSelectedProductId updates the store', () => {
    useUIStore.getState().setSelectedProductId(42);
    expect(useUIStore.getState().selectedProductId).toBe(42);
  });

  it('setColorScheme updates the store', () => {
    useUIStore.getState().setColorScheme('dark');
    expect(useUIStore.getState().colorScheme).toBe('dark');
  });

  it('setActiveProductFilter updates the store', () => {
    useUIStore.getState().setActiveProductFilter(true);
    expect(useUIStore.getState().activeProductFilter).toBe(true);
  });

  it('setActiveAlertFilter updates the store', () => {
    useUIStore.getState().setActiveAlertFilter(false);
    expect(useUIStore.getState().activeAlertFilter).toBe(false);
  });

  it('initial colorScheme is system', () => {
    expect(useUIStore.getState().colorScheme).toBe('system');
  });
});
