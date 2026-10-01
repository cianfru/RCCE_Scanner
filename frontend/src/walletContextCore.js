// The wallet context object and its hook, without the wallet client library, so a
// component that only reads the wallet (the scanner table, also on the landing)
// does not pull the client into its bundle. WalletContext.jsx provides the value.
import { createContext, useContext } from "react";

export const WalletContext = createContext({
  address: null,
  isConnected: false,
  walletClient: null,
  connect: async () => {},
  disconnect: () => {},
  error: null,
  viewAddress: "",
  setViewAddress: () => false,
  effectiveAddress: null,
  readOnly: false,
});

export function useWallet() {
  return useContext(WalletContext);
}
