import SwiftUI

struct MetricsScreen: View {
    @StateObject private var viewModel: MetricsViewModel

    init(backend: any BackendServing) {
        _viewModel = StateObject(wrappedValue: MetricsViewModel(backend: backend))
    }

    var body: some View {
        NavigationStack {
            ScreenContainer {
                ScrollView {
                    VStack(spacing: 16) {
                        if let errorMessage = viewModel.errorMessage {
                            ErrorBanner(message: errorMessage)
                        }
                        ContentCard(title: "How To Read This") {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("`Truth` uses the fixed formulas and definitions from the authoritative knowledge base. `Working` uses the same formulas, but with the latest learned parameters, calibration choices, and recent model updates.")
                                    .foregroundStyle(.secondary)
                                Text("Forecast charts use decimal returns. For example, `0.01` means about `1%`, `-0.02` means about `-2%`. Metrics such as volatility, Sharpe, Sortino, beta, and drawdown do not share the same scale, so they are explained individually below instead of being forced onto one axis.")
                                    .foregroundStyle(.secondary)
                            }
                        }

                        ContentCard(title: "Knowledge Base") {
                            Picker("Mode", selection: $viewModel.knowledgeBase) {
                                ForEach(KnowledgeBaseMode.allCases) { mode in
                                    Text(mode.title).tag(mode)
                                }
                            }
                            .pickerStyle(.segmented)

                            if let dashboard = viewModel.dashboard {
                                Text(dashboard.knowledgeVersion)
                                    .font(.title3.bold())
                                Text(dashboard.summary)
                                    .foregroundStyle(.secondary)
                                KnowledgeBaseExplanationView(mode: viewModel.knowledgeBase)
                            }
                        }

                        if let dashboard = viewModel.dashboard {
                            ContentCard(title: "Forecast vs Actual") {
                                if dashboard.recentSimulations.isEmpty {
                                    EmptyStateView(title: "No Forecast History", message: "Simulations will appear here after model runs.")
                                } else {
                                    SimulationTrendChart(simulations: dashboard.recentSimulations)
                                    ForecastChartExplanationView(simulations: dashboard.recentSimulations)
                                }
                            }

                            ContentCard(title: "Latest Metrics") {
                                ForEach(dashboard.items) { item in
                                    VStack(alignment: .leading, spacing: 12) {
                                        HStack {
                                            VStack(alignment: .leading) {
                                                Text(item.displayName)
                                                    .font(.headline)
                                                Text(item.kind.capitalized)
                                                    .font(.caption)
                                                    .foregroundStyle(.secondary)
                                            }
                                            Spacer()
                                            Text(item.latestClose?.currencyString ?? "n/a")
                                                .font(.headline)
                                        }
                                        if let riskMetrics = item.riskMetrics {
                                            MetricSummaryView(riskMetrics: riskMetrics)
                                        }
                                        if let forecast = item.latestForecast {
                                            ForecastInsightView(forecast: forecast)
                                        }
                                        AIInterpretationView(item: item)
                                    }
                                    .padding(.vertical, 8)
                                }
                            }

                            ContentCard(title: "Using Predictions Responsibly") {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text("These predictions are research tools, not personal financial advice. A positive forecast does not mean a trade should be made, and a negative forecast does not automatically mean an asset should be avoided.")
                                        .foregroundStyle(.secondary)
                                    Text("A sensible workflow is: use `Truth` to understand the fixed logic, use `Working` to see how recent data is influencing the live model, compare forecast ranges with volatility and drawdown, and then challenge the output with macro and geopolitical context before acting.")
                                        .foregroundStyle(.secondary)
                                }
                            }
                        } else if viewModel.isLoading {
                            ContentCard { LoadingStateView(message: "Loading metrics...") }
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Predictions & Metrics")
            .task { await viewModel.load() }
            .task(id: viewModel.knowledgeBase) { await viewModel.load() }
        }
    }
}

private struct KnowledgeBaseExplanationView: View {
    let mode: KnowledgeBaseMode

    private var title: String {
        switch mode {
        case .truth:
            return "What Truth Means"
        case .working:
            return "What Working Means"
        }
    }

    private var bodyText: String {
        switch mode {
        case .truth:
            return "This is the stable reference model. It keeps the official formulas, metric definitions, and econometric logic unchanged so the app has a reproducible anchor."
        case .working:
            return "This is the adaptive model. It preserves the same definitions as Truth, but updates learned parameters after daily, weekly, and monthly prediction results so the system can improve over time."
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.subheadline.weight(.semibold))
            Text(bodyText)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.gvAccent.opacity(0.08))
        )
    }
}

private struct ForecastChartExplanationView: View {
    let simulations: [SimulationRecord]

    private var latestErrorText: String {
        guard let latest = simulations.sorted(by: { $0.dateValue > $1.dateValue }).first else { return "n/a" }
        if let mape = latest.mape {
            return mape.percentString
        }
        if let rmse = latest.rmse {
            return rmse.percentString
        }
        return "n/a"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("How to read this chart")
                .font(.subheadline.weight(.semibold))
            Text("The green line is the model forecast and the darker line is the realised result. The vertical axis is in decimal returns, so `0.01` is roughly `1%` and `-0.01` is roughly `-1%`.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Text("Latest forecast error: \(latestErrorText). Smaller gaps generally mean the current model is tracking reality more closely.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }
}

private struct ForecastInsightView: View {
    let forecast: ForecastSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                InfoChip(title: "Forecast", value: forecast.forecastValue?.percentString ?? "n/a")
                InfoChip(title: "Range", value: "\(forecast.lowerBound?.percentString ?? "n/a") to \(forecast.upperBound?.percentString ?? "n/a")")
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Forecast context")
                    .font(.subheadline.weight(.semibold))
                Text(forecastExplanation(forecast))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func forecastExplanation(_ forecast: ForecastSnapshot) -> String {
        let central = forecast.forecastValue ?? 0
        let width = (forecast.upperBound ?? central) - (forecast.lowerBound ?? central)
        let direction: String
        if central > 0.005 {
            direction = "leans positive"
        } else if central < -0.005 {
            direction = "leans negative"
        } else {
            direction = "is close to flat"
        }

        let certainty: String
        if width < 0.03 {
            certainty = "with a relatively tight range"
        } else if width < 0.08 {
            certainty = "with a moderate uncertainty band"
        } else {
            certainty = "with a wide uncertainty band"
        }

        return "The current \(forecast.model.uppercased()) forecast \(direction) \(certainty). This should be read as a scenario estimate, not a guaranteed outcome."
    }
}

private struct MetricSummaryView: View {
    let riskMetrics: RiskMetrics

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12)
    ]

    private var entries: [MetricExplainer] {
        [
            MetricExplainer(
                title: "Volatility",
                value: riskMetrics.volatility.map { $0.percentString } ?? "n/a",
                explanation: "Annualised variability of returns. Higher values usually mean a rougher ride.",
                signal: interpretVolatility(riskMetrics.volatility)
            ),
            MetricExplainer(
                title: "Sharpe",
                value: riskMetrics.sharpe.map { formatRatio($0) } ?? "n/a",
                explanation: "Return per unit of total risk. Higher is usually better if the estimate is stable.",
                signal: interpretSharpe(riskMetrics.sharpe)
            ),
            MetricExplainer(
                title: "Sortino",
                value: riskMetrics.sortino.map { formatRatio($0) } ?? "n/a",
                explanation: "Return per unit of downside risk. It focuses on harmful volatility.",
                signal: interpretSortino(riskMetrics.sortino)
            ),
            MetricExplainer(
                title: "Beta",
                value: riskMetrics.beta.map { formatRatio($0) } ?? "n/a",
                explanation: "Sensitivity to market moves. Around 1 tracks the market, above 1 is more reactive.",
                signal: interpretBeta(riskMetrics.beta)
            ),
            MetricExplainer(
                title: "VaR",
                value: riskMetrics.varHistorical.map { $0.percentString } ?? "n/a",
                explanation: "Estimated loss threshold at a chosen confidence level under normal conditions.",
                signal: interpretVar(riskMetrics.varHistorical)
            ),
            MetricExplainer(
                title: "Max Drawdown",
                value: riskMetrics.maxDrawdown.map { $0.percentString } ?? "n/a",
                explanation: "Largest peak-to-trough decline seen in the lookback period.",
                signal: interpretDrawdown(riskMetrics.maxDrawdown)
            )
        ]
    }

    var body: some View {
        LazyVGrid(columns: columns, spacing: 12) {
            ForEach(entries) { entry in
                VStack(alignment: .leading, spacing: 8) {
                    Text(entry.title)
                        .font(.subheadline.weight(.semibold))
                    Text(entry.value)
                        .font(.title3.weight(.bold))
                    Text(entry.signal)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Color.gvAccent)
                    Text(entry.explanation)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .background(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(Color.gvCardBackground.opacity(0.8))
                )
            }
        }
    }

    private func formatRatio(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(2)))
    }

    private func interpretVolatility(_ value: Double?) -> String {
        guard let value else { return "Waiting for more data" }
        switch value {
        case ..<0.15: return "Relatively calm"
        case ..<0.30: return "Moderate movement"
        default: return "High variability"
        }
    }

    private func interpretSharpe(_ value: Double?) -> String {
        guard let value else { return "Waiting for more data" }
        switch value {
        case ..<0: return "Risk not well rewarded"
        case ..<1: return "Modest risk-adjusted return"
        case ..<2: return "Solid risk-adjusted return"
        default: return "Very strong if stable"
        }
    }

    private func interpretSortino(_ value: Double?) -> String {
        guard let value else { return "Waiting for more data" }
        switch value {
        case ..<0: return "Downside risk outweighs return"
        case ..<1: return "Limited downside efficiency"
        case ..<2: return "Healthy downside profile"
        default: return "Very strong downside profile"
        }
    }

    private func interpretBeta(_ value: Double?) -> String {
        guard let value else { return "Waiting for more data" }
        switch value {
        case ..<0.8: return "Less reactive than market"
        case ...1.2: return "Close to market sensitivity"
        default: return "More reactive than market"
        }
    }

    private func interpretVar(_ value: Double?) -> String {
        guard let value else { return "Waiting for more data" }
        let loss = abs(value)
        switch loss {
        case ..<0.02: return "Contained tail risk"
        case ..<0.05: return "Meaningful downside risk"
        default: return "Heavy tail-risk warning"
        }
    }

    private func interpretDrawdown(_ value: Double?) -> String {
        guard let value else { return "Waiting for more data" }
        let loss = abs(value)
        switch loss {
        case ..<0.10: return "Shallow drawdown history"
        case ..<0.25: return "Moderate drawdown history"
        default: return "Deep drawdown history"
        }
    }
}

private struct AIInterpretationView: View {
    let item: MetricCard

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("AI-style interpretation")
                .font(.subheadline.weight(.semibold))
            Text(summaryText)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.gvAccent.opacity(0.08))
        )
    }

    private var summaryText: String {
        let volatility = item.riskMetrics?.volatility
        let sharpe = item.riskMetrics?.sharpe
        let beta = item.riskMetrics?.beta
        let forecast = item.latestForecast?.forecastValue

        let riskText: String
        if let volatility {
            riskText = volatility > 0.30 ? "The asset is currently behaving like a higher-risk name." : "The asset is showing a more moderate risk profile."
        } else {
            riskText = "The app still needs more price history before the risk profile becomes reliable."
        }

        let rewardText: String
        if let sharpe {
            rewardText = sharpe > 1 ? "Recent returns have compensated risk reasonably well." : "Recent returns have not strongly compensated for risk yet."
        } else {
            rewardText = "Risk-adjusted return is still being estimated."
        }

        let marketText: String
        if let beta {
            marketText = beta > 1.1 ? "It may amplify broader market moves." : beta < 0.9 ? "It may move less aggressively than the broader market." : "It is broadly moving in line with the market."
        } else {
            marketText = "Market sensitivity is still stabilising."
        }

        let forecastText: String
        if let forecast {
            forecastText = forecast > 0 ? "The latest forecast tilts positive, but should be treated as a probability-weighted scenario rather than a promise." : forecast < 0 ? "The latest forecast tilts negative, which is useful as a caution flag rather than a direct instruction." : "The latest forecast is close to neutral."
        } else {
            forecastText = "There is no current forecast snapshot for this asset yet."
        }

        return "\(riskText) \(rewardText) \(marketText) \(forecastText)"
    }
}

private struct MetricExplainer: Identifiable {
    let id = UUID()
    let title: String
    let value: String
    let explanation: String
    let signal: String
}
