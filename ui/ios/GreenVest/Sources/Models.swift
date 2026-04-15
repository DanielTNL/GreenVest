import Foundation

enum KnowledgeBaseMode: String, CaseIterable, Identifiable {
    case truth
    case working

    var id: String { rawValue }
    var title: String { rawValue.capitalized }
}

enum SimulationHorizon: String, CaseIterable, Identifiable {
    case daily
    case weekly
    case monthly

    var id: String { rawValue }
    var title: String { rawValue.capitalized }
}

enum SimulationRunType: String, CaseIterable, Identifiable {
    case past
    case future

    var id: String { rawValue }

    var title: String {
        switch self {
        case .past:
            return "Past Simulations"
        case .future:
            return "Future Simulations"
        }
    }
}

enum SimulationAssetKind: String, CaseIterable, Identifiable {
    case stock
    case basket

    var id: String { rawValue }
    var title: String { rawValue.capitalized }
}

struct StockListResponse: Codable {
    let items: [StockSummary]
}

struct StockSearchResponse: Codable {
    let items: [StockSearchCandidate]
}

struct StockSummary: Codable, Identifiable, Hashable {
    let symbol: String
    let name: String?
    let exchange: String?
    let assetType: String?
    let source: String?
    let latestClose: Double?
    let latestPriceTimestampUTC: String?

    var id: String { symbol }

    enum CodingKeys: String, CodingKey {
        case symbol
        case name
        case exchange
        case assetType = "asset_type"
        case source
        case latestClose = "latest_close"
        case latestPriceTimestampUTC = "latest_price_timestamp_utc"
    }
}

struct StockSearchCandidate: Codable, Identifiable, Hashable {
    let symbol: String
    let name: String?
    let exchange: String?
    let assetType: String?
    let source: String?
    let latestClose: Double?
    let latestPriceTimestampUTC: String?
    let isTracked: Bool

    var id: String { symbol }

    enum CodingKeys: String, CodingKey {
        case symbol
        case name
        case exchange
        case assetType = "asset_type"
        case source
        case latestClose = "latest_close"
        case latestPriceTimestampUTC = "latest_price_timestamp_utc"
        case isTracked = "is_tracked"
    }
}

struct WatchSuggestionResponse: Codable {
    let items: [WatchSuggestion]
}

struct WatchSuggestion: Codable, Identifiable, Hashable {
    let suggestionDate: String
    let symbol: String
    let rank: Int
    let name: String?
    let theme: String?
    let rationale: String?
    let score: Double?
    let latestClose: Double?
    let isTracked: Bool

    var id: String { "\(suggestionDate)-\(symbol)" }

    enum CodingKeys: String, CodingKey {
        case suggestionDate = "suggestion_date"
        case symbol
        case rank
        case name
        case theme
        case rationale
        case score
        case latestClose = "latest_close"
        case isTracked = "is_tracked"
    }
}

struct StockIdentity: Codable, Hashable {
    let symbol: String
    let name: String?
    let exchange: String?
    let assetType: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case symbol
        case name
        case exchange
        case assetType = "asset_type"
        case source
    }
}

struct StockDetailResponse: Codable {
    let stock: StockIdentity
    let latestClose: Double?
    let dailyChangePercent: Double?
    let priceHistory: [PricePoint]
    let riskMetrics: RiskMetrics?
    let latestForecast: ForecastSnapshot?

    enum CodingKeys: String, CodingKey {
        case stock
        case latestClose = "latest_close"
        case dailyChangePercent = "daily_change_percent"
        case priceHistory = "price_history"
        case riskMetrics = "risk_metrics"
        case latestForecast = "latest_forecast"
    }
}

struct BasketListResponse: Codable {
    let items: [BasketSummary]
}

struct BasketSummary: Codable, Identifiable, Hashable {
    let basketId: Int
    let name: String
    let description: String?
    let createdAtUTC: String?
    let constituents: [BasketConstituent]
    let riskMetrics: RiskMetrics?

    var id: Int { basketId }

    enum CodingKeys: String, CodingKey {
        case basketId = "basket_id"
        case name
        case description
        case createdAtUTC = "created_at_utc"
        case constituents
        case riskMetrics = "risk_metrics"
    }
}

struct BasketConstituent: Codable, Identifiable, Hashable {
    let basketId: Int
    let symbol: String
    let weight: Double

    var id: String { "\(basketId)-\(symbol)" }

    enum CodingKeys: String, CodingKey {
        case basketId = "basket_id"
        case symbol
        case weight
    }
}

struct BasketDetailResponse: Codable {
    let basket: BasketSummary
    let priceHistory: [PricePoint]
    let riskMetrics: RiskMetrics?
    let recentSimulations: [SimulationRecord]

    enum CodingKeys: String, CodingKey {
        case basket
        case priceHistory = "price_history"
        case riskMetrics = "risk_metrics"
        case recentSimulations = "recent_simulations"
    }
}

struct PricePoint: Codable, Identifiable, Hashable {
    let timestampUTC: String
    let tradingDate: String?
    let open: Double?
    let high: Double?
    let low: Double?
    let close: Double?
    let volume: Double?

    var id: String { timestampUTC + (tradingDate ?? "") }
    var dateValue: Date { AppDateParser.parse(timestampUTC) }

    enum CodingKeys: String, CodingKey {
        case timestampUTC = "timestamp_utc"
        case tradingDate = "trading_date"
        case open
        case high
        case low
        case close
        case volume
    }
}

struct RiskMetrics: Codable, Hashable {
    let volatility: Double?
    let covariance: Double?
    let correlation: Double?
    let sharpe: Double?
    let sortino: Double?
    let beta: Double?
    let varParametric: Double?
    let varHistorical: Double?
    let varMonteCarlo: Double?
    let cvar: Double?
    let maxDrawdown: Double?

    enum CodingKeys: String, CodingKey {
        case volatility
        case covariance
        case correlation
        case sharpe
        case sortino
        case beta
        case varParametric = "var_parametric"
        case varHistorical = "var_historical"
        case varMonteCarlo = "var_monte_carlo"
        case cvar
        case maxDrawdown = "max_drawdown"
    }
}

struct ForecastSnapshot: Codable, Hashable {
    let symbol: String
    let model: String
    let runTimestampUTC: String
    let horizon: Int
    let horizonUnit: String
    let forecastValue: Double?
    let lowerBound: Double?
    let upperBound: Double?
    let actualValue: Double?
    let errorValue: Double?
    let status: String?

    enum CodingKeys: String, CodingKey {
        case symbol
        case model
        case runTimestampUTC = "run_timestamp_utc"
        case horizon
        case horizonUnit = "horizon_unit"
        case forecastValue = "forecast_value"
        case lowerBound = "lower_bound"
        case upperBound = "upper_bound"
        case actualValue = "actual_value"
        case errorValue = "error_value"
        case status
    }
}

struct MetricsDashboardResponse: Codable {
    let knowledgeBase: String
    let knowledgeVersion: String
    let summary: String
    let items: [MetricCard]
    let recentSimulations: [SimulationRecord]

    enum CodingKeys: String, CodingKey {
        case knowledgeBase = "knowledge_base"
        case knowledgeVersion = "knowledge_version"
        case summary
        case items
        case recentSimulations = "recent_simulations"
    }
}

struct MetricCard: Codable, Identifiable, Hashable {
    let id: String
    let kind: String
    let displayName: String
    let symbol: String?
    let riskMetrics: RiskMetrics?
    let latestForecast: ForecastSnapshot?
    let latestClose: Double?

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case displayName = "display_name"
        case symbol
        case riskMetrics = "risk_metrics"
        case latestForecast = "latest_forecast"
        case latestClose = "latest_close"
    }
}

struct MacroOverviewResponse: Codable {
    let indicators: [MacroIndicator]
    let commodities: [CommoditySnapshot]
    let predictionMarkets: [PredictionMarketSnapshot]

    enum CodingKeys: String, CodingKey {
        case indicators
        case commodities
        case predictionMarkets = "prediction_markets"
    }
}

struct MacroIndicator: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let fredSeriesID: String
    let frequency: String?
    let units: String?
    let latestObservation: MacroObservation?
    let history: [MacroObservation]

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case fredSeriesID = "fred_series_id"
        case frequency
        case units
        case latestObservation = "latest_observation"
        case history
    }
}

struct MacroObservation: Codable, Identifiable, Hashable {
    let observationDate: String
    let value: Double?
    let timestampUTC: String?

    var id: String { observationDate }
    var dateValue: Date { AppDateParser.parse(timestampUTC ?? observationDate) }

    enum CodingKeys: String, CodingKey {
        case observationDate = "observation_date"
        case value
        case timestampUTC = "timestamp_utc"
    }
}

struct CommoditySnapshot: Codable, Identifiable, Hashable {
    let symbol: String
    let name: String?
    let source: String?
    let latestPrice: CommodityPriceSnapshot?
    let history: [CommodityHistoryPoint]

    var id: String { symbol }

    enum CodingKeys: String, CodingKey {
        case symbol
        case name
        case source
        case latestPrice = "latest_price"
        case history
    }
}

struct CommodityPriceSnapshot: Codable, Hashable {
    let timestampUTC: String
    let close: Double?
    let open: Double?
    let high: Double?
    let low: Double?
    let volume: Double?

    enum CodingKeys: String, CodingKey {
        case timestampUTC = "timestamp_utc"
        case close
        case open
        case high
        case low
        case volume
    }
}

struct CommodityHistoryPoint: Codable, Identifiable, Hashable {
    let tradingDate: String
    let close: Double?

    var id: String { tradingDate }
    var dateValue: Date { AppDateParser.parse(tradingDate) }

    enum CodingKeys: String, CodingKey {
        case tradingDate = "trading_date"
        case close
    }
}

struct PredictionMarketSnapshot: Codable, Identifiable, Hashable {
    let marketID: String
    let slug: String?
    let question: String
    let description: String?
    let active: Int?
    let closed: Int?
    let endDateUTC: String?
    let updatedAtUTC: String?
    let timestampUTC: String?
    let yesProb: Double?
    let noProb: Double?
    let lastTradePrice: Double?
    let volume: Double?
    let liquidity: Double?

    var id: String { marketID }

    enum CodingKeys: String, CodingKey {
        case marketID = "market_id"
        case slug
        case question
        case description
        case active
        case closed
        case endDateUTC = "end_date_utc"
        case updatedAtUTC = "updated_at_utc"
        case timestampUTC = "timestamp_utc"
        case yesProb = "yes_prob"
        case noProb = "no_prob"
        case lastTradePrice = "last_trade_price"
        case volume
        case liquidity
    }
}

struct AlertsResponse: Codable {
    let items: [AlertItem]
    let systemStatus: SystemStatus

    enum CodingKeys: String, CodingKey {
        case items
        case systemStatus = "system_status"
    }
}

struct AlertItem: Codable, Identifiable, Hashable {
    let feedID: String
    let source: String
    let level: String
    let symbol: String?
    let title: String
    let message: String
    let timestampUTC: String

    var id: String { feedID }
    var dateValue: Date { AppDateParser.parse(timestampUTC) }

    enum CodingKeys: String, CodingKey {
        case feedID = "feed_id"
        case source
        case level
        case symbol
        case title
        case message
        case timestampUTC = "timestamp_utc"
    }
}

struct SystemStatus: Codable, Hashable {
    let stockCount: Int
    let basketCount: Int
    let forecastCount: Int
    let simulationCount: Int
    let lastStockUpdateUTC: String?
    let lastMacroUpdateUTC: String?
    let lastPredictionMarketUpdateUTC: String?
    let lastAuditUTC: String?

    enum CodingKeys: String, CodingKey {
        case stockCount = "stock_count"
        case basketCount = "basket_count"
        case forecastCount = "forecast_count"
        case simulationCount = "simulation_count"
        case lastStockUpdateUTC = "last_stock_update_utc"
        case lastMacroUpdateUTC = "last_macro_update_utc"
        case lastPredictionMarketUpdateUTC = "last_prediction_market_update_utc"
        case lastAuditUTC = "last_audit_utc"
    }
}

struct SimulationOptionsResponse: Codable {
    let stocks: [StockSummary]
    let baskets: [BasketSummary]
}

struct SimulationRecord: Codable, Identifiable, Hashable {
    let simID: Int
    let basketID: Int?
    let portfolioName: String?
    let simulationType: String?
    let status: String?
    let modelsUsed: [String]?
    let aiAnalysis: String?
    let keyOutcomeSummary: String?
    let bestModel: String?
    let modelResults: [SimulationModelResult]?
    let assetKind: String?
    let assetIdentifier: String?
    let startDate: String
    let endDate: String
    let horizon: Int
    let horizonUnit: String
    let initialCapital: Double
    let predictedReturn: Double?
    let actualReturn: Double?
    let rmse: Double?
    let mape: Double?
    let directionalAccuracy: Double?
    let createdAtUTC: String

    var id: Int { simID }
    var dateValue: Date { AppDateParser.parse(createdAtUTC) }

    enum CodingKeys: String, CodingKey {
        case simID = "sim_id"
        case basketID = "basket_id"
        case portfolioName = "portfolio_name"
        case simulationType = "simulation_type"
        case status
        case modelsUsed = "models_used"
        case aiAnalysis = "ai_analysis"
        case keyOutcomeSummary = "key_outcome_summary"
        case bestModel = "best_model"
        case modelResults = "model_results"
        case assetKind = "asset_kind"
        case assetIdentifier = "asset_identifier"
        case startDate = "start_date"
        case endDate = "end_date"
        case horizon
        case horizonUnit = "horizon_unit"
        case initialCapital = "initial_capital"
        case predictedReturn = "predicted_return"
        case actualReturn = "actual_return"
        case rmse
        case mape
        case directionalAccuracy = "directional_accuracy"
        case createdAtUTC = "created_at_utc"
    }
}

struct SimulationsResponse: Codable {
    let items: [SimulationRecord]
}

struct SimulationRequest: Codable {
    let assetKind: String
    let assetIdentifier: String
    let simulationType: String
    let horizonUnit: String
    let modelName: String
    let initialCapital: Double
    let startDate: String
    let endDate: String

    enum CodingKeys: String, CodingKey {
        case assetKind = "asset_kind"
        case assetIdentifier = "asset_identifier"
        case simulationType = "simulation_type"
        case horizonUnit = "horizon_unit"
        case modelName = "model_name"
        case initialCapital = "initial_capital"
        case startDate = "start_date"
        case endDate = "end_date"
    }
}

struct SimulationResponse: Codable {
    let simulationID: Int
    let simulationType: String
    let status: String
    let portfolioName: String
    let assetKind: String
    let assetIdentifier: String
    let startDate: String
    let endDate: String
    let initialInvestment: Double
    let models: [SimulationModelResult]
    let bestModel: String?
    let aiAnalysis: String?
    let keyOutcomeSummary: String?

    enum CodingKeys: String, CodingKey {
        case simulationID = "simulation_id"
        case simulationType = "simulation_type"
        case status
        case portfolioName = "portfolio_name"
        case assetKind = "asset_kind"
        case assetIdentifier = "asset_identifier"
        case startDate = "start_date"
        case endDate = "end_date"
        case initialInvestment = "initial_investment"
        case models
        case bestModel = "best_model"
        case aiAnalysis = "ai_analysis"
        case keyOutcomeSummary = "key_outcome_summary"
    }
}

struct SimulationModelResult: Codable, Identifiable, Hashable {
    let modelKey: String
    let displayName: String
    let forecastModel: String?
    let versionID: String?
    let explanation: String?
    let predictedReturn: Double?
    let actualReturn: Double?
    let predictedEndingValue: Double?
    let actualEndingValue: Double?
    let predictedGainLoss: Double?
    let actualGainLoss: Double?
    let absoluteError: Double?
    let percentageError: Double?
    let directionalAccuracy: Double?
    let status: String?
    let rank: Int?
    let latestUpdatedWorkingVersion: String?
    let componentPredictions: [String: Double]?
    let componentActuals: [String: Double]?

    var id: String { modelKey }

    enum CodingKeys: String, CodingKey {
        case modelKey = "model_key"
        case displayName = "display_name"
        case forecastModel = "forecast_model"
        case versionID = "version_id"
        case explanation
        case predictedReturn = "predicted_return"
        case actualReturn = "actual_return"
        case predictedEndingValue = "predicted_ending_value"
        case actualEndingValue = "actual_ending_value"
        case predictedGainLoss = "predicted_gain_loss"
        case actualGainLoss = "actual_gain_loss"
        case absoluteError = "absolute_error"
        case percentageError = "percentage_error"
        case directionalAccuracy = "directional_accuracy"
        case status
        case rank
        case latestUpdatedWorkingVersion = "latest_updated_working_version"
        case componentPredictions = "component_predictions"
        case componentActuals = "component_actuals"
    }
}

struct BasketCreateRequest: Codable {
    let name: String
    let description: String
    let symbols: [String]
    let equalWeight: Bool

    enum CodingKeys: String, CodingKey {
        case name
        case description
        case symbols
        case equalWeight = "equal_weight"
    }
}

struct TrackStockRequest: Codable {
    let symbol: String
    let name: String?
    let exchange: String?
}

struct AuditRunResponse: Codable {
    let items: [AuditEntry]
}

struct AuditEntry: Codable, Identifiable, Hashable {
    let symbol: String
    let status: String
    let message: String?
    let volatility: Double?

    var id: String { symbol + status }
}

struct ChatRequest: Codable {
    let message: String
}

struct ChatResponse: Codable, Hashable {
    let reply: String
    let actions: [ChatAction]
    let intent: String
}

struct ChatAction: Codable, Identifiable, Hashable {
    let title: String
    let prompt: String

    var id: String { title + prompt }
}

struct HealthResponse: Codable {
    let status: String
    let systemStatus: SystemStatus
    let truthVersion: String
    let workingVersions: [String: String]

    enum CodingKeys: String, CodingKey {
        case status
        case systemStatus = "system_status"
        case truthVersion = "truth_version"
        case workingVersions = "working_versions"
    }
}

struct APIErrorEnvelope: Codable {
    let error: String
}
