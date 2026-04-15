import Combine
import Foundation
import Security
import UserNotifications

enum AppSettingsKeys {
    static let backendBaseURL = "backend_base_url"
    static let updateFrequency = "update_frequency"
    static let mathAgentEnabled = "math_agent_enabled"
    static let opsAgentEnabled = "ops_agent_enabled"
    static let notificationsEnabled = "notifications_enabled"
    static let legacySimulatorBackendURLString = "http://127.0.0.1:8000/api"
    static let legacyDeviceBackendURLString = "http://192.168.8.25:8000/api"
    static let cloudBackendURLString = "https://greenvest-api-replace-me.fly.dev/api"

    static var defaultBackendURLString: String {
        cloudBackendURLString
    }

    static func isLegacyLocalURL(_ value: String?) -> Bool {
        guard let value else { return false }
        return value == legacySimulatorBackendURLString || value == legacyDeviceBackendURLString
    }
}

enum UpdateFrequency: String, CaseIterable, Identifiable {
    case hourly
    case daily
    case weekly

    var id: String { rawValue }
    var title: String { rawValue.capitalized }
}

@MainActor
final class AppSettingsStore: ObservableObject {
    @Published var backendBaseURL: String {
        didSet { defaults.set(backendBaseURL, forKey: AppSettingsKeys.backendBaseURL) }
    }
    @Published var updateFrequency: UpdateFrequency {
        didSet { defaults.set(updateFrequency.rawValue, forKey: AppSettingsKeys.updateFrequency) }
    }
    @Published var mathAgentEnabled: Bool {
        didSet { defaults.set(mathAgentEnabled, forKey: AppSettingsKeys.mathAgentEnabled) }
    }
    @Published var opsAgentEnabled: Bool {
        didSet { defaults.set(opsAgentEnabled, forKey: AppSettingsKeys.opsAgentEnabled) }
    }
    @Published var notificationsEnabled: Bool {
        didSet { defaults.set(notificationsEnabled, forKey: AppSettingsKeys.notificationsEnabled) }
    }

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        let storedBackendURL = defaults.string(forKey: AppSettingsKeys.backendBaseURL)
        if AppSettingsKeys.isLegacyLocalURL(storedBackendURL) {
            backendBaseURL = AppSettingsKeys.defaultBackendURLString
        } else {
            backendBaseURL = storedBackendURL ?? AppSettingsKeys.defaultBackendURLString
        }
        updateFrequency = UpdateFrequency(rawValue: defaults.string(forKey: AppSettingsKeys.updateFrequency) ?? "daily") ?? .daily
        mathAgentEnabled = defaults.object(forKey: AppSettingsKeys.mathAgentEnabled) as? Bool ?? true
        opsAgentEnabled = defaults.object(forKey: AppSettingsKeys.opsAgentEnabled) as? Bool ?? true
        notificationsEnabled = defaults.object(forKey: AppSettingsKeys.notificationsEnabled) as? Bool ?? true
    }
}

final class KeychainStore {
    func set(_ value: String, for key: String) {
        let data = Data(value.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data
        ]
        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }

    func string(for key: String) -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: AnyObject?
        SecItemCopyMatching(query as CFDictionary, &result)
        guard let data = result as? Data, let string = String(data: data, encoding: .utf8) else {
            return ""
        }
        return string
    }
}

@MainActor
final class NotificationManager: ObservableObject {
    @Published private(set) var authorizationStatus: UNAuthorizationStatus = .notDetermined

    func configureIfNeeded(enabled: Bool) async {
        await refreshStatus()
        guard enabled, authorizationStatus == .notDetermined else { return }
        _ = try? await requestAuthorization()
    }

    func refreshStatus() async {
        authorizationStatus = await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                continuation.resume(returning: settings.authorizationStatus)
            }
        }
    }

    func requestAuthorization() async throws -> Bool {
        registerCategories()
        let granted = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Bool, Error>) in
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume(returning: granted)
                }
            }
        }
        await refreshStatus()
        return granted
    }

    func scheduleSimulationNotification(name: String, summary: String) async {
        guard authorizationStatus == .authorized || authorizationStatus == .provisional else { return }
        let content = UNMutableNotificationContent()
        content.title = "Simulation Completed"
        content.body = "\(name): \(summary)"
        content.sound = .default
        content.categoryIdentifier = "SIMULATION_COMPLETE"
        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
        )
        try? await UNUserNotificationCenter.current().add(request)
    }

    func scheduleAlertNotification(title: String, body: String) async {
        guard authorizationStatus == .authorized || authorizationStatus == .provisional else { return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        content.categoryIdentifier = "SYSTEM_ALERT"
        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
        )
        try? await UNUserNotificationCenter.current().add(request)
    }

    private func registerCategories() {
        let action = UNNotificationAction(identifier: "VIEW_SIMULATION_RESULT", title: "View Simulation Result")
        let simulationCategory = UNNotificationCategory(
            identifier: "SIMULATION_COMPLETE",
            actions: [action],
            intentIdentifiers: []
        )
        let alertCategory = UNNotificationCategory(identifier: "SYSTEM_ALERT", actions: [], intentIdentifiers: [])
        UNUserNotificationCenter.current().setNotificationCategories([simulationCategory, alertCategory])
    }
}
