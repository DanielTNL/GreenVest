import SwiftUI

struct AlertsSettingsScreen: View {
    @StateObject private var viewModel: AlertsSettingsViewModel
    @ObservedObject var settingsStore: AppSettingsStore
    @ObservedObject var notificationManager: NotificationManager
    let keychainStore: KeychainStore

    @State private var alphaKey = ""
    @State private var fmpKey = ""
    @State private var eodhdKey = ""
    @State private var fredKey = ""
    @State private var didLoadKeys = false
    @FocusState private var focusedField: SettingsField?

    init(
        backend: any BackendServing,
        settingsStore: AppSettingsStore,
        notificationManager: NotificationManager,
        keychainStore: KeychainStore
    ) {
        _viewModel = StateObject(wrappedValue: AlertsSettingsViewModel(backend: backend))
        self.settingsStore = settingsStore
        self.notificationManager = notificationManager
        self.keychainStore = keychainStore
    }

    var body: some View {
        NavigationStack {
            ScreenContainer {
                ScrollView {
                    VStack(spacing: 16) {
                        if let errorMessage = viewModel.errorMessage {
                            ErrorBanner(message: errorMessage)
                        }
                        ContentCard(title: "System Alerts") {
                            if let alerts = viewModel.alertsResponse?.items, !alerts.isEmpty {
                                ForEach(alerts.prefix(8)) { alert in
                                    VStack(alignment: .leading, spacing: 6) {
                                        HStack {
                                            Text(alert.title)
                                                .font(.headline)
                                            Spacer()
                                            Text(alert.level.uppercased())
                                                .font(.caption2)
                                                .foregroundStyle(alert.level == "warning" ? .orange : .secondary)
                                        }
                                        Text(alert.message)
                                            .font(.footnote)
                                            .foregroundStyle(.secondary)
                                        Text(AppDateParser.shortDate.string(from: alert.dateValue))
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                    .padding(.vertical, 6)
                                }
                            } else {
                                EmptyStateView(title: "No Active Alerts", message: "Math and Ops alerts will appear here after audits and scheduled jobs run.")
                            }
                        }

                        if let systemStatus = viewModel.alertsResponse?.systemStatus {
                            ContentCard(title: "Backend Status") {
                                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                                    InfoChip(title: "Stocks", value: "\(systemStatus.stockCount)")
                                    InfoChip(title: "Baskets", value: "\(systemStatus.basketCount)")
                                    InfoChip(title: "Forecasts", value: "\(systemStatus.forecastCount)")
                                    InfoChip(title: "Runs", value: "\(systemStatus.simulationCount)")
                                }
                            }
                        }

                        ContentCard(title: "Settings") {
                            TextField("Cloud Backend URL", text: $settingsStore.backendBaseURL)
                                .textFieldStyle(.roundedBorder)
                                .textInputAutocapitalization(.never)
                                .keyboardType(.URL)
                                .focused($focusedField, equals: .backendURL)
                                .accessibilityIdentifier("backend_url_field")

                            Button("Sync Backend From GitHub") {
                                Task { await settingsStore.refreshBackendConfigurationIfNeeded(force: true) }
                            }
                            .buttonStyle(.bordered)

                            Picker("Update Frequency", selection: $settingsStore.updateFrequency) {
                                ForEach(UpdateFrequency.allCases) { frequency in
                                    Text(frequency.title).tag(frequency)
                                }
                            }

                            Toggle("Enable Math Agent", isOn: $settingsStore.mathAgentEnabled)
                            Toggle("Enable Ops Agent", isOn: $settingsStore.opsAgentEnabled)
                            Toggle("Enable Notifications", isOn: $settingsStore.notificationsEnabled)

                            HStack {
                                Button("Request Notifications") {
                                    Task { _ = try? await notificationManager.requestAuthorization() }
                                }
                                .buttonStyle(.bordered)

                                Button("Run Manual Audit") {
                                    Task { await viewModel.runManualAudit(notificationManager: notificationManager) }
                                }
                                .buttonStyle(.borderedProminent)
                                .tint(.gvAccent)
                            }

                            Text("Use your public backend URL here, for example `https://greenvest-api.fly.dev/api`. If this field is still a placeholder, the app will try to sync it from `ui/ios/backend-config.json` in the GitHub repo first.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }

                        ContentCard(title: "GitHub-Managed Secrets") {
                            Text("Runtime API keys should live in GitHub Actions secrets and be pushed into your cloud host during deployment. The iPhone app should not be the source of truth for provider keys, and the backend URL should be synced from GitHub config or your deployed cloud URL.")
                                .foregroundStyle(.secondary)
                            VStack(alignment: .leading, spacing: 6) {
                                Text("GitHub backend config")
                                    .font(.subheadline.weight(.semibold))
                                Text("`ui/ios/backend-config.json`")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                Text("Required GitHub secrets")
                                    .font(.subheadline.weight(.semibold))
                                Text("`FLY_API_TOKEN`, `ALPHAVANTAGE_API_KEY`, `FMP_API_KEY`, `EODHD_API_KEY`, `FRED_API_KEY`, `OPENAI_API_KEY`")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                Text("Required GitHub variable")
                                    .font(.subheadline.weight(.semibold))
                                Text("`FLY_APP_NAME`")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                Text("Optional GitHub secrets")
                                    .font(.subheadline.weight(.semibold))
                                Text("`OPENAI_MODEL`, `GEOPOLITICAL_RISK_FRED_SERIES_ID`, `GEOPOLITICAL_RISK_SERIES_NAME`")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding()
                }
                .contentShape(Rectangle())
                .onTapGesture {
                    focusedField = nil
                }
            }
            .navigationTitle("Alerts & Settings")
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") {
                        focusedField = nil
                    }
                }
            }
            .task {
                if !didLoadKeys {
                    alphaKey = keychainStore.string(for: "ALPHAVANTAGE_API_KEY")
                    fmpKey = keychainStore.string(for: "FMP_API_KEY")
                    eodhdKey = keychainStore.string(for: "EODHD_API_KEY")
                    fredKey = keychainStore.string(for: "FRED_API_KEY")
                    didLoadKeys = true
                }
                await viewModel.load()
            }
        }
    }
}

private enum SettingsField: Hashable {
    case backendURL
}
