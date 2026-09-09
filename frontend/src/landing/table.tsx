// Minimal Table wrappers — the visual styling lives in refined-landing.css
// (.r-preview-table). Mirrors the design kit's shadcn Table structure
// (a scroll container around a plain <table>).
export function Table({ className = '', children, ...rest }: any) {
  return (
    <div data-slot="table-container" style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
      <table data-slot="table" className={className} {...rest}>
        {children}
      </table>
    </div>
  );
}
export function TableHeader({ children, ...rest }: any) {
  return <thead data-slot="table-header" {...rest}>{children}</thead>;
}
export function TableBody({ children, ...rest }: any) {
  return <tbody data-slot="table-body" {...rest}>{children}</tbody>;
}
export function TableRow({ children, ...rest }: any) {
  return <tr data-slot="table-row" {...rest}>{children}</tr>;
}
export function TableHead({ children, ...rest }: any) {
  return <th data-slot="table-head" {...rest}>{children}</th>;
}
export function TableCell({ className = '', children, ...rest }: any) {
  return <td data-slot="table-cell" className={className} {...rest}>{children}</td>;
}
