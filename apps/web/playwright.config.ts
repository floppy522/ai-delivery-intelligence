import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:5173", viewport: { width: 1440, height: 1000 } },
  webServer: [
    { command: "ADI_ROOT=../.. uv run --project ../api uvicorn adi.main:app --host 127.0.0.1 --port 8000", port: 8000, reuseExistingServer: true },
    { command: "npm run dev -- --host 127.0.0.1", port: 5173, reuseExistingServer: true },
  ],
});
