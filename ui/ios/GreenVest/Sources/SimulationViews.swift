import Charts
import SwiftUI

struct SimulationsScreen: View {
    let backend: any BackendServing
    @StateObject private var viewModel: SimulationViewModel
    @ObservedObject var notificationManager: NotificationManager
    @State private var isBasketComposerPresented = false
    @State private var selectedRun: SimulationRecord?
    @State private var selectedModel: SimulationModelResult?
    @FocusState private var isInvestmentFieldFocused: Bool

    init(backend: any BackendServing, notificationManager: NotificationManager) {
        self.backend = backend
        _viewModel = StateObject(wrappedValue: SimulationViewModel(backend: backend))
        self.notificationManager = notificationManager
    }

    var body: some View {
        NavigationStack {
            ScreenContainer {
                ScrollView {
                    VStack(spacing: 16) {
                        if let errorMessage = viewModel.errorMessage {
                            ErrorBanner(message: errorMessage)
                        }

                        ContentCard(title: "Simulation Type") {
                            Picker("Simulation Type", selection: $viewModel.runType) {
                                ForEach(SimulationRunType.allCases) { type in
                                    Text(type.title).tag(type)
                                }
                            }
                            .pickerStyle(.segmented)

                            Text(
                                viewModel.runType == .past
                                    ? "Retrospective testing compares the Truth Model and the Working Model against known historical outcomes."
                                    : "Forward-looking simulations freeze the Truth Model and Working Model now, then compare them with the Updated Working Model once the period ends."
                            )
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                        }

                        ContentCard(title: "Run Simulation") {
                            Picker("Asset Type", selection: $viewModel.assetKind) {
                                ForEach(SimulationAssetKind.allCases) { kind in
                                    Text(kind.title).tag(kind)
                                }
                            }
                            .pickerStyle(.segmented)

                            if viewModel.assetKind == .stock {
                                Picker("Stock", selection: $viewModel.selectedStockSymbol) {
                                    ForEach(viewModel.stocks) { stock in
                                        Text(stock.symbol).tag(stock.symbol)
                                    }
                                }
                            } else {
                                VStack(alignment: .leading, spacing: 12) {
                                    Picker("Basket", selection: $viewModel.selectedBasketID) {
                                        ForEach(viewModel.baskets) { basket in
                                            Text(basket.name).tag(Optional(basket.basketId))
                                        }
                                    }

                                    HStack(alignment: .top, spacing: 12) {
                                        Text(viewModel.baskets.isEmpty ? "Create a reusable basket from your stock list to simulate it here." : "Saved baskets can be reused for future simulations and broader tracking.")
                                            .font(.footnote)
                                            .foregroundStyle(.secondary)
                                        Spacer()
                                        Button {
                                            isBasketComposerPresented = true
                                        } label: {
                                            Label("Create Basket", systemImage: "plus.circle.fill")
                                        }
                                        .buttonStyle(.bordered)
                                    }
                                }
                            }

                            Picker("Horizon", selection: $viewModel.horizon) {
                                ForEach(SimulationHorizon.allCases) { horizon in
                                    Text(horizon.title).tag(horizon)
                                }
                            }
                            .pickerStyle(.segmented)

                            HStack {
                                if viewModel.runType == .past {
                                    DatePicker(
                                        "Historical Start",
                                        selection: $viewModel.startDate,
                                        in: ...Date.now,
                                        displayedComponents: .date
                                    )
                                    DatePicker(
                                        "Historical End",
                                        selection: $viewModel.endDate,
                                        in: ...Date.now,
                                        displayedComponents: .date
                                    )
                                } else {
                                    DatePicker(
                                        "Forecast Start",
                                        selection: $viewModel.startDate,
                                        in: Date.now...,
                                        displayedComponents: .date
                                    )
                                    DatePicker(
                                        "Forecast End",
                                        selection: $viewModel.endDate,
                                        in: viewModel.startDate...,
                                        displayedComponents: .date
                                    )
                                }
                            }
                            .onChange(of: viewModel.runType) { _, _ in
                                viewModel.syncDatesForRunType()
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Initial Investment (€)")
                                    .font(.subheadline.weight(.semibold))
                                TextField("€10,000", text: $viewModel.initialCapital)
                                    .keyboardType(.decimalPad)
                                    .textFieldStyle(.roundedBorder)
                                    .focused($isInvestmentFieldFocused)
                                Text("This is the starting amount used to translate forecasted returns into ending portfolio values.")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Models used in every run")
                                    .font(.subheadline.weight(.semibold))
                                Text(
                                    viewModel.runType == .past
                                        ? "Past runs compare the fixed Truth Model with the current Working Model over the same historical window."
                                        : "Future runs store the starting Truth Model and Working Model now, then add the Updated Working Model when the forecast period finishes."
                                )
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                            }

                            Button {
                                isInvestmentFieldFocused = false
                                Task { await viewModel.runSimulation(notificationManager: notificationManager) }
                            } label: {
                                if viewModel.isRunning {
                                    ProgressView()
                                        .tint(.white)
                                        .frame(maxWidth: .infinity)
                                } else {
                                    Text(viewModel.runType == .past ? "Run Past Simulation" : "Run Future Simulation")
                                        .frame(maxWidth: .infinity)
                                }
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.gvAccent)
                            .accessibilityIdentifier("run_simulation_button")
                        }

                        if let result = viewModel.simulationResult {
                            ContentCard(title: "Latest Result") {
                                ResultHeaderView(result: result)
                                ComparativeSimulationChart(models: result.models)
                                ForEach(result.models) { model in
                                    SimulationModelCard(model: model, initialInvestment: result.initialInvestment) {
                                        selectedModel = model
                                    }
                                }
                                if let analysis = result.aiAnalysis ?? result.keyOutcomeSummary {
                                    AIAnalysisSection(text: analysis)
                                }
                            }
                        }

                        ContentCard(title: viewModel.runType == .past ? "Recent Past Runs" : "Recent Future Runs") {
                            if viewModel.isLoading && viewModel.visibleRecentSimulations.isEmpty {
                                LoadingStateView(message: "Loading simulations...")
                            } else if viewModel.visibleRecentSimulations.isEmpty {
                                EmptyStateView(
                                    title: viewModel.runType == .past ? "No Past Simulations Yet" : "No Future Simulations Yet",
                                    message: viewModel.runType == .past
                                        ? "Run your first historical comparison to review Truth Model and Working Model performance."
                                        : "Run your first forward-looking scenario to store live forecasts for later evaluation."
                                )
                            } else {
                                VStack(spacing: 12) {
                                    ForEach(viewModel.visibleRecentSimulations) { simulation in
                                        Button {
                                            selectedRun = simulation
                                        } label: {
                                            RecentSimulationRow(simulation: simulation)
                                        }
                                        .buttonStyle(.plain)
                                        .swipeActions {
                                            Button(role: .destructive) {
                                                Task { await viewModel.deleteSimulation(simulation) }
                                            } label: {
                                                Label("Delete", systemImage: "trash")
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    .padding()
                }
                .contentShape(Rectangle())
                .onTapGesture {
                    isInvestmentFieldFocused = false
                }
            }
            .navigationTitle("Simulations")
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") {
                        isInvestmentFieldFocused = false
                    }
                }
            }
            .task { await viewModel.load() }
            .sheet(isPresented: $isBasketComposerPresented) {
                BasketComposerSheet(backend: backend, availableStocks: viewModel.stocks) { basket in
                    viewModel.assetKind = .basket
                    viewModel.selectedBasketID = basket.basketId
                    Task { await viewModel.load() }
                }
            }
            .sheet(item: $selectedRun) { run in
                SimulationRunDetailSheet(run: run) {
                    Task {
                        await viewModel.deleteSimulation(run)
                        selectedRun = nil
                    }
                }
            }
            .sheet(item: $selectedModel) { model in
                ModelExplanationSheet(model: model)
            }
        }
    }
}

private struct ResultHeaderView: View {
    let result: SimulationResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(result.simulationType == "past" ? "Past Simulation" : "Future Simulation")
                    .font(.headline)
                Spacer()
                Text(result.status.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Text("\(result.portfolioName) • \(AppDateParser.shortDate.string(from: AppDateParser.parse(result.startDate))) to \(AppDateParser.shortDate.string(from: AppDateParser.parse(result.endDate)))")
                .font(.footnote)
                .foregroundStyle(.secondary)
            InfoChip(title: "Initial Investment", value: result.initialInvestment.currencyString)
        }
    }
}

private struct ComparativeSimulationChart: View {
    let models: [SimulationModelResult]

    var body: some View {
        Chart(chartRows) { row in
            BarMark(
                x: .value("Model", row.label),
                y: .value("Return", row.value)
            )
            .foregroundStyle(row.seriesColor)
            .position(by: .value("Series", row.series))
        }
        .frame(height: 220)
    }

    private var chartRows: [ChartRow] {
        models.flatMap { model in
            var rows: [ChartRow] = []
            if let predicted = model.predictedReturn {
                rows.append(ChartRow(label: model.displayName, series: "Predicted", value: predicted, seriesColor: Color.gvAccent))
            }
            if let actual = model.actualReturn {
                rows.append(ChartRow(label: model.displayName, series: "Actual", value: actual, seriesColor: Color.gvChartNegative))
            }
            return rows
        }
    }
}

private struct SimulationModelCard: View {
    let model: SimulationModelResult
    let initialInvestment: Double
    let onExplain: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.displayName)
                        .font(.headline)
                    Text(model.versionID ?? "Version unavailable")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("About") {
                    onExplain()
                }
                .buttonStyle(.bordered)
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ValueTile(title: "Initial Investment", value: initialInvestment.currencyString)
                ValueTile(title: "Predicted Ending Value", value: model.predictedEndingValue?.currencyString ?? "n/a")
                ValueTile(title: "Actual Ending Value", value: model.actualEndingValue?.currencyString ?? "Awaiting data")
                ValueTile(title: "Status", value: model.status?.replacingOccurrences(of: "_", with: " ").capitalized ?? "n/a")
                ValueTile(title: "Predicted Return", value: combinedReturnText(currency: model.predictedGainLoss, percent: model.predictedReturn))
                ValueTile(title: "Actual Return", value: combinedReturnText(currency: model.actualGainLoss, percent: model.actualReturn))
            }

            if let explanation = model.explanation {
                Text(explanation)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            if let rank = model.rank {
                Text("Performance rank: \(rank)")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Color.gvAccent)
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color.gvCardBackground.opacity(0.78))
        )
    }

    private func combinedReturnText(currency: Double?, percent: Double?) -> String {
        switch (currency, percent) {
        case let (.some(currency), .some(percent)):
            return "\(currency.currencyString) (\(percent.percentString))"
        case let (.some(currency), .none):
            return currency.currencyString
        case let (.none, .some(percent)):
            return percent.percentString
        default:
            return "n/a"
        }
    }
}

private struct ValueTile: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.subheadline.weight(.semibold))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.gvAccent.opacity(0.08))
        )
    }
}

private struct AIAnalysisSection: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("AI Analysis")
                .font(.headline)
            Text(text)
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

private struct RecentSimulationRow: View {
    let simulation: SimulationRecord

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(simulation.portfolioName ?? "Portfolio")
                        .font(.headline)
                    Text(simulation.simulationType == "future" ? "Future Simulation" : "Past Simulation")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(simulation.status?.replacingOccurrences(of: "_", with: " ").capitalized ?? "n/a")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            Text("Created \(AppDateParser.shortDate.string(from: simulation.dateValue))")
                .font(.footnote)
                .foregroundStyle(.secondary)

            Text("\(AppDateParser.shortDate.string(from: AppDateParser.parse(simulation.startDate))) to \(AppDateParser.shortDate.string(from: AppDateParser.parse(simulation.endDate)))")
                .font(.footnote)
                .foregroundStyle(.secondary)

            HStack {
                InfoChip(title: "Initial", value: simulation.initialCapital.currencyString)
                InfoChip(title: "Models", value: String(modelsCount))
            }

            if let summary = simulation.keyOutcomeSummary {
                Text(summary)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color.gvCardBackground.opacity(0.86))
        )
    }

    private var modelsCount: Int {
        let fromNames = simulation.modelsUsed?.count ?? 0
        let fromResults = simulation.modelResults?.count ?? 0
        if max(fromNames, fromResults) > 0 {
            return max(fromNames, fromResults)
        }
        return simulation.simulationType == "future" ? 2 : 2
    }
}

private struct SimulationRunDetailSheet: View {
    let run: SimulationRecord
    let onDelete: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    ContentCard(title: run.portfolioName ?? "Simulation") {
                        Text(run.keyOutcomeSummary ?? "No summary available.")
                            .foregroundStyle(.secondary)
                        HStack {
                            InfoChip(title: "Type", value: run.simulationType == "future" ? "Future" : "Past")
                            InfoChip(title: "Status", value: run.status?.replacingOccurrences(of: "_", with: " ").capitalized ?? "n/a")
                        }
                        HStack {
                            InfoChip(title: "Created", value: AppDateParser.shortDate.string(from: run.dateValue))
                            InfoChip(title: "Initial", value: run.initialCapital.currencyString)
                        }
                    }

                    if let models = run.modelResults {
                        ContentCard(title: "Models Used") {
                            ComparativeSimulationChart(models: models)
                            ForEach(models) { model in
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(model.displayName)
                                        .font(.headline)
                                    Text(model.versionID ?? "Version unavailable")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(model.explanation ?? "No explanation available.")
                                        .font(.footnote)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 4)
                            }
                        }
                    }

                    if let analysis = run.aiAnalysis {
                        ContentCard(title: "AI Analysis") {
                            Text(analysis)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Run Details")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(role: .destructive) {
                        onDelete()
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

private struct ChartRow: Identifiable {
    let id = UUID()
    let label: String
    let series: String
    let value: Double
    let seriesColor: Color
}

private struct ModelExplanationSheet: View {
    let model: SimulationModelResult
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    ContentCard(title: model.displayName) {
                        Text(model.explanation ?? "No explanation available.")
                            .foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 8) {
                            Text("What it relies on")
                                .font(.subheadline.weight(.semibold))
                            Text("Historical price data, the selected horizon, basket composition if relevant, and the backend forecasting logic tied to this model version.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                            Text("What it is good at")
                                .font(.subheadline.weight(.semibold))
                            Text(modelStrengthText)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                            Text("Limitations")
                                .font(.subheadline.weight(.semibold))
                            Text(modelLimitationText)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                            Text("Why it may differ")
                                .font(.subheadline.weight(.semibold))
                            Text(modelDifferenceText)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Model Info")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private var modelStrengthText: String {
        switch model.modelKey {
        case "truth_model":
            return "Consistency, auditability, and serving as the fixed reference model."
        case "working_model":
            return "Active simulation work with current adaptive logic."
        default:
            return "Representing the most current predictive logic after iterative backend learning."
        }
    }

    private var modelLimitationText: String {
        switch model.modelKey {
        case "truth_model":
            return "It does not learn from new simulation outcomes."
        case "working_model":
            return "It may lag behind the newest learned adjustments."
        default:
            return "It changes over time, so version tracking and interpretation matter."
        }
    }

    private var modelDifferenceText: String {
        switch model.modelKey {
        case "truth_model":
            return "It stays fixed while the other two models adapt."
        case "working_model":
            return "It adapts, but it is not the newest iteratively improved state."
        default:
            return "It reflects the latest backend learning, so its output can differ from both the static Truth Model and the active Working Model."
        }
    }
}
