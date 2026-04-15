import XCTest
@testable import GreenVest

@MainActor
final class ViewModelTests: XCTestCase {
    func testSimulationViewModelLoadsPreviewOptions() async {
        let viewModel = SimulationViewModel(backend: PreviewBackendService())
        await viewModel.load()

        XCTAssertEqual(viewModel.stocks.count, 3)
        XCTAssertEqual(viewModel.selectedStockSymbol, "AAPL")
        XCTAssertEqual(viewModel.baskets.first?.name, "Tech Basket")
    }

    func testMetricsViewModelLoadsDashboard() async {
        let viewModel = MetricsViewModel(backend: PreviewBackendService())
        await viewModel.load()

        XCTAssertEqual(viewModel.dashboard?.knowledgeVersion, "daily-preview-1")
        XCTAssertEqual(viewModel.dashboard?.items.count, 2)
    }
}
