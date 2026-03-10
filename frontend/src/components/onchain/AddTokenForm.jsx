import { useState } from "react";
import { S, CHAIN_META } from "./styles.js";

export default function AddTokenForm({ onAdd }) {
  const [chain, setChain] = useState("ethereum");
  const [contract, setContract] = useState("");
  const [adding, setAdding] = useState(false);

  const handleAdd = async () => {
    if (!contract.trim()) return;
    setAdding(true);
    try {
      await onAdd(chain, contract.trim());
      setContract("");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        flexWrap: "wrap",
        marginBottom: 16,
      }}
    >
      <select
        value={chain}
        onChange={(e) => setChain(e.target.value)}
        style={{ ...S.select, width: 100 }}
      >
        {Object.entries(CHAIN_META).map(([k, v]) => (
          <option key={k} value={k}>
            {v.label}
          </option>
        ))}
      </select>
      <input
        value={contract}
        onChange={(e) => setContract(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        placeholder="Paste token contract address..."
        style={S.input}
      />
      <button
        onClick={handleAdd}
        disabled={adding || !contract.trim()}
        style={{
          ...S.btn,
          opacity: adding || !contract.trim() ? 0.5 : 1,
        }}
      >
        {adding ? "Adding..." : "Track"}
      </button>
    </div>
  );
}
