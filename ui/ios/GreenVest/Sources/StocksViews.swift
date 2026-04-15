import SwiftUI

struct StocksBasketsScreen: View {
    let backend: any BackendServing
    @StateObject private var viewModel: StocksViewModel
    @State private var isBasketComposerPresented = false

    init(backend: any BackendServing) {
        self.backend = backend
        _viewModel = StateObject(wrappedValue: StocksViewModel(backend: backend))
    }

    var body: some View {
        NavigationStack {
            ScreenContainer {
                ScrollView {
                    VStack(spacing: 16) {
                        if let errorMessage = viewModel.errorMessage {
                            ErrorBanner(message: errorMessage)
                        }
                        if !viewModel.searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                            ContentCard(title: "Search Results") {
                                if viewModel.isSearching {
                                    LoadingStateView(message: "Searching symbols...")
                                } else if viewModel.searchResults.isEmpty {
                                    EmptyStateView(title: "No Matches", message: "Try another company name or ticker symbol.")
                                } else {
                                    ForEach(viewModel.searchResults) { candidate in
                                        HStack(spacing: 12) {
                                            VStack(alignment: .leading, spacing: 4) {
                                                Text(candidate.symbol)
                                                    .font(.headline)
                                                Text(candidate.name ?? "Unknown Company")
                                                    .font(.subheadline)
                                                    .foregroundStyle(.secondary)
                                                if let exchange = candidate.exchange {
                                                    Text(exchange)
                                                        .font(.caption)
                                                        .foregroundStyle(.secondary)
                                                }
                                            }
                                            Spacer()
                                            if candidate.isTracked {
                                                Text("Tracked")
                                                    .font(.caption.weight(.semibold))
                                                    .foregroundStyle(.secondary)
                                            } else {
                                                Button {
                                                    Task { await viewModel.track(candidate) }
                                                } label: {
                                                    Label("Add", systemImage: "plus.circle.fill")
                                                }
                                                .buttonStyle(.borderedProminent)
                                                .tint(.gvAccent)
                                                .disabled(viewModel.isTracking)
                                            }
                                        }
                                        .padding(.vertical, 6)
                                        if candidate.id != viewModel.searchResults.last?.id {
                                            Divider()
                                        }
                                    }
                                }
                            }
                        } else {
                            ContentCard(title: "Daily Ideas") {
                                if viewModel.isLoading && viewModel.suggestions.isEmpty {
                                    LoadingStateView(message: "Preparing today's watchlist ideas...")
                                } else if viewModel.suggestions.isEmpty {
                                    EmptyStateView(title: "No Ideas Yet", message: "Daily ideas will appear here after the morning suggestion run.")
                                } else {
                                    ForEach(viewModel.suggestions) { suggestion in
                                        HStack(alignment: .top, spacing: 12) {
                                            VStack(alignment: .leading, spacing: 6) {
                                                HStack {
                                                    Text("\(suggestion.rank). \(suggestion.symbol)")
                                                        .font(.headline)
                                                    if let theme = suggestion.theme {
                                                        Text(theme)
                                                            .font(.caption.weight(.semibold))
                                                            .padding(.horizontal, 8)
                                                            .padding(.vertical, 4)
                                                            .background(Capsule().fill(Color.gvAccent.opacity(0.12)))
                                                    }
                                                }
                                                Text(suggestion.name ?? suggestion.symbol)
                                                    .font(.subheadline)
                                                    .foregroundStyle(.secondary)
                                                Text(suggestion.rationale ?? "AI-selected daily watchlist candidate.")
                                                    .font(.footnote)
                                                    .foregroundStyle(.secondary)
                                            }
                                            Spacer()
                                            VStack(alignment: .trailing, spacing: 8) {
                                                if let latestClose = suggestion.latestClose {
                                                    Text(latestClose.currencyString)
                                                        .font(.subheadline.weight(.semibold))
                                                }
                                                if suggestion.isTracked {
                                                    Text("Tracked")
                                                        .font(.caption.weight(.semibold))
                                                        .foregroundStyle(.secondary)
                                                } else {
                                                    Button {
                                                        Task {
                                                            await viewModel.track(
                                                                StockSearchCandidate(
                                                                    symbol: suggestion.symbol,
                                                                    name: suggestion.name,
                                                                    exchange: nil,
                                                                    assetType: "equity",
                                                                    source: "watch_suggestion",
                                                                    latestClose: suggestion.latestClose,
                                                                    latestPriceTimestampUTC: nil,
                                                                    isTracked: suggestion.isTracked
                                                                )
                                                            )
                                                        }
                                                    } label: {
                                                        Label("Add", systemImage: "plus.circle.fill")
                                                    }
                                                    .buttonStyle(.bordered)
                                                    .tint(.gvAccent)
                                                    .disabled(viewModel.isTracking)
                                                }
                                            }
                                        }
                                        .padding(.vertical, 6)
                                        if suggestion.id != viewModel.suggestions.last?.id {
                                            Divider()
                                        }
                                    }
                                }
                            }
                        }
                        ContentCard(title: "Watchlist") {
                            if viewModel.isLoading && viewModel.stocks.isEmpty {
                                LoadingStateView(message: "Loading market data...")
                            } else if viewModel.stocks.isEmpty {
                                EmptyStateView(title: "No Stocks Yet", message: "Search for a stock above and tap Add to start tracking it.")
                            } else {
                                ForEach(viewModel.stocks) { stock in
                                    NavigationLink {
                                        StockDetailScreen(backend: backend, symbol: stock.symbol)
                                    } label: {
                                        HStack {
                                            VStack(alignment: .leading, spacing: 4) {
                                                Text(stock.symbol)
                                                    .font(.headline)
                                                Text(stock.name ?? "Unknown Company")
                                                    .font(.subheadline)
                                                    .foregroundStyle(.secondary)
                                            }
                                            Spacer()
                                            VStack(alignment: .trailing, spacing: 4) {
                                                Text(stock.latestClose?.currencyString ?? "n/a")
                                                    .font(.headline)
                                                Text(stock.exchange ?? "")
                                                    .font(.caption)
                                                    .foregroundStyle(.secondary)
                                            }
                                        }
                                        .padding(.vertical, 6)
                                    }
                                    .buttonStyle(.plain)
                                    .accessibilityIdentifier("stock_row_\(stock.symbol)")
                                    if stock.id != viewModel.stocks.last?.id {
                                        Divider()
                                    }
                                }
                            }
                        }

                        ContentCard(title: "Baskets") {
                            if viewModel.baskets.isEmpty {
                                EmptyStateView(title: "No Baskets", message: "Create baskets through the chat assistant or backend API.")
                            } else {
                                ForEach(viewModel.baskets) { basket in
                                    NavigationLink {
                                        BasketDetailScreen(backend: backend, basketID: basket.basketId)
                                    } label: {
                                        VStack(alignment: .leading, spacing: 8) {
                                            HStack {
                                                Text(basket.name)
                                                    .font(.headline)
                                                Spacer()
                                                Text("\(basket.constituents.count) holdings")
                                                    .font(.caption)
                                                    .foregroundStyle(.secondary)
                                            }
                                            Text(basket.description ?? "No description")
                                                .font(.subheadline)
                                                .foregroundStyle(.secondary)
                                            ScrollView(.horizontal, showsIndicators: false) {
                                                HStack {
                                                    ForEach(basket.constituents) { constituent in
                                                        InfoChip(title: constituent.symbol, value: constituent.weight.percentString)
                                                    }
                                                }
                                            }
                                        }
                                        .padding(.vertical, 6)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Stocks & Baskets")
            .searchable(text: $viewModel.searchText, prompt: "Search stocks")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        isBasketComposerPresented = true
                    } label: {
                        Label("New Basket", systemImage: "plus.circle.fill")
                    }
                    .disabled(viewModel.stocks.isEmpty)
                }
            }
            .task { await viewModel.load() }
            .task(id: viewModel.searchText) {
                try? await Task.sleep(for: .milliseconds(350))
                await viewModel.searchCatalog()
            }
            .sheet(isPresented: $isBasketComposerPresented) {
                BasketComposerSheet(backend: backend, availableStocks: viewModel.stocks) { _ in
                    Task { await viewModel.load() }
                }
            }
        }
    }
}

struct StockDetailScreen: View {
    @StateObject private var viewModel: StockDetailViewModel

    init(backend: any BackendServing, symbol: String) {
        _viewModel = StateObject(wrappedValue: StockDetailViewModel(backend: backend, symbol: symbol))
    }

    var body: some View {
        ScreenContainer {
            ScrollView {
                VStack(spacing: 16) {
                    if let errorMessage = viewModel.errorMessage {
                        ErrorBanner(message: errorMessage)
                    }
                    if viewModel.isLoading, viewModel.detail == nil {
                        ContentCard { LoadingStateView(message: "Loading \(viewModel.symbol)...") }
                    } else if let detail = viewModel.detail {
                        ContentCard {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(detail.stock.symbol)
                                    .font(.largeTitle.bold())
                                Text(detail.stock.name ?? "")
                                    .font(.headline)
                                    .foregroundStyle(.secondary)
                                HStack {
                                    InfoChip(title: "Last", value: detail.latestClose?.currencyString ?? "n/a")
                                    InfoChip(title: "1D", value: detail.dailyChangePercent?.percentString ?? "n/a")
                                }
                            }
                        }
                        ContentCard(title: "Price Chart") {
                            if detail.priceHistory.contains(where: { $0.open != nil || $0.high != nil || $0.low != nil }) {
                                CandlestickPriceChart(points: detail.priceHistory)
                            } else {
                                PriceLineChart(points: detail.priceHistory)
                            }
                        }
                        if let riskMetrics = detail.riskMetrics {
                            ContentCard(title: "Risk Metrics") {
                                RiskMetricSummaryView(riskMetrics: riskMetrics)
                                RiskMetricBarChart(riskMetrics: riskMetrics)
                            }
                        }
                        if let forecast = detail.latestForecast {
                            ContentCard(title: "Latest Forecast") {
                                HStack {
                                    InfoChip(title: "Model", value: forecast.model.capitalized)
                                    InfoChip(title: "Horizon", value: forecast.horizonUnit.capitalized)
                                    InfoChip(title: "Forecast", value: forecast.forecastValue?.percentString ?? "n/a")
                                }
                            }
                        }
                    }
                }
                .padding()
            }
        }
        .navigationTitle(viewModel.symbol)
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.load() }
    }
}

struct BasketDetailScreen: View {
    private let backend: any BackendServing
    @StateObject private var viewModel: BasketDetailViewModel
    @State private var isBasketComposerPresented = false

    init(backend: any BackendServing, basketID: Int) {
        self.backend = backend
        _viewModel = StateObject(wrappedValue: BasketDetailViewModel(backend: backend, basketID: basketID))
    }

    var body: some View {
        ScreenContainer {
            ScrollView {
                VStack(spacing: 16) {
                    if let errorMessage = viewModel.errorMessage {
                        ErrorBanner(message: errorMessage)
                    }
                    if viewModel.isLoading, viewModel.detail == nil {
                        ContentCard { LoadingStateView(message: "Loading basket...") }
                    } else if let detail = viewModel.detail {
                        ContentCard {
                            Text(detail.basket.name)
                                .font(.largeTitle.bold())
                            Text(detail.basket.description ?? "Portfolio basket")
                                .font(.headline)
                                .foregroundStyle(.secondary)
                        }
                        ContentCard(title: "Basket Performance") {
                            PriceLineChart(points: detail.priceHistory)
                        }
                        ContentCard(title: "Constituents") {
                            ForEach(detail.basket.constituents) { constituent in
                                HStack {
                                    Text(constituent.symbol)
                                    Spacer()
                                    Text(constituent.weight.percentString)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 4)
                            }
                        }
                        if let riskMetrics = detail.riskMetrics {
                            ContentCard(title: "Risk Metrics") {
                                RiskMetricSummaryView(riskMetrics: riskMetrics)
                            }
                        }
                    }
                }
                .padding()
            }
        }
        .navigationTitle("Basket")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if viewModel.detail != nil {
                    Button("Edit") {
                        isBasketComposerPresented = true
                    }
                }
            }
        }
        .task { await viewModel.load() }
        .sheet(isPresented: $isBasketComposerPresented) {
            if let detail = viewModel.detail {
                BasketComposerSheet(
                    backend: backend,
                    availableStocks: [],
                    initialBasket: detail.basket
                ) { _ in
                    Task { await viewModel.load() }
                }
            }
        }
    }
}

private struct RiskMetricSummaryView: View {
    let riskMetrics: RiskMetrics

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            InfoChip(title: "Volatility", value: riskMetrics.volatility?.percentString ?? "n/a")
            InfoChip(title: "Sharpe", value: riskMetrics.sharpe?.decimalString ?? "n/a")
            InfoChip(title: "Sortino", value: riskMetrics.sortino?.decimalString ?? "n/a")
            InfoChip(title: "Beta", value: riskMetrics.beta?.decimalString ?? "n/a")
            InfoChip(title: "VaR", value: riskMetrics.varHistorical?.percentString ?? "n/a")
            InfoChip(title: "Drawdown", value: riskMetrics.maxDrawdown?.percentString ?? "n/a")
        }
    }
}
