import FadeIn from "../components/FadeIn.jsx";
import BridgeFlowWidget from "../components/BridgeFlowWidget.jsx";
import useViewport from "../hooks/useViewport.js";

// /bridge (More → Bridge): USDC moving in and out of Hyperliquid through its Arbitrum bridge.
// It used to sit in the scanner's "Market context" row; it answers its own question here.
export default function BridgePage({ style }) {
  const { isMobile } = useViewport();
  return (
    <FadeIn delay={150} style={style}>
      <section className="bridge-page">
        <p className="bridge-lead">
          Is money arriving on Hyperliquid or leaving it? This is the USDC crossing its bridge from Arbitrum.
          Inflow is traders adding margin; outflow is traders taking it home.
        </p>
        <BridgeFlowWidget isMobile={isMobile} detail
          fallback={<p className="bridge-lead">Bridge flows are not available right now.</p>} />
      </section>
    </FadeIn>
  );
}
