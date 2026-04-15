Native iOS client work now lives under [ui/ios](/Users/daniellobo/Documents/Playground/ai_investment_backend/ui/ios).

Generate the Xcode project with:

```bash
cd /Users/daniellobo/Documents/Playground/ai_investment_backend/ui/ios
xcodegen generate
```

Open the generated project at [GreenVest.xcodeproj](/Users/daniellobo/Documents/Playground/ai_investment_backend/ui/ios/GreenVest.xcodeproj).

Cloud-first backend notes:

- The app should point to a public backend URL such as `https://<your-fly-app-name>.fly.dev/api`.
- The default app placeholder is `https://greenvest-api-replace-me.fly.dev/api` until you replace it with your real deployed backend URL.
- For local debugging only, you can still run `python3 scripts/run_local_api.py --host 127.0.0.1 --port 8000`, but that is no longer the intended iPhone workflow.
- Runtime provider secrets should be managed in GitHub Actions secrets and synced into the cloud host during deployment, not entered on the phone.

The `GreenVest` SwiftUI app includes:

- Stocks & Baskets
- Simulations
- Predictions & Metrics
- Macro & Geopolitics
- Alerts & Settings
- Floating chat assistant sheet
