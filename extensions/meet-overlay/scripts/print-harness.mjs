console.log(`Local overlay harness (no Google Meet required)

1. Build:  npm run build
2. Chrome → chrome://extensions → Load unpacked → extensions/meet-overlay/dist
3. Either:
   • Click the extension toolbar icon on any non-Meet tab → opens harness.html
   • Or open: chrome-extension://<YOUR_EXTENSION_ID>/harness.html

Demo Simulation works with no API.
Offline Analysis needs FastAPI on 127.0.0.1:8765 + allowlisted extension ID.
`);