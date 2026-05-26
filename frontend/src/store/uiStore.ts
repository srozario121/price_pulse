import { create } from 'zustand';

type ColorScheme = 'light' | 'dark' | 'system';

interface UIState {
  selectedProductId: number | null;
  colorScheme: ColorScheme;
  activeProductFilter: boolean | null;
  activeAlertFilter: boolean | null;
  setSelectedProductId: (id: number | null) => void;
  setColorScheme: (scheme: ColorScheme) => void;
  setActiveProductFilter: (filter: boolean | null) => void;
  setActiveAlertFilter: (filter: boolean | null) => void;
}

const getInitialColorScheme = (): ColorScheme => {
  if (typeof window === 'undefined') return 'system';
  // default to 'system'
  return 'system';
};

export const useUIStore = create<UIState>((set) => ({
  selectedProductId: null,
  colorScheme: getInitialColorScheme(),
  activeProductFilter: null,
  activeAlertFilter: null,
  setSelectedProductId: (id) => set({ selectedProductId: id }),
  setColorScheme: (scheme) => set({ colorScheme: scheme }),
  setActiveProductFilter: (filter) => set({ activeProductFilter: filter }),
  setActiveAlertFilter: (filter) => set({ activeAlertFilter: filter }),
}));
