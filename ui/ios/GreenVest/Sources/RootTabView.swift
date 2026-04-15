import SwiftUI

struct RootTabView: View {
    let backend: any BackendServing
    @ObservedObject var settingsStore: AppSettingsStore
    @ObservedObject var notificationManager: NotificationManager
    let keychainStore: KeychainStore

    @State private var isChatPresented = false

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                TabView {
                    StocksBasketsScreen(backend: backend)
                        .tabItem { Label("Stocks", systemImage: "chart.line.uptrend.xyaxis") }
                        .accessibilityIdentifier("tab_stocks")

                    SimulationsScreen(backend: backend, notificationManager: notificationManager)
                        .tabItem { Label("Simulations", systemImage: "waveform.path.ecg.rectangle") }
                        .accessibilityIdentifier("tab_simulations")

                    MetricsScreen(backend: backend)
                        .tabItem { Label("Metrics", systemImage: "chart.bar.doc.horizontal") }
                        .accessibilityIdentifier("tab_metrics")

                    MacroGeopoliticsScreen(backend: backend)
                        .tabItem { Label("Macro", systemImage: "globe.europe.africa.fill") }
                        .accessibilityIdentifier("tab_macro")

                    AlertsSettingsScreen(
                        backend: backend,
                        settingsStore: settingsStore,
                        notificationManager: notificationManager,
                        keychainStore: keychainStore
                    )
                    .tabItem { Label("Alerts", systemImage: "bell.badge") }
                    .accessibilityIdentifier("tab_alerts")
                }
                .tint(.gvAccent)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.gvBackground.ignoresSafeArea())

                if !isChatPresented {
                    VStack {
                        Spacer()
                        HStack {
                            Spacer()
                            FloatingChatButton {
                                isChatPresented = true
                            }
                        }
                    }
                    .padding(.horizontal, 18)
                    .padding(.bottom, max(88, proxy.safeAreaInsets.bottom + 66))
                    .transition(.move(edge: .trailing).combined(with: .opacity))
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.gvBackground.ignoresSafeArea())
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.gvBackground.ignoresSafeArea())
        .animation(.spring(response: 0.28, dampingFraction: 0.9), value: isChatPresented)
        .fullScreenCover(isPresented: $isChatPresented) {
            ChatAssistantScreen(backend: backend)
        }
    }
}
