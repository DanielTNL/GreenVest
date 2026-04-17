import Foundation

protocol BackendServing {
    func fetchHealth() async throws -> HealthResponse
    func fetchStocks(query: String?) async throws -> [StockSummary]
    func searchStockCatalog(query: String) async throws -> [StockSearchCandidate]
    func fetchDailySuggestions() async throws -> [WatchSuggestion]
    func trackStock(symbol: String, name: String?, exchange: String?) async throws -> StockSummary
    func fetchStockDetail(symbol: String) async throws -> StockDetailResponse
    func fetchBaskets() async throws -> [BasketSummary]
    func fetchBasketDetail(basketID: Int) async throws -> BasketDetailResponse
    func createBasket(request: BasketCreateRequest) async throws -> BasketSummary
    func fetchSimulationOptions() async throws -> SimulationOptionsResponse
    func runSimulation(request: SimulationRequest) async throws -> SimulationResponse
    func fetchRecentSimulations() async throws -> [SimulationRecord]
    func deleteSimulation(simulationID: Int) async throws
    func fetchMetrics(knowledgeBase: KnowledgeBaseMode) async throws -> MetricsDashboardResponse
    func fetchMacroOverview() async throws -> MacroOverviewResponse
    func fetchAlerts() async throws -> AlertsResponse
    func runManualAudit() async throws -> AuditRunResponse
    func sendChat(message: String) async throws -> ChatResponse
}

enum NetworkError: LocalizedError {
    case invalidURL
    case invalidResponse
    case server(String)
    case cannotConnect(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "The backend URL is invalid."
        case .invalidResponse:
            return "The backend returned an unexpected response."
        case let .server(message):
            return message
        case let .cannotConnect(message):
            return message
        }
    }
}

private struct EmptyResponse: Codable {}

final class BackendAPIClient: BackendServing {
    private let session: URLSession
    private let baseURLProvider: () -> URL?
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(
        session: URLSession = .shared,
        baseURLProvider: @escaping () -> URL? = {
            URL(string: UserDefaults.standard.string(forKey: AppSettingsKeys.backendBaseURL) ?? AppSettingsKeys.defaultBackendURLString)
        }
    ) {
        self.session = session
        self.baseURLProvider = baseURLProvider
        decoder = JSONDecoder()
        encoder = JSONEncoder()
    }

    func fetchHealth() async throws -> HealthResponse {
        try await get("/health")
    }

    func fetchStocks(query: String?) async throws -> [StockSummary] {
        let response: StockListResponse = try await get(
            "/stocks",
            queryItems: query.map { [URLQueryItem(name: "q", value: $0)] } ?? []
        )
        return response.items
    }

    func searchStockCatalog(query: String) async throws -> [StockSearchCandidate] {
        let response: StockSearchResponse = try await get(
            "/stocks/search",
            queryItems: [URLQueryItem(name: "q", value: query)]
        )
        return response.items
    }

    func fetchDailySuggestions() async throws -> [WatchSuggestion] {
        let response: WatchSuggestionResponse = try await get("/stocks/suggestions")
        return response.items
    }

    func trackStock(symbol: String, name: String?, exchange: String?) async throws -> StockSummary {
        try await post(
            "/stocks/track",
            body: TrackStockRequest(symbol: symbol, name: name, exchange: exchange)
        )
    }

    func fetchStockDetail(symbol: String) async throws -> StockDetailResponse {
        try await get("/stocks/\(symbol)")
    }

    func fetchBaskets() async throws -> [BasketSummary] {
        let response: BasketListResponse = try await get("/baskets")
        return response.items
    }

    func fetchBasketDetail(basketID: Int) async throws -> BasketDetailResponse {
        try await get("/baskets/\(basketID)")
    }

    func createBasket(request: BasketCreateRequest) async throws -> BasketSummary {
        try await post("/baskets", body: request)
    }

    func fetchSimulationOptions() async throws -> SimulationOptionsResponse {
        try await get("/simulation-options")
    }

    func runSimulation(request: SimulationRequest) async throws -> SimulationResponse {
        try await post("/simulations/run", body: request)
    }

    func fetchRecentSimulations() async throws -> [SimulationRecord] {
        let response: SimulationsResponse = try await get("/simulations/recent")
        return response.items
    }

    func deleteSimulation(simulationID: Int) async throws {
        let _: EmptyResponse = try await delete("/simulations/\(simulationID)")
    }

    func fetchMetrics(knowledgeBase: KnowledgeBaseMode) async throws -> MetricsDashboardResponse {
        try await get(
            "/metrics",
            queryItems: [URLQueryItem(name: "knowledge_base", value: knowledgeBase.rawValue)]
        )
    }

    func fetchMacroOverview() async throws -> MacroOverviewResponse {
        try await get("/macro")
    }

    func fetchAlerts() async throws -> AlertsResponse {
        try await get("/alerts")
    }

    func runManualAudit() async throws -> AuditRunResponse {
        try await post("/audit/run", body: ["lookback": 252])
    }

    func sendChat(message: String) async throws -> ChatResponse {
        try await post("/chat", body: ChatRequest(message: message))
    }

    private func get<Response: Decodable>(
        _ path: String,
        queryItems: [URLQueryItem] = []
    ) async throws -> Response {
        var request = try buildRequest(path: path, method: "GET")
        if !queryItems.isEmpty {
            var components = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)
            components?.queryItems = queryItems
            guard let url = components?.url else { throw NetworkError.invalidURL }
            request.url = url
        }
        return try await perform(request)
    }

    private func post<Body: Encodable, Response: Decodable>(
        _ path: String,
        body: Body
    ) async throws -> Response {
        var request = try buildRequest(path: path, method: "POST")
        request.httpBody = try encoder.encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return try await perform(request)
    }

    private func delete<Response: Decodable>(_ path: String) async throws -> Response {
        let request = try buildRequest(path: path, method: "DELETE")
        return try await perform(request)
    }

    private func buildRequest(path: String, method: String) throws -> URLRequest {
        guard let baseURL = baseURLProvider() else { throw NetworkError.invalidURL }
        let trimmedPath = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let url = baseURL.appendingPathComponent(trimmedPath)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        return request
    }

    private func perform<Response: Decodable>(_ request: URLRequest) async throws -> Response {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            if let retryRequest = retryRequestIfNeeded(after: error, original: request) {
                do {
                    let retried = try await session.data(for: retryRequest)
                    return try decodeResponse(data: retried.0, response: retried.1)
                } catch {
                    throw mapNetworkError(error, url: retryRequest.url)
                }
            }
            throw mapNetworkError(error, url: request.url)
        }
        return try decodeResponse(data: data, response: response)
    }

    private func decodeResponse<Response: Decodable>(data: Data, response: URLResponse) throws -> Response {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw NetworkError.invalidResponse
        }
        guard (200 ..< 300).contains(httpResponse.statusCode) else {
            let message = (try? decoder.decode(APIErrorEnvelope.self, from: data).error) ?? "Request failed."
            throw NetworkError.server(message)
        }
        return try decoder.decode(Response.self, from: data)
    }

    private func retryRequestIfNeeded(after error: Error, original request: URLRequest) -> URLRequest? {
        guard let urlError = error as? URLError else { return nil }
        guard [.cannotConnectToHost, .cannotFindHost, .networkConnectionLost, .timedOut].contains(urlError.code) else {
            return nil
        }
        return nil
    }

    private func mapNetworkError(_ error: Error, url: URL?) -> Error {
        guard let urlError = error as? URLError else { return error }
        if AppSettingsKeys.isPlaceholderCloudURL(url?.absoluteString) {
            return NetworkError.cannotConnect(
                "The public backend URL is still a placeholder. Deploy the backend, update `ui/ios/backend-config.json` in GitHub with the real API URL, or enter the deployed URL manually in Settings."
            )
        }
        let host = url?.host ?? "the backend"
        switch urlError.code {
        case .cannotConnectToHost, .cannotFindHost, .networkConnectionLost, .notConnectedToInternet, .timedOut:
            return NetworkError.cannotConnect(
                "Could not connect to the cloud backend at \(host). Check that your public backend URL is correct, that `ui/ios/backend-config.json` in GitHub points to the deployed API, and that the cloud deployment is live."
            )
        default:
            return urlError
        }
    }
}

final class PreviewBackendService: BackendServing {
    func fetchHealth() async throws -> HealthResponse { PreviewData.health }
    func fetchStocks(query: String?) async throws -> [StockSummary] { PreviewData.stocks }
    func searchStockCatalog(query: String) async throws -> [StockSearchCandidate] {
        PreviewData.searchCandidates.filter {
            query.isEmpty || $0.symbol.localizedCaseInsensitiveContains(query) || ($0.name ?? "").localizedCaseInsensitiveContains(query)
        }
    }
    func fetchDailySuggestions() async throws -> [WatchSuggestion] { PreviewData.watchSuggestions }
    func trackStock(symbol: String, name: String?, exchange: String?) async throws -> StockSummary {
        StockSummary(
            symbol: symbol,
            name: name,
            exchange: exchange,
            assetType: "equity",
            source: "preview",
            latestClose: 123.45,
            latestPriceTimestampUTC: "2026-04-15T08:00:00+00:00"
        )
    }
    func fetchStockDetail(symbol: String) async throws -> StockDetailResponse { PreviewData.stockDetail }
    func fetchBaskets() async throws -> [BasketSummary] { PreviewData.baskets }
    func fetchBasketDetail(basketID: Int) async throws -> BasketDetailResponse { PreviewData.basketDetail }
    func createBasket(request: BasketCreateRequest) async throws -> BasketSummary { PreviewData.baskets[0] }
    func fetchSimulationOptions() async throws -> SimulationOptionsResponse { PreviewData.simulationOptions }
    func runSimulation(request: SimulationRequest) async throws -> SimulationResponse { PreviewData.simulationResult }
    func fetchRecentSimulations() async throws -> [SimulationRecord] { PreviewData.simulations }
    func deleteSimulation(simulationID: Int) async throws {}
    func fetchMetrics(knowledgeBase: KnowledgeBaseMode) async throws -> MetricsDashboardResponse {
        PreviewData.metrics(knowledgeBase: knowledgeBase)
    }
    func fetchMacroOverview() async throws -> MacroOverviewResponse { PreviewData.macroOverview }
    func fetchAlerts() async throws -> AlertsResponse { PreviewData.alerts }
    func runManualAudit() async throws -> AuditRunResponse {
        AuditRunResponse(items: [AuditEntry(symbol: "AAPL", status: "ok", message: nil, volatility: 0.24)])
    }
    func sendChat(message: String) async throws -> ChatResponse {
        ChatResponse(
            reply: "Preview mode is active. I can still show how a weekly simulation would look for AAPL.",
            actions: [ChatAction(title: "Run weekly simulation", prompt: "Run a weekly simulation for AAPL")],
            intent: "preview"
        )
    }
}

enum PreviewData {
    static let health = HealthResponse(
        status: "ok",
        systemStatus: SystemStatus(
            stockCount: 12,
            basketCount: 3,
            forecastCount: 18,
            simulationCount: 7,
            lastStockUpdateUTC: "2026-04-14T08:00:00+00:00",
            lastMacroUpdateUTC: "2026-04-13T00:00:00+00:00",
            lastPredictionMarketUpdateUTC: "2026-04-14T08:10:00+00:00",
            lastAuditUTC: "2026-04-14T08:30:00+00:00"
        ),
        truthVersion: "truth-v1",
        workingVersions: ["daily": "daily-preview-1", "weekly": "weekly-preview-1", "monthly": "monthly-preview-1"]
    )

    static let stocks = [
        StockSummary(symbol: "AAPL", name: "Apple Inc.", exchange: "NASDAQ", assetType: "equity", source: "preview", latestClose: 201.42, latestPriceTimestampUTC: "2026-04-14T16:00:00+00:00"),
        StockSummary(symbol: "MSFT", name: "Microsoft", exchange: "NASDAQ", assetType: "equity", source: "preview", latestClose: 428.55, latestPriceTimestampUTC: "2026-04-14T16:00:00+00:00"),
        StockSummary(symbol: "GOOGL", name: "Alphabet", exchange: "NASDAQ", assetType: "equity", source: "preview", latestClose: 175.83, latestPriceTimestampUTC: "2026-04-14T16:00:00+00:00")
    ]

    static let searchCandidates = [
        StockSearchCandidate(symbol: "PLTR", name: "Palantir Technologies", exchange: "NASDAQ", assetType: "equity", source: "fmp_search", latestClose: nil, latestPriceTimestampUTC: nil, isTracked: false),
        StockSearchCandidate(symbol: "PANW", name: "Palo Alto Networks", exchange: "NASDAQ", assetType: "equity", source: "fmp_search", latestClose: nil, latestPriceTimestampUTC: nil, isTracked: false),
        StockSearchCandidate(symbol: "PATH", name: "UiPath", exchange: "NYSE", assetType: "equity", source: "fmp_search", latestClose: nil, latestPriceTimestampUTC: nil, isTracked: false)
    ]

    static let watchSuggestions = [
        WatchSuggestion(suggestionDate: "2026-04-15", symbol: "NVDA", rank: 1, name: "NVIDIA", theme: "AI", rationale: "AI infrastructure leader with strong recent momentum and heavy relevance to your interests.", score: 14.2, latestClose: 912.42, isTracked: false),
        WatchSuggestion(suggestionDate: "2026-04-15", symbol: "PLTR", rank: 2, name: "Palantir", theme: "AI", rationale: "AI software and defense analytics name with persistent thematic relevance.", score: 11.7, latestClose: 28.14, isTracked: false),
        WatchSuggestion(suggestionDate: "2026-04-15", symbol: "SLB", rank: 3, name: "Schlumberger", theme: "Commodity Trading", rationale: "Energy-services bellwether tied to commodity and oil-cycle monitoring.", score: 9.3, latestClose: 52.89, isTracked: false),
        WatchSuggestion(suggestionDate: "2026-04-15", symbol: "XOM", rank: 4, name: "Exxon Mobil", theme: "Energy", rationale: "Large-cap energy anchor for oil and macro regime tracking.", score: 8.9, latestClose: 118.22, isTracked: false),
        WatchSuggestion(suggestionDate: "2026-04-15", symbol: "AVGO", rank: 5, name: "Broadcom", theme: "Semiconductors", rationale: "Semiconductor and infrastructure play with AI-adjacent demand exposure.", score: 8.4, latestClose: 1332.10, isTracked: false),
    ]

    static let riskMetrics = RiskMetrics(
        volatility: 0.24,
        covariance: 0.02,
        correlation: 0.84,
        sharpe: 1.18,
        sortino: 1.41,
        beta: 1.12,
        varParametric: 0.035,
        varHistorical: 0.031,
        varMonteCarlo: 0.036,
        cvar: 0.042,
        maxDrawdown: -0.18
    )

    static let forecast = ForecastSnapshot(
        symbol: "AAPL",
        model: "Truth Model",
        runTimestampUTC: "2026-04-14T08:00:00+00:00",
        horizon: 1,
        horizonUnit: "weekly",
        forecastValue: 0.021,
        lowerBound: -0.012,
        upperBound: 0.046,
        actualValue: 0.017,
        errorValue: 0.004,
        status: "evaluated"
    )

    static let stockDetail = StockDetailResponse(
        stock: StockIdentity(symbol: "AAPL", name: "Apple Inc.", exchange: "NASDAQ", assetType: "equity", source: "preview"),
        latestClose: 201.42,
        dailyChangePercent: 0.008,
        priceHistory: stride(from: 0, to: 20, by: 1).map { index in
            let base = 180.0 + Double(index)
            return PricePoint(
                timestampUTC: "2026-03-\(String(format: "%02d", index + 1))T00:00:00+00:00",
                tradingDate: "2026-03-\(String(format: "%02d", index + 1))",
                open: base,
                high: base + 3,
                low: base - 2,
                close: base + 1,
                volume: 1_000_000 + Double(index * 10_000)
            )
        },
        riskMetrics: riskMetrics,
        latestForecast: forecast
    )

    static let baskets = [
        BasketSummary(
            basketId: 1,
            name: "Tech Basket",
            description: "Equal-weight big tech basket",
            createdAtUTC: "2026-04-14T09:00:00+00:00",
            constituents: [
                BasketConstituent(basketId: 1, symbol: "AAPL", weight: 0.34),
                BasketConstituent(basketId: 1, symbol: "MSFT", weight: 0.33),
                BasketConstituent(basketId: 1, symbol: "GOOGL", weight: 0.33)
            ],
            riskMetrics: riskMetrics
        )
    ]

    static let simulations = [
        SimulationRecord(
            simID: 7,
            basketID: 1,
            portfolioName: "Tech Basket",
            simulationType: "past",
            status: "completed",
            modelsUsed: ["Truth Model", "Working Model", "Updated Working Model"],
            aiAnalysis: "The Updated Working Model handled this run best because it stayed closer to the realised basket move while the Truth Model stayed more conservative.",
            keyOutcomeSummary: "Updated Working Model performed best with a smaller forecast error than the other two models.",
            bestModel: "updated_working_model",
            modelResults: sampleModelResults,
            assetKind: "basket",
            assetIdentifier: "1",
            startDate: "2026-03-01",
            endDate: "2026-04-14",
            horizon: 6,
            horizonUnit: "weekly",
            initialCapital: 10000,
            predictedReturn: 0.022,
            actualReturn: 0.018,
            rmse: 0.004,
            mape: 0.20,
            directionalAccuracy: 1,
            createdAtUTC: "2026-04-14T08:45:00+00:00"
        ),
        SimulationRecord(
            simID: 6,
            basketID: nil,
            portfolioName: "AAPL",
            simulationType: "future",
            status: "awaiting_actual_data",
            modelsUsed: ["Truth Model", "Working Model", "Updated Working Model"],
            aiAnalysis: "This future simulation is stored and waiting for end-of-period data so the three models can be compared properly.",
            keyOutcomeSummary: "Predictions stored; awaiting actual market data.",
            bestModel: nil,
            modelResults: sampleFutureModelResults,
            assetKind: "stock",
            assetIdentifier: "AAPL",
            startDate: "2026-04-15",
            endDate: "2026-05-15",
            horizon: 4,
            horizonUnit: "weekly",
            initialCapital: 10000,
            predictedReturn: 0.018,
            actualReturn: nil,
            rmse: nil,
            mape: nil,
            directionalAccuracy: nil,
            createdAtUTC: "2026-04-15T08:45:00+00:00"
        )
    ]

    static let basketDetail = BasketDetailResponse(
        basket: baskets[0],
        priceHistory: stride(from: 0, to: 16, by: 1).map { index in
            PricePoint(
                timestampUTC: "2026-03-\(String(format: "%02d", index + 1))T00:00:00+00:00",
                tradingDate: "2026-03-\(String(format: "%02d", index + 1))",
                open: nil,
                high: nil,
                low: nil,
                close: 100 + Double(index) * 1.8,
                volume: nil
            )
        },
        riskMetrics: riskMetrics,
        recentSimulations: simulations
    )

    static let simulationOptions = SimulationOptionsResponse(stocks: stocks, baskets: baskets)

    static let simulationResult = SimulationResponse(
        simulationID: 8,
        simulationType: "past",
        status: "completed",
        portfolioName: "Tech Basket",
        assetKind: "basket",
        assetIdentifier: "1",
        startDate: "2026-03-01",
        endDate: "2026-04-14",
        initialInvestment: 10000,
        models: sampleModelResults,
        bestModel: "updated_working_model",
        aiAnalysis: "The Updated Working Model captured the direction and ending value more closely than the other two models in this preview run.",
        keyOutcomeSummary: "Updated Working Model performed best."
    )

    static let sampleModelResults = [
        SimulationModelResult(modelKey: "truth_model", displayName: "Truth Model", forecastModel: "naive", versionID: "truth-v1", explanation: "Static reference model anchored to the knowledge base.", predictedReturn: 0.081, actualReturn: 0.084, predictedEndingValue: 10810, actualEndingValue: 10840, predictedGainLoss: 810, actualGainLoss: 840, absoluteError: 0.003, percentageError: 0.036, directionalAccuracy: 1, status: "completed", rank: 2, latestUpdatedWorkingVersion: "weekly-preview-1", componentPredictions: ["AAPL": 0.08], componentActuals: ["AAPL": 0.084]),
        SimulationModelResult(modelKey: "working_model", displayName: "Working Model", forecastModel: "arima", versionID: "weekly-preview-1", explanation: "Active adaptive model tied to the current working state.", predictedReturn: 0.092, actualReturn: 0.084, predictedEndingValue: 10920, actualEndingValue: 10840, predictedGainLoss: 920, actualGainLoss: 840, absoluteError: 0.008, percentageError: 0.095, directionalAccuracy: 1, status: "completed", rank: 3, latestUpdatedWorkingVersion: "weekly-preview-1", componentPredictions: ["AAPL": 0.092], componentActuals: ["AAPL": 0.084]),
        SimulationModelResult(modelKey: "updated_working_model", displayName: "Updated Working Model", forecastModel: "prophet", versionID: "weekly-preview-1", explanation: "Latest iteratively improved working model.", predictedReturn: 0.086, actualReturn: 0.084, predictedEndingValue: 10860, actualEndingValue: 10840, predictedGainLoss: 860, actualGainLoss: 840, absoluteError: 0.002, percentageError: 0.024, directionalAccuracy: 1, status: "completed", rank: 1, latestUpdatedWorkingVersion: "weekly-preview-1", componentPredictions: ["AAPL": 0.086], componentActuals: ["AAPL": 0.084]),
    ]

    static let sampleFutureModelResults = [
        SimulationModelResult(modelKey: "truth_model", displayName: "Truth Model", forecastModel: "naive", versionID: "truth-v1", explanation: "Static reference model anchored to the knowledge base.", predictedReturn: 0.031, actualReturn: nil, predictedEndingValue: 10310, actualEndingValue: nil, predictedGainLoss: 310, actualGainLoss: nil, absoluteError: nil, percentageError: nil, directionalAccuracy: nil, status: "awaiting_actual_data", rank: nil, latestUpdatedWorkingVersion: "weekly-preview-1", componentPredictions: ["AAPL": 0.031], componentActuals: nil),
        SimulationModelResult(modelKey: "working_model", displayName: "Working Model", forecastModel: "arima", versionID: "weekly-preview-1", explanation: "Active adaptive model tied to the current working state.", predictedReturn: 0.042, actualReturn: nil, predictedEndingValue: 10420, actualEndingValue: nil, predictedGainLoss: 420, actualGainLoss: nil, absoluteError: nil, percentageError: nil, directionalAccuracy: nil, status: "awaiting_actual_data", rank: nil, latestUpdatedWorkingVersion: "weekly-preview-1", componentPredictions: ["AAPL": 0.042], componentActuals: nil),
        SimulationModelResult(modelKey: "updated_working_model", displayName: "Updated Working Model", forecastModel: "prophet", versionID: "weekly-preview-1", explanation: "Latest iteratively improved working model.", predictedReturn: 0.047, actualReturn: nil, predictedEndingValue: 10470, actualEndingValue: nil, predictedGainLoss: 470, actualGainLoss: nil, absoluteError: nil, percentageError: nil, directionalAccuracy: nil, status: "awaiting_actual_data", rank: nil, latestUpdatedWorkingVersion: "weekly-preview-1", componentPredictions: ["AAPL": 0.047], componentActuals: nil),
    ]

    static func metrics(knowledgeBase: KnowledgeBaseMode) -> MetricsDashboardResponse {
        MetricsDashboardResponse(
            knowledgeBase: knowledgeBase.rawValue,
            knowledgeVersion: knowledgeBase == .truth ? "truth-v1" : "daily-preview-1",
            summary: knowledgeBase == .truth ? "Authoritative formulas from truth_db." : "Adaptive working model with fresh daily learning outcomes.",
            items: [
                MetricCard(id: "AAPL", kind: "stock", displayName: "Apple Inc.", symbol: "AAPL", riskMetrics: riskMetrics, latestForecast: forecast, latestClose: 201.42),
                MetricCard(id: "basket-1", kind: "basket", displayName: "Tech Basket", symbol: nil, riskMetrics: riskMetrics, latestForecast: nil, latestClose: 128.7)
            ],
            recentSimulations: simulations
        )
    }

    static let macroOverview = MacroOverviewResponse(
        indicators: [
            MacroIndicator(
                id: 1,
                name: "CPI",
                fredSeriesID: "CPIAUCSL",
                frequency: "monthly",
                units: "index",
                latestObservation: MacroObservation(observationDate: "2026-03-01", value: 319.1, timestampUTC: "2026-03-01T00:00:00+00:00"),
                history: stride(from: 0, to: 8, by: 1).map {
                    MacroObservation(observationDate: "2025-\(String(format: "%02d", $0 + 8))-01", value: 300 + Double($0) * 2.2, timestampUTC: "2025-\(String(format: "%02d", $0 + 8))-01T00:00:00+00:00")
                }
            )
        ],
        commodities: [
            CommoditySnapshot(
                symbol: "CLUSD",
                name: "Crude Oil",
                source: "preview",
                latestPrice: CommodityPriceSnapshot(timestampUTC: "2026-04-14T00:00:00+00:00", close: 84.3, open: 82.1, high: 85.0, low: 81.7, volume: 10000),
                history: stride(from: 0, to: 10, by: 1).map {
                    CommodityHistoryPoint(tradingDate: "2026-04-\(String(format: "%02d", $0 + 1))", close: 76 + Double($0))
                }
            )
        ],
        predictionMarkets: [
            PredictionMarketSnapshot(
                marketID: "pm-1",
                slug: "fed-cut-june",
                question: "Will the Fed cut rates by June?",
                description: "Preview Polymarket feed",
                active: 1,
                closed: 0,
                endDateUTC: "2026-06-30T00:00:00+00:00",
                updatedAtUTC: "2026-04-14T08:00:00+00:00",
                timestampUTC: "2026-04-14T08:00:00+00:00",
                yesProb: 0.61,
                noProb: 0.39,
                lastTradePrice: 0.61,
                volume: 120000,
                liquidity: 54000
            )
        ]
    )

    static let alerts = AlertsResponse(
        items: [
            AlertItem(feedID: "alert-1", source: "math_agent", level: "warning", symbol: "AAPL", title: "Volatility drift", message: "Volatility discrepancy exceeded the configured threshold for AAPL.", timestampUTC: "2026-04-14T08:30:00+00:00"),
            AlertItem(feedID: "audit-2", source: "ops_agent", level: "info", symbol: nil, title: "Scheduler healthy", message: "Daily ETL and forecast jobs completed on time.", timestampUTC: "2026-04-14T08:00:00+00:00")
        ],
        systemStatus: health.systemStatus
    )
}
