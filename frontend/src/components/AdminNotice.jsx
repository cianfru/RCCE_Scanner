import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

// Shown briefly when the server refuses a change without the admin key (see auth.js). /settings is not in the
// menus, so the notice links to it.
export default function AdminNotice() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    let timer;
    const on = () => { setShow(true); clearTimeout(timer); timer = setTimeout(() => setShow(false), 6000); };
    window.addEventListener("reflex-admin-required", on);
    return () => { window.removeEventListener("reflex-admin-required", on); clearTimeout(timer); };
  }, []);
  if (!show) return null;
  return <div className="admin-notice" role="status">This change needs the admin key. Add it in <Link to="/settings" onClick={() => setShow(false)}>Settings</Link>.</div>;
}
