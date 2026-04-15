import Charts
import SwiftUI

struct ScreenContainer<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        ZStack(alignment: .top) {
            AppTheme.backgroundGradient.ignoresSafeArea()
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                .safeAreaPadding(.bottom, 28)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color.gvBackground.ignoresSafeArea())
        .fontDesign(.rounded)
    }
}

struct ContentCard<Content: View>: View {
    let title: String?
    let content: Content

    init(title: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let title {
                Text(title)
                    .font(.headline)
            }
            content
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(Color.gvCardBackground.opacity(0.92))
                .shadow(color: .black.opacity(0.06), radius: 16, y: 8)
        )
    }
}

struct InfoChip: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.subheadline.weight(.semibold))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Capsule().fill(Color.gvAccent.opacity(0.12)))
    }
}

struct LoadingStateView: View {
    let message: String

    var body: some View {
        VStack(spacing: 12) {
            ProgressView()
                .tint(.gvAccent)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 160)
    }
}

struct EmptyStateView: View {
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 10) {
            Text(title)
                .font(.headline)
            Text(message)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 160)
    }
}

struct FloatingChatButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label("Chat", systemImage: "message.fill")
                .font(.headline)
                .padding(.horizontal, 18)
                .padding(.vertical, 12)
                .background(
                    Capsule()
                        .fill(Color.gvAccent)
                        .shadow(color: Color.gvAccent.opacity(0.35), radius: 12, y: 6)
                )
                .foregroundStyle(.white)
        }
        .accessibilityIdentifier("floating_chat_button")
    }
}

struct PriceLineChart: View {
    let points: [PricePoint]

    var body: some View {
        Chart(Array(points.suffix(30))) { point in
            if let close = point.close {
                LineMark(x: .value("Date", point.dateValue), y: .value("Close", close))
                    .foregroundStyle(Color.gvAccent)
                AreaMark(x: .value("Date", point.dateValue), y: .value("Close", close))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color.gvAccent.opacity(0.2), Color.gvAccent.opacity(0.01)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading)
        }
        .frame(height: 220)
    }
}

struct CandlestickPriceChart: View {
    let points: [PricePoint]

    var body: some View {
        Chart(Array(points.suffix(20))) { point in
            let open = point.open ?? point.close ?? 0
            let close = point.close ?? point.open ?? 0
            let high = point.high ?? max(open, close)
            let low = point.low ?? min(open, close)
            RuleMark(
                x: .value("Date", point.dateValue),
                yStart: .value("Low", low),
                yEnd: .value("High", high)
            )
            .foregroundStyle(.secondary)

            RectangleMark(
                x: .value("Date", point.dateValue),
                yStart: .value("Open", open),
                yEnd: .value("Close", close),
                width: 8
            )
            .foregroundStyle(close >= open ? Color.gvChartPositive : Color.gvChartNegative)
        }
        .chartYAxis {
            AxisMarks(position: .leading)
        }
        .frame(height: 220)
    }
}

struct RiskMetricBarChart: View {
    let riskMetrics: RiskMetrics

    private var entries: [(String, Double)] {
        [
            ("Vol", riskMetrics.volatility ?? 0),
            ("Sharpe", riskMetrics.sharpe ?? 0),
            ("Sortino", riskMetrics.sortino ?? 0),
            ("Beta", riskMetrics.beta ?? 0)
        ]
    }

    var body: some View {
        Chart(entries, id: \.0) { entry in
            BarMark(x: .value("Metric", entry.0), y: .value("Value", entry.1))
                .foregroundStyle(Color.gvAccent.gradient)
        }
        .frame(height: 180)
    }
}

struct SimulationTrendChart: View {
    let simulations: [SimulationRecord]

    var body: some View {
        Chart(simulations) { simulation in
            if let predicted = simulation.predictedReturn {
                LineMark(x: .value("Run", simulation.dateValue), y: .value("Predicted", predicted))
                    .foregroundStyle(Color.gvAccent)
            }
            if let actual = simulation.actualReturn {
                LineMark(x: .value("Run", simulation.dateValue), y: .value("Actual", actual))
                    .foregroundStyle(Color.gvChartNegative)
            }
        }
        .frame(height: 220)
    }
}

struct ErrorBanner: View {
    let message: String

    var body: some View {
        Text(message)
            .font(.footnote)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color.red.opacity(0.12))
            )
            .foregroundStyle(Color.red)
    }
}
