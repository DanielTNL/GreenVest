import SwiftUI

struct BasketComposerSheet: View {
    @Environment(\.dismiss) private var dismiss

    let backend: any BackendServing
    let availableStocks: [StockSummary]
    let initialBasket: BasketSummary?
    let onSaved: (BasketSummary) -> Void

    @State private var name: String
    @State private var description: String
    @State private var searchText = ""
    @State private var selectedSymbols: Set<String>
    @State private var isSaving = false
    @State private var isLoadingStocks = false
    @State private var loadedStocks: [StockSummary] = []
    @State private var errorMessage: String?

    init(
        backend: any BackendServing,
        availableStocks: [StockSummary],
        initialBasket: BasketSummary? = nil,
        onSaved: @escaping (BasketSummary) -> Void
    ) {
        self.backend = backend
        self.availableStocks = availableStocks
        self.initialBasket = initialBasket
        self.onSaved = onSaved
        _name = State(initialValue: initialBasket?.name ?? "")
        _description = State(initialValue: initialBasket?.description ?? "")
        _selectedSymbols = State(initialValue: Set(initialBasket?.constituents.map(\.symbol) ?? []))
    }

    private var filteredStocks: [StockSummary] {
        let normalizedQuery = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        let sortedStocks = stockUniverse.sorted {
            ($0.name ?? $0.symbol).localizedCaseInsensitiveCompare($1.name ?? $1.symbol) == .orderedAscending
        }
        guard !normalizedQuery.isEmpty else { return sortedStocks }
        return sortedStocks.filter {
            $0.symbol.localizedCaseInsensitiveContains(normalizedQuery)
                || ($0.name ?? "").localizedCaseInsensitiveContains(normalizedQuery)
        }
    }

    private var stockUniverse: [StockSummary] {
        availableStocks.isEmpty ? loadedStocks : availableStocks
    }

    private var canSave: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !selectedSymbols.isEmpty
            && !isSaving
    }

    var body: some View {
        NavigationStack {
            ScreenContainer {
                ScrollView {
                    VStack(spacing: 16) {
                        if let errorMessage {
                            ErrorBanner(message: errorMessage)
                        }

                        ContentCard(title: initialBasket == nil ? "Basket Details" : "Update Basket") {
                            TextField("Basket name", text: $name)
                                .textFieldStyle(.roundedBorder)

                            TextField("Description", text: $description, axis: .vertical)
                                .textFieldStyle(.roundedBorder)

                            TextField("Search stocks", text: $searchText)
                                .textFieldStyle(.roundedBorder)
                                .textInputAutocapitalization(.never)

                            if !selectedSymbols.isEmpty {
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack {
                                        ForEach(Array(selectedSymbols).sorted(), id: \.self) { symbol in
                                            InfoChip(title: symbol, value: "Selected")
                                        }
                                    }
                                }
                            }
                        }

                        ContentCard(title: "Select Holdings") {
                            if isLoadingStocks && stockUniverse.isEmpty {
                                LoadingStateView(message: "Loading stocks...")
                            } else if filteredStocks.isEmpty {
                                EmptyStateView(
                                    title: "No Matching Stocks",
                                    message: "Load market data first or broaden the search to add holdings."
                                )
                            } else {
                                LazyVStack(spacing: 10) {
                                    ForEach(filteredStocks) { stock in
                                        Button {
                                            toggleSelection(for: stock.symbol)
                                        } label: {
                                            HStack(spacing: 12) {
                                                Image(systemName: selectedSymbols.contains(stock.symbol) ? "checkmark.circle.fill" : "circle")
                                                    .foregroundStyle(selectedSymbols.contains(stock.symbol) ? Color.gvAccent : .secondary)
                                                    .font(.title3)
                                                VStack(alignment: .leading, spacing: 4) {
                                                    Text(stock.symbol)
                                                        .font(.headline)
                                                    Text(stock.name ?? "Unknown company")
                                                        .font(.subheadline)
                                                        .foregroundStyle(.secondary)
                                                }
                                                Spacer()
                                                Text(stock.latestClose?.currencyString ?? "n/a")
                                                    .font(.subheadline.weight(.semibold))
                                            }
                                            .padding(.vertical, 6)
                                        }
                                        .buttonStyle(.plain)
                                        if stock.id != filteredStocks.last?.id {
                                            Divider()
                                        }
                                    }
                                }
                            }
                        }

                        Button {
                            Task { await saveBasket() }
                        } label: {
                            if isSaving {
                                ProgressView()
                                    .tint(.white)
                                    .frame(maxWidth: .infinity)
                            } else {
                                Text(initialBasket == nil ? "Save Basket" : "Update Basket")
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.gvAccent)
                        .disabled(!canSave)
                    }
                    .padding()
                }
            }
            .navigationTitle(initialBasket == nil ? "New Basket" : "Edit Basket")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
            .task {
                await loadStocksIfNeeded()
            }
        }
    }

    private func toggleSelection(for symbol: String) {
        if selectedSymbols.contains(symbol) {
            selectedSymbols.remove(symbol)
        } else {
            selectedSymbols.insert(symbol)
        }
    }

    @MainActor
    private func saveBasket() async {
        isSaving = true
        defer { isSaving = false }
        do {
            let basket = try await backend.createBasket(
                request: BasketCreateRequest(
                    name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                    description: description.trimmingCharacters(in: .whitespacesAndNewlines),
                    symbols: Array(selectedSymbols).sorted(),
                    equalWeight: true
                )
            )
            errorMessage = nil
            onSaved(basket)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    private func loadStocksIfNeeded() async {
        guard availableStocks.isEmpty, loadedStocks.isEmpty, !isLoadingStocks else { return }
        isLoadingStocks = true
        defer { isLoadingStocks = false }
        do {
            loadedStocks = try await backend.fetchStocks(query: nil)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
