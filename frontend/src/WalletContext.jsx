import { useState, useCallback, useEffect, useRef } from "react";
import { createWalletClient, custom } from "viem";
import { arbitrum } from "viem/chains";
import { WalletContext, useWallet } from "./walletContextCore.js";

export { useWallet };

const STORAGE_KEY = "rcce-wallet-address";
// An address to look at without connecting (read-only): Portfolio, the Radar's My trades
// and the coin page read it when no wallet is connected.
const VIEW_KEY = "rcce-view-address";
const LEGACY_VIEW_KEY = "smap-address";   // the Radar's own address box, before this
const ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;

function initialViewAddress() {
  try {
    const saved = localStorage.getItem(VIEW_KEY);
    if (saved != null) return ADDRESS_RE.test(saved) ? saved.toLowerCase() : "";
    // First load: take over a valid address typed into the Radar's box.
    const legacy = (localStorage.getItem(LEGACY_VIEW_KEY) || "").trim();
    if (ADDRESS_RE.test(legacy)) {
      localStorage.setItem(VIEW_KEY, legacy.toLowerCase());
      return legacy.toLowerCase();
    }
  } catch { /* storage blocked */ }
  return "";
}

export function WalletProvider({ children }) {
  const [address, setAddress] = useState(null);
  const [error, setError] = useState(null);
  const [viewAddress, setViewState] = useState(initialViewAddress);
  const walletClientRef = useRef(null);

  const hasProvider = typeof window !== "undefined" && !!window.ethereum;

  const buildClient = useCallback(() => {
    if (!window.ethereum) return null;
    const client = createWalletClient({
      chain: arbitrum,
      transport: custom(window.ethereum),
    });
    walletClientRef.current = client;
    return client;
  }, []);

  // Auto-reconnect from localStorage (silent — no popup)
  useEffect(() => {
    if (!hasProvider) return;
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return;

    window.ethereum
      .request({ method: "eth_accounts" })
      .then((accounts) => {
        const match = accounts.find((a) => a.toLowerCase() === saved.toLowerCase());
        if (match) {
          setAddress(match.toLowerCase());
          buildClient();
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      })
      .catch(() => localStorage.removeItem(STORAGE_KEY));
  }, [hasProvider, buildClient]);

  // Listen for account/chain changes
  useEffect(() => {
    if (!hasProvider) return;
    const onAccountsChanged = (accounts) => {
      if (accounts.length === 0) {
        setAddress(null);
        walletClientRef.current = null;
        localStorage.removeItem(STORAGE_KEY);
      } else {
        const addr = accounts[0].toLowerCase();
        setAddress(addr);
        localStorage.setItem(STORAGE_KEY, addr);
        buildClient();
      }
    };
    const onChainChanged = () => {
      if (address) buildClient();
    };
    window.ethereum.on("accountsChanged", onAccountsChanged);
    window.ethereum.on("chainChanged", onChainChanged);
    return () => {
      window.ethereum.removeListener("accountsChanged", onAccountsChanged);
      window.ethereum.removeListener("chainChanged", onChainChanged);
    };
  }, [hasProvider, address, buildClient]);

  const connect = useCallback(async () => {
    setError(null);
    if (!hasProvider) {
      setError("No wallet detected. Install MetaMask or Rabby.");
      return;
    }
    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      if (accounts.length === 0) {
        setError("No accounts returned.");
        return;
      }
      const addr = accounts[0].toLowerCase();
      setAddress(addr);
      localStorage.setItem(STORAGE_KEY, addr);
      buildClient();
    } catch (err) {
      if (err.code === 4001) {
        setError("Connection rejected.");
      } else {
        setError(err.message || "Wallet connection failed.");
      }
    }
  }, [hasProvider, buildClient]);

  // A valid address or "" (stop viewing). Returns whether it was accepted.
  const setViewAddress = useCallback((value) => {
    // Lowercase: one address, one cache key and one banner spelling however it was typed.
    const v = String(value ?? "").trim().toLowerCase();
    if (v && !ADDRESS_RE.test(v)) return false;
    setViewState(v);
    try { localStorage.setItem(VIEW_KEY, v); } catch { /* storage blocked */ }
    return true;
  }, []);

  const disconnect = useCallback(() => {
    setAddress(null);
    walletClientRef.current = null;
    localStorage.removeItem(STORAGE_KEY);
    setError(null);
  }, []);

  return (
    <WalletContext.Provider
      value={{
        address,
        isConnected: !!address,
        walletClient: walletClientRef.current,
        connect,
        disconnect,
        error,
        viewAddress,
        setViewAddress,
        effectiveAddress: address || viewAddress || null,
        readOnly: !address && !!viewAddress,
      }}
    >
      {children}
    </WalletContext.Provider>
  );
}
