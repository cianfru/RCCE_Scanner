// Minimal controlled Tabs — replaces the design kit's base-ui Tabs.
// Emits the exact hooks the landing CSS targets: [data-slot] and [data-active].
import { createContext, useContext } from 'react';

type Ctx = { value: string; onValueChange: (v: string) => void };
const TabsCtx = createContext<Ctx>({ value: '', onValueChange: () => {} });

export function Tabs({ value, onValueChange, className = '', children }: any) {
  return (
    <div data-slot="tabs" className={className}>
      <TabsCtx.Provider value={{ value, onValueChange }}>{children}</TabsCtx.Provider>
    </div>
  );
}

export function TabsList({ className = '', children, ...rest }: any) {
  return (
    <div data-slot="tabs-list" role="tablist" className={className} {...rest}>
      {children}
    </div>
  );
}

export function TabsTrigger({ value, className = '', children, ...rest }: any) {
  const ctx = useContext(TabsCtx);
  const active = ctx.value === value;
  return (
    <button
      type="button"
      role="tab"
      data-slot="tabs-trigger"
      data-active={active ? '' : undefined}
      aria-selected={active}
      className={className}
      onClick={() => ctx.onValueChange(value)}
      {...rest}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, className = '', children }: any) {
  const ctx = useContext(TabsCtx);
  if (ctx.value !== value) return null;
  return (
    <div data-slot="tabs-content" className={className}>
      {children}
    </div>
  );
}
