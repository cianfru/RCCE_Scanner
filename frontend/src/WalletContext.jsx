import { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { createWalletClient, custom } from "viem";
import { arbitrum } from "viem/chains";

const WalletContext = createContext({
  address: null,
  isConnected: false,
  walletClient: null,
  connect: async () => {},
  disconnect: () => {},
  error: null,
});

const STORAGE_KEY = "rcce-wallet-address";

export function WalletProvider({ children }) {
  const [address, setAddress] = useState(null);
  const [error, setError] = useState(null);
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
      }}
    >
      {children}
    </WalletContext.Provider>
  );
}

export function useWallet() {
  return useContext(WalletContext);
}
