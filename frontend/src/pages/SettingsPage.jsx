import GlassCard from "../components/GlassCard.jsx";
import FadeIn from "../components/FadeIn.jsx";
import SettingsForm from "../components/SettingsForm.jsx";
import useViewport from "../hooks/useViewport.js";

// /settings: the owner's runtime controls, opened by its address (not linked from the header or More). The title row comes from App.
export default function SettingsPage({ style }) {
  const { isMobile } = useViewport();
  return (
    <FadeIn delay={150} style={style}>
      <GlassCard style={{ maxWidth: 760, padding: isMobile ? 16 : 24 }}>
        <SettingsForm />
      </GlassCard>
    </FadeIn>
  );
}
