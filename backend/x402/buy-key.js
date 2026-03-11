#!/usr/bin/env node
/**
 * AIXBT x402 API Key Purchaser
 *
 * Buys a 1-day AIXBT API key ($0.10 USDC on Base) via x402 protocol.
 * Saves the key to ../data/aixbt_key.json for the Python backend to read.
 *
 * Usage:
 *   node buy-key.js                    # Buy 1-day key (default)
 *   node buy-key.js 7d                 # Buy 7-day key
 *   node buy-key.js --generate-wallet  # Generate a new wallet
 *
 * Environment:
 *   AIXBT_WALLET_KEY — Private key for Base wallet with USDC
 */

import { writeFileSync, mkdirSync, existsSync, readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, "..", "data");
const KEY_FILE = join(DATA_DIR, "aixbt_key.json");

// Duration options and their endpoints
const DURATIONS = {
  "1d": { endpoint: "/x402/v2/api-keys/1d", cost: "$0.10" },
  "7d": { endpoint: "/x402/v2/api-keys/7d", cost: "$0.50" },
  "4w": { endpoint: "/x402/v2/api-keys/4w", cost: "$1.50" },
};

async function generateWallet() {
  const { generatePrivateKey, privateKeyToAccount } = await import(
    "viem/accounts"
  );
  const key = generatePrivateKey();
  const account = privateKeyToAccount(key);
  console.log("=== New Base Wallet Generated ===");
  console.log(`Address:     ${account.address}`);
  console.log(`Private Key: ${key}`);
  console.log("");
  console.log("Next steps:");
  console.log("1. Add to backend/.env:  AIXBT_WALLET_KEY=" + key);
  console.log(
    "2. Fund with USDC on Base chain: send at least $0.10 USDC to " +
      account.address
  );
  console.log("3. Run: node buy-key.js");
}

async function buyKey(duration = "1d") {
  const walletKey = process.env.AIXBT_WALLET_KEY;
  if (!walletKey) {
    console.error(
      "Error: AIXBT_WALLET_KEY not set. Run with --generate-wallet first."
    );
    process.exit(1);
  }

  const durConfig = DURATIONS[duration];
  if (!durConfig) {
    console.error(
      `Error: Invalid duration '${duration}'. Options: ${Object.keys(DURATIONS).join(", ")}`
    );
    process.exit(1);
  }

  console.log(
    `Purchasing ${duration} AIXBT API key (${durConfig.cost} USDC on Base)...`
  );

  try {
    // Dynamic imports for x402
    const { wrapFetchWithPayment } = await import("@x402/fetch");
    const { privateKeyToAccount } = await import("viem/accounts");

    const signer = privateKeyToAccount(walletKey);
    console.log(`Wallet: ${signer.address}`);

    // Create x402 payment-wrapped fetch
    const fetchWithPayment = wrapFetchWithPayment(fetch, signer);

    // Purchase the API key
    const url = `https://api.aixbt.tech${durConfig.endpoint}`;
    const response = await fetchWithPayment(url, { method: "POST" });

    if (!response.ok) {
      const text = await response.text();
      console.error(`Purchase failed (${response.status}): ${text}`);
      process.exit(1);
    }

    const result = await response.json();
    const apiKey = result.data?.apiKey || result.apiKey || result.key;

    if (!apiKey) {
      console.error("Purchase succeeded but no API key in response:", result);
      process.exit(1);
    }

    // Calculate expiry
    const now = Date.now();
    const durationMs = {
      "1d": 24 * 60 * 60 * 1000,
      "7d": 7 * 24 * 60 * 60 * 1000,
      "4w": 28 * 24 * 60 * 60 * 1000,
    }[duration];

    const keyData = {
      api_key: apiKey,
      purchased_at: new Date(now).toISOString(),
      expires_at: new Date(now + durationMs).toISOString(),
      expires_ts: now + durationMs,
      duration: duration,
      cost: durConfig.cost,
      wallet: signer.address,
    };

    // Save to data directory
    if (!existsSync(DATA_DIR)) {
      mkdirSync(DATA_DIR, { recursive: true });
    }
    writeFileSync(KEY_FILE, JSON.stringify(keyData, null, 2));

    console.log("=== API Key Purchased ===");
    console.log(`Key:     ${apiKey.substring(0, 12)}...`);
    console.log(`Expires: ${keyData.expires_at}`);
    console.log(`Saved:   ${KEY_FILE}`);
    console.log("");
    console.log("The scanner backend will auto-detect this key on next request.");

    // Also output just the key for scripting
    if (process.argv.includes("--quiet")) {
      process.stdout.write(apiKey);
    }
  } catch (err) {
    if (err.message?.includes("insufficient")) {
      console.error(
        "Error: Insufficient USDC balance. Fund your wallet on Base chain."
      );
    } else {
      console.error("Error:", err.message || err);
    }
    process.exit(1);
  }
}

// CLI
const args = process.argv.slice(2);
if (args.includes("--generate-wallet")) {
  generateWallet();
} else {
  const duration = args.find((a) => DURATIONS[a]) || "1d";
  buyKey(duration);
}
