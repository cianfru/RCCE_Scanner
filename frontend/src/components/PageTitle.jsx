import { T } from "../theme.js";
import useViewport from "../hooks/useViewport.js";

// The page title: the same Bricolage heading every page has always shown, now an h1.
export default function PageTitle({ children }) {
  const { isMobile } = useViewport();
  return (
    <h1 style={{
      fontSize: isMobile ? 25 : 34,
      fontWeight: 550,
      color: T.text1,
      fontFamily: "var(--font-display), sans-serif",
      letterSpacing: "-0.035em",
      margin: 0,
    }}>
      {children}
    </h1>
  );
}
