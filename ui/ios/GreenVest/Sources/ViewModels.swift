import Foundation
import SwiftUI

@MainActor
final class StocksViewModel: ObservableObject {
    @Published var searchText = ""
    @Published private(set) var stocks: [StockSummary] = []
    @Published private(set) var searchResults: [StockSearchCandidate] = []
    @Published private(set) var suggestions: [WatchSuggestion] = []
    @Published private(set) var baskets: [BasketSummary] = []
    @Published private(set) var isLoading = false
    @Published private(set) var isSearching = false
    @Published private(set) var isTracking = false
    @Published var errorMessage: String?

    private let backend: any BackendServing

    init(backend: any BackendServing) {
        self.backend = backend
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let stocksTask = backend.fetchStocks(query: nil)
            async let basketsTask = backend.fetchBaskets()
            async let suggestionsTask = backend.fetchDailySuggestions()
            stocks = try await stocksTask
            baskets = try await basketsTask
            suggestions = try await suggestionsTask
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func searchCatalog() async {
        let trimmed = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            searchResults = []
            return
        }
        isSearching = true
        defer { isSearching = false }
        do {
            searchResults = try await backend.searchStockCatalog(query: trimmed)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
            searchResults = []
        }
    }

    func track(_ candidate: StockSearchCandidate) async {
        isTracking = true
        defer { isTracking = false }
        do {
            _ = try await backend.trackStock(symbol: candidate.symbol, name: candidate.name, exchange: candidate.exchange)
            searchText = ""
            searchResults = []
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
final class StockDetailViewModel: ObservableObject {
    @Published private(set) var detail: StockDetailResponse?
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    private let backend: any BackendServing
    let symbol: String

    init(backend: any BackendServing, symbol: String) {
        self.backend = backend
        self.symbol = symbol
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            detail = try await backend.fetchStockDetail(symbol: symbol)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
final class BasketDetailViewModel: ObservableObject {
    @Published private(set) var detail: BasketDetailResponse?
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    private let backend: any BackendServing
    let basketID: Int

    init(backend: any BackendServing, basketID: Int) {
        self.backend = backend
        self.basketID = basketID
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            detail = try await backend.fetchBasketDetail(basketID: basketID)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
final class SimulationViewModel: ObservableObject {
    @Published var runType: SimulationRunType = .past
    @Published var assetKind: SimulationAssetKind = .stock
    @Published var selectedStockSymbol = ""
    @Published var selectedBasketID: Int?
    @Published var horizon: SimulationHorizon = .weekly
    @Published var initialCapital = "10000"
    @Published var startDate = Calendar.current.date(byAdding: .month, value: -6, to: .now) ?? .now
    @Published var endDate = Date.now
    @Published private(set) var stocks: [StockSummary] = []
    @Published private(set) var baskets: [BasketSummary] = []
    @Published private(set) var recentSimulations: [SimulationRecord] = []
    @Published private(set) var simulationResult: SimulationResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var isRunning = false
    @Published var errorMessage: String?

    private let backend: any BackendServing

    init(backend: any BackendServing) {
        self.backend = backend
        syncDatesForRunType()
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let optionsTask = backend.fetchSimulationOptions()
            async let simulationsTask = backend.fetchRecentSimulations()
            let options = try await optionsTask
            stocks = options.stocks
            baskets = options.baskets
            if selectedStockSymbol.isEmpty { selectedStockSymbol = stocks.first?.symbol ?? "" }
            if selectedBasketID == nil { selectedBasketID = baskets.first?.basketId }
            recentSimulations = try await simulationsTask
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runSimulation(notificationManager: NotificationManager) async {
        guard let request = buildRequest() else {
            errorMessage = "Choose a stock or basket before running a simulation."
            return
        }
        isRunning = true
        defer { isRunning = false }
        do {
            let result = try await backend.runSimulation(request: request)
            simulationResult = result
            recentSimulations = try await backend.fetchRecentSimulations()
            errorMessage = nil
            let summaryModel = result.models.first(where: { $0.modelKey == "updated_working_model" }) ?? result.models.first
            await notificationManager.scheduleSimulationNotification(
                name: selectedAssetLabel,
                summary: {
                    guard let summaryModel else { return "Simulation completed." }
                    if let actual = summaryModel.actualReturn {
                        return "Predicted \(summaryModel.predictedReturn?.percentString ?? "n/a"), actual \(actual.percentString)"
                    }
                    return "Stored future forecast of \(summaryModel.predictedReturn?.percentString ?? "n/a")."
                }()
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteSimulation(_ simulation: SimulationRecord) async {
        do {
            try await backend.deleteSimulation(simulationID: simulation.simID)
            recentSimulations.removeAll { $0.simID == simulation.simID }
            if simulationResult?.simulationID == simulation.simID {
                simulationResult = nil
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func syncDatesForRunType() {
        switch runType {
        case .past:
            if endDate > .now {
                endDate = .now
            }
            if startDate >= endDate {
                startDate = Calendar.current.date(byAdding: .month, value: -6, to: endDate) ?? .now
            }
        case .future:
            let futureStart = max(.now, startDate)
            startDate = futureStart
            if endDate <= startDate {
                endDate = Calendar.current.date(byAdding: .month, value: 1, to: startDate) ?? startDate
            }
        }
    }

    var visibleRecentSimulations: [SimulationRecord] {
        recentSimulations.filter { simulation in
            switch runType {
            case .past:
                return (simulation.simulationType ?? "past") == "past"
            case .future:
                return (simulation.simulationType ?? "future") == "future"
            }
        }
    }

    var selectedAssetLabel: String {
        switch assetKind {
        case .stock:
            return selectedStockSymbol
        case .basket:
            return baskets.first(where: { $0.basketId == selectedBasketID })?.name ?? "Basket"
        }
    }

    private func buildRequest() -> SimulationRequest? {
        let identifier: String
        switch assetKind {
        case .stock:
            guard !selectedStockSymbol.isEmpty else { return nil }
            identifier = selectedStockSymbol
        case .basket:
            guard let selectedBasketID else { return nil }
            identifier = String(selectedBasketID)
        }
        return SimulationRequest(
            assetKind: assetKind.rawValue,
            assetIdentifier: identifier,
            simulationType: runType.rawValue,
            horizonUnit: horizon.rawValue,
            modelName: "working_model",
            initialCapital: Double(initialCapital) ?? 10000,
            startDate: Self.dateFormatter.string(from: startDate),
            endDate: Self.dateFormatter.string(from: endDate)
        )
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

@MainActor
final class MetricsViewModel: ObservableObject {
    @Published var knowledgeBase: KnowledgeBaseMode = .working
    @Published private(set) var dashboard: MetricsDashboardResponse?
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    private let backend: any BackendServing

    init(backend: any BackendServing) {
        self.backend = backend
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            dashboard = try await backend.fetchMetrics(knowledgeBase: knowledgeBase)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
final class MacroViewModel: ObservableObject {
    @Published private(set) var macroOverview: MacroOverviewResponse?
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    private let backend: any BackendServing

    init(backend: any BackendServing) {
        self.backend = backend
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            macroOverview = try await backend.fetchMacroOverview()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

@MainActor
final class AlertsSettingsViewModel: ObservableObject {
    @Published private(set) var alertsResponse: AlertsResponse?
    @Published private(set) var health: HealthResponse?
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    private let backend: any BackendServing

    init(backend: any BackendServing) {
        self.backend = backend
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let alertsTask = backend.fetchAlerts()
            async let healthTask = backend.fetchHealth()
            alertsResponse = try await alertsTask
            health = try await healthTask
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runManualAudit(notificationManager: NotificationManager) async {
        do {
            let response = try await backend.runManualAudit()
            let warnings = response.items.filter { $0.status != "ok" }
            if let firstWarning = warnings.first {
                await notificationManager.scheduleAlertNotification(
                    title: "Manual Audit Completed",
                    body: firstWarning.message ?? "A warning needs attention."
                )
            }
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ChatMessage: Identifiable, Hashable {
    enum Role {
        case user
        case assistant
    }

    let id = UUID()
    let role: Role
    let text: String
    let actions: [ChatAction]
}

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var inputText = ""
    @Published private(set) var messages: [ChatMessage] = [
        ChatMessage(
            role: .assistant,
            text: "Ask for volatility, basket creation, simulations, or risk metrics in Dutch or English.",
            actions: [
                ChatAction(title: "Show AAPL volatility", prompt: "Show me today's volatility for Apple"),
                ChatAction(title: "Create tech basket", prompt: "Create a tech basket with Apple, Microsoft and Google at equal weights")
            ]
        )
    ]
    @Published private(set) var isSending = false
    @Published var errorMessage: String?

    private let backend: any BackendServing

    init(backend: any BackendServing) {
        self.backend = backend
    }

    func sendCurrentMessage() async {
        let trimmed = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        inputText = ""
        await send(message: trimmed)
    }

    func send(message: String) async {
        messages.append(ChatMessage(role: .user, text: message, actions: []))
        isSending = true
        errorMessage = nil
        defer { isSending = false }
        do {
            let response = try await backend.sendChat(message: message)
            messages.append(ChatMessage(role: .assistant, text: response.reply, actions: response.actions))
            errorMessage = nil
        } catch {
            let fallbackReply = "I couldn't finish that request right now. \(error.localizedDescription)"
            messages.append(ChatMessage(role: .assistant, text: fallbackReply, actions: []))
            errorMessage = error.localizedDescription
        }
    }
}
