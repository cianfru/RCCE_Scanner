import { useEffect, useState } from "react";

// Shown briefly when the server refuses a change without the admin key (see auth.js).
export default function AdminNotice() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    let timer;
    const on = () => { setShow(true); clearTimeout(timer); timer = setTimeout(() => setShow(false), 6000); };
    window.addEventListener("reflex-admin-required", on);
    return () => { window.removeEventListener("reflex-admin-required", on); clearTimeout(timer); };
  }, []);
  if (!show) return null;
  return <div className="admin-notice" role="status">This change needs the admin key. Add it under Settings.</div>;
}
