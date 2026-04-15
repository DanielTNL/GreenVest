import Charts
import SwiftUI

struct MacroGeopoliticsScreen: View {
    @StateObject private var viewModel: MacroViewModel

    init(backend: any BackendServing) {
        _viewModel = StateObject(wrappedValue: MacroViewModel(backend: backend))
    }

    var body: some View {
        NavigationStack {
            ScreenContainer {
                ScrollView {
                    VStack(spacing: 16) {
                        if let errorMessage = viewModel.errorMessage {
                            ErrorBanner(message: errorMessage)
                        }
                        if viewModel.isLoading, viewModel.macroOverview == nil {
                            ContentCard { LoadingStateView(message: "Loading macro and geopolitics feeds...") }
                        } else if let overview = viewModel.macroOverview {
                            ContentCard(title: "Macroeconomic Indicators") {
                                if overview.indicators.isEmpty {
                                    EmptyStateView(title: "No Macro Data", message: "Run FRED ingestion to populate macro indicators.")
                                } else {
                                    ForEach(overview.indicators) { indicator in
                                        VStack(alignment: .leading, spacing: 10) {
                                            Text(indicator.name)
                                                .font(.headline)
                                            Text("Used as an exogenous model input when available.")
                                                .font(.footnote)
                                                .foregroundStyle(.secondary)
                                            ChartContainer(observations: indicator.history)
                                            HStack {
                                                InfoChip(title: "Latest", value: indicator.latestObservation?.value?.decimalString ?? "n/a")
                                                InfoChip(title: "Frequency", value: indicator.frequency ?? "n/a")
                                            }
                                        }
                                        .padding(.vertical, 8)
                                    }
                                }
                            }

                            ContentCard(title: "Commodities") {
                                ForEach(overview.commodities) { commodity in
                                    VStack(alignment: .leading, spacing: 10) {
                                        Text(commodity.name ?? commodity.symbol)
                                            .font(.headline)
                                        Text(commodity.latestPrice?.close?.currencyString ?? "n/a")
                                            .font(.subheadline)
                                            .foregroundStyle(.secondary)
                                        CommodityChart(history: commodity.history)
                                    }
                                    .padding(.vertical, 8)
                                }
                            }

                            ContentCard(title: "Prediction Markets") {
                                ForEach(overview.predictionMarkets) { market in
                                    VStack(alignment: .leading, spacing: 10) {
                                        Text(market.question)
                                            .font(.headline)
                                        HStack {
                                            InfoChip(title: "Yes", value: market.yesProb?.percentString ?? "n/a")
                                            InfoChip(title: "No", value: market.noProb?.percentString ?? "n/a")
                                            InfoChip(title: "Liquidity", value: market.liquidity?.currencyString ?? "n/a")
                                        }
                                        Text(market.description ?? "")
                                            .font(.footnote)
                                            .foregroundStyle(.secondary)
                                    }
                                    .padding(.vertical, 8)
                                }
                            }
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Macro & Geopolitics")
            .task { await viewModel.load() }
        }
    }
}

private struct ChartContainer: View {
    let observations: [MacroObservation]

    var body: some View {
        Chart(observations) { observation in
            if let value = observation.value {
                LineMark(x: .value("Date", observation.dateValue), y: .value("Value", value))
                    .foregroundStyle(Color.gvAccent)
            }
        }
        .frame(height: 180)
    }
}

private struct CommodityChart: View {
    let history: [CommodityHistoryPoint]

    var body: some View {
        Chart(history) { point in
            if let close = point.close {
                LineMark(x: .value("Date", point.dateValue), y: .value("Close", close))
                    .foregroundStyle(Color.gvChartPositive)
            }
        }
        .frame(height: 180)
    }
}
