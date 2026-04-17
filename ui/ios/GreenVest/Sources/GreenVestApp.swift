import SwiftUI

@main
struct GreenVestApp: App {
    @StateObject private var settingsStore = AppSettingsStore()
    @StateObject private var notificationManager = NotificationManager()

    private let backend: any BackendServing
    private let keychainStore = KeychainStore()

    init() {
        if ProcessInfo.processInfo.arguments.contains("UI_TEST_MODE") {
            backend = PreviewBackendService()
        } else {
            backend = BackendAPIClient()
        }
    }

    var body: some Scene {
        WindowGroup {
            RootTabView(
                backend: backend,
                settingsStore: settingsStore,
                notificationManager: notificationManager,
                keychainStore: keychainStore
            )
            .task {
                await settingsStore.refreshBackendConfigurationIfNeeded()
            }
            .task(id: settingsStore.notificationsEnabled) {
                await notificationManager.configureIfNeeded(enabled: settingsStore.notificationsEnabled)
            }
        }
    }
}
