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
      tabIndex={active ? 0 : -1}
      onKeyDown={event => {
        const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
        if (!keys.includes(event.key)) return;
        const buttons = Array.from(event.currentTarget.closest('[role="tablist"]')?.querySelectorAll<HTMLButtonElement>('[role="tab"]') || []);
        const index = buttons.indexOf(event.currentTarget);
        if (!buttons.length) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
        buttons[next].focus();
        buttons[next].click();
      }}
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
