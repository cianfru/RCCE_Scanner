import GlassCard from "../components/GlassCard.jsx";
import FadeIn from "../components/FadeIn.jsx";
import SettingsDropdown from "../components/SettingsDropdown.jsx";
import useViewport from "../hooks/useViewport.js";

// /settings: the gear's controls as a page (reached from More). The title row comes from App.
export default function SettingsPage({ style }) {
  const { isMobile } = useViewport();
  return (
    <FadeIn delay={150} style={style}>
      <GlassCard style={{ maxWidth: 760, padding: isMobile ? 16 : 24 }}>
        <SettingsDropdown embedded />
      </GlassCard>
    </FadeIn>
  );
}
