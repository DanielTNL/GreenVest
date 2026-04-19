Native iOS client work now lives under [ui/ios](/Users/daniellobo/Documents/Playground/GreenVest/ui/ios).

Generate the Xcode project with:

```bash
cd /Users/daniellobo/Documents/Playground/GreenVest/ui/ios
xcodegen generate
```

Open the generated project at [GreenVest.xcodeproj](/Users/daniellobo/Documents/Playground/GreenVest/ui/ios/GreenVest.xcodeproj).

Cloud-first backend notes:

- The app should point to the public backend URL `https://greenvest-api.fly.dev/api`.
- The GitHub-managed bootstrap file lives at `ui/ios/backend-config.json` and should stay aligned with the deployed Fly app.
- For local debugging only, you can still run `python3 scripts/run_local_api.py --host 127.0.0.1 --port 8000`, but that is no longer the intended iPhone workflow.
- Runtime provider secrets should be managed in GitHub Actions secrets and synced into the cloud host during deployment, not entered on the phone.

The `GreenVest` SwiftUI app includes:

- Stocks & Baskets
- Simulations
- Predictions & Metrics
- Macro & Geopolitics
- Alerts & Settings
- Floating chat assistant sheet
